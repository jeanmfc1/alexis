"""Thread-safe in-memory store of job runs.

A JobRun is a plain JSON-ready dict (see the shape below). The registry is the
single source of truth for run state, mutated by both request handlers (start,
cancel) and the runner's watcher threads, so every access is guarded by a lock.

JobRun shape:
    {
      "run_id": "<uuid hex>", "job_id": "<str>", "label": "<str>",
      "status": "pending"|"running"|"succeeded"|"failed"|"cancelled",
      "pid": <int|null>, "returncode": <int|null>,
      "started_at": "<iso|null>", "ended_at": "<iso|null>",
      "argv": [<str>, ...], "log_file": "<abs path str|null>",
      "produces": "<str|null>",
    }
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime

_TERMINAL = ("succeeded", "failed", "cancelled")


class JobRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, dict] = {}
        self._order: list[str] = []  # creation order; newest is last

    def create(self, job_id: str, label: str, argv: list[str],
               produces: str | None) -> dict:
        run_id = uuid.uuid4().hex
        run = {
            "run_id": run_id,
            "job_id": job_id,
            "label": label,
            "status": "pending",
            "pid": None,
            "returncode": None,
            "started_at": None,
            "ended_at": None,
            "argv": list(argv),
            "log_file": None,
            "produces": produces,
        }
        with self._lock:
            self._runs[run_id] = run
            self._order.append(run_id)
        return dict(run)

    def get(self, run_id: str) -> dict | None:
        with self._lock:
            run = self._runs.get(run_id)
            return dict(run) if run else None

    def list_runs(self) -> list[dict]:
        """Newest first."""
        with self._lock:
            return [dict(self._runs[rid]) for rid in reversed(self._order)
                    if rid in self._runs]

    def update(self, run_id: str, **fields) -> dict | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            run.update(fields)
            return dict(run)

    def mark_started(self, run_id: str, pid: int) -> dict | None:
        return self.update(run_id, status="running", pid=pid,
                           started_at=datetime.now().isoformat())

    def mark_finished(self, run_id: str, returncode: int) -> dict | None:
        """Finalize a run that ran to completion. Respects a prior 'cancelled'."""
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            if run["status"] != "cancelled":
                run["status"] = "succeeded" if returncode == 0 else "failed"
            run["returncode"] = returncode
            run["ended_at"] = datetime.now().isoformat()
            return dict(run)

    def mark_cancelled(self, run_id: str) -> dict | None:
        return self.update(run_id, status="cancelled",
                           ended_at=datetime.now().isoformat())

    @staticmethod
    def is_terminal(run: dict | None) -> bool:
        return bool(run) and run.get("status") in _TERMINAL
