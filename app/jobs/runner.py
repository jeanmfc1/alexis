"""Subprocess job runner.

Launches catalog pipelines as child processes, captures their combined
stdout+stderr to a per-run log file, tracks status in a JobRegistry, and
supports cancellation. Designed for Windows first (the deployment target) with
a POSIX fallback so it also runs on the WSL dev box.

A module-level singleton ``RUNNER`` is shared by the API layer.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from core.paths import app_root, logs_dir, ensure_dir
from app.jobs import catalog
from app.jobs.registry import JobRegistry

_IS_WIN = sys.platform == "win32"

# Grace period between escalating cancel signals.
_CANCEL_GRACE_S = 3.0


class JobRunner:
    def __init__(self) -> None:
        self.registry = JobRegistry()
        # run_id -> {"proc": Popen, "fh": file handle, "thread": Thread}
        self._procs: dict[str, dict] = {}
        self._lock = threading.Lock()

    # -- start --------------------------------------------------------------
    def start(self, job_id: str) -> dict:
        entry = catalog.get_entry(job_id)
        if entry is None:
            raise ValueError(f"unknown job_id: {job_id}")
        if not entry.get("ready", False):
            raise ValueError(f"job not ready to run: {job_id}")

        argv = catalog.build_argv(job_id)
        run = self.registry.create(
            job_id=job_id,
            label=entry["label"],
            argv=argv,
            produces=entry.get("produces"),
        )
        run_id = run["run_id"]

        ensure_dir(logs_dir())
        log_path = logs_dir() / f"{run_id}.log"
        self.registry.update(run_id, log_file=str(log_path))

        # Child environment: unbuffered + utf-8 so logs stream promptly and do
        # not crash on a cp1252 console; repo root on PYTHONPATH so "-m
        # pipelines.x" and "import core..." resolve in the child.
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        root = str(app_root())
        prior = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = root + (os.pathsep + prior if prior else "")

        creationflags = 0
        start_new_session = False
        if _IS_WIN:
            # CREATE_NO_WINDOW: no console flashes. CREATE_NEW_PROCESS_GROUP:
            # the child gets its own group so CTRL_BREAK_EVENT hits only it,
            # never the parent uvicorn/pywebview process.
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            start_new_session = True

        # Binary log file; child writes utf-8 bytes, the reader decodes with
        # errors="replace". Never inherit the parent's stdout.
        fh = open(log_path, "wb")
        try:
            fh.write(f"[runner] $ {' '.join(argv)}\n".encode("utf-8"))
            fh.write(f"[runner] cwd={root}\n".encode("utf-8"))
            fh.flush()
            proc = subprocess.Popen(
                argv,
                cwd=root,
                env=env,
                stdout=fh,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
                start_new_session=start_new_session,
            )
        except Exception as exc:
            fh.write(f"[runner] failed to start: {exc}\n".encode("utf-8"))
            fh.close()
            self.registry.update(run_id, status="failed", returncode=-1,
                                 ended_at=None)
            self.registry.mark_finished(run_id, returncode=-1)
            raise

        self.registry.mark_started(run_id, pid=proc.pid)

        watcher = threading.Thread(
            target=self._watch, args=(run_id, proc, fh),
            name=f"alexis-job-{run_id[:8]}", daemon=True,
        )
        with self._lock:
            self._procs[run_id] = {"proc": proc, "fh": fh, "thread": watcher}
        watcher.start()

        return self.registry.get(run_id)

    # -- watch --------------------------------------------------------------
    def _watch(self, run_id: str, proc: subprocess.Popen, fh) -> None:
        try:
            returncode = proc.wait()
        finally:
            try:
                fh.flush()
                fh.close()
            except Exception:
                pass
        self.registry.mark_finished(run_id, returncode=returncode)

    # -- cancel -------------------------------------------------------------
    def cancel(self, run_id: str) -> dict:
        run = self.registry.get(run_id)
        if run is None:
            raise KeyError(run_id)
        if JobRegistry.is_terminal(run):
            raise ValueError("run already finished")

        with self._lock:
            handle = self._procs.get(run_id)
        proc = handle["proc"] if handle else None

        # Mark intent first so the watcher keeps the 'cancelled' status.
        self.registry.mark_cancelled(run_id)

        if proc is None or proc.poll() is not None:
            return self.registry.get(run_id)

        try:
            if _IS_WIN:
                # Only valid for a child started with CREATE_NEW_PROCESS_GROUP.
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.terminate()
        except Exception:
            pass

        if not self._wait(proc, _CANCEL_GRACE_S):
            try:
                proc.terminate()
            except Exception:
                pass
            if not self._wait(proc, _CANCEL_GRACE_S):
                try:
                    proc.kill()
                except Exception:
                    pass

        return self.registry.get(run_id)

    @staticmethod
    def _wait(proc: subprocess.Popen, timeout: float) -> bool:
        try:
            proc.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False

    # -- introspection ------------------------------------------------------
    def get(self, run_id: str) -> dict | None:
        return self.registry.get(run_id)

    def list_runs(self) -> list[dict]:
        return self.registry.list_runs()

    def log_path(self, run_id: str) -> Path | None:
        run = self.registry.get(run_id)
        if run and run.get("log_file"):
            return Path(run["log_file"])
        return None


# Shared singleton used by the API layer.
RUNNER = JobRunner()
