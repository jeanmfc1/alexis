"""Job endpoints: catalog, start, list, status, cancel, and SSE log stream.

All handlers are sync def (FastAPI threadpools them) EXCEPT the SSE log stream,
which is async and returns an EventSourceResponse driven by a non-blocking
async generator that tails the run's log file.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.jobs import catalog
from app.jobs.runner import RUNNER

router = APIRouter()
_log = logging.getLogger("alexis.api.jobs")

# Defensive ceiling so a wedged job cannot leak a streaming coroutine forever.
_MAX_STREAM_SECONDS = 3600.0
_POLL_INTERVAL_S = 0.4
_TERMINAL = ("succeeded", "failed", "cancelled")


@router.get("/api/jobs/catalog")
def jobs_catalog() -> dict:
    return {"jobs": catalog.get_catalog()}


@router.get("/api/jobs")
def list_jobs() -> dict:
    return {"runs": RUNNER.list_runs()}


@router.post("/api/jobs")
def start_job(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")
    job_id = payload.get("job_id")
    if not job_id or not isinstance(job_id, str):
        raise HTTPException(status_code=400, detail="job_id is required")
    try:
        return RUNNER.start(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        _log.exception("[err] start_job failed: %s", exc)
        raise HTTPException(status_code=500,
                            detail=f"could not start job: {type(exc).__name__}")


@router.get("/api/jobs/{run_id}")
def get_job(run_id: str) -> dict:
    run = RUNNER.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown run_id")
    return run


@router.post("/api/jobs/{run_id}/cancel")
def cancel_job(run_id: str) -> dict:
    try:
        return RUNNER.cancel(run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown run_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        _log.exception("[err] cancel_job failed: %s", exc)
        raise HTTPException(status_code=500,
                            detail=f"could not cancel job: {type(exc).__name__}")


def _read_from(log_path: Path | None, pos: int) -> tuple[str, int]:
    """Read new bytes from `pos`; return (decoded_text, new_pos)."""
    if not log_path or not log_path.exists():
        return "", pos
    try:
        with open(log_path, "rb") as fh:
            fh.seek(pos)
            chunk = fh.read()
            new_pos = fh.tell()
    except OSError:
        return "", pos
    if not chunk:
        return "", new_pos
    return chunk.decode("utf-8", errors="replace"), new_pos


@router.get("/api/jobs/{run_id}/logs")
async def stream_logs(run_id: str, request: Request) -> EventSourceResponse:
    run = RUNNER.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown run_id")

    async def _gen():
        log_path = Path(run["log_file"]) if run.get("log_file") else None
        pos = 0
        started = time.monotonic()
        while True:
            if await request.is_disconnected():
                return

            text, pos = _read_from(log_path, pos)
            if text:
                yield {"event": "log", "data": text}

            cur = RUNNER.get(run_id)
            if cur is None or cur.get("status") in _TERMINAL:
                # Final flush: the watcher closes the log file before marking
                # the run terminal, so anything left is fully written by now.
                tail, pos = _read_from(log_path, pos)
                if tail:
                    yield {"event": "log", "data": tail}
                yield {
                    "event": "end",
                    "data": json.dumps({
                        "status": cur.get("status") if cur else "unknown",
                        "returncode": cur.get("returncode") if cur else None,
                    }),
                }
                return

            if time.monotonic() - started > _MAX_STREAM_SECONDS:
                yield {"event": "end", "data": json.dumps({"status": "timeout"})}
                return

            await asyncio.sleep(_POLL_INTERVAL_S)

    return EventSourceResponse(_gen())
