"""In-process pipeline dispatch for frozen builds.

In a PyInstaller exe ``python -m pipelines.x`` is unavailable, so the job
runner re-launches the exe as ``ALEXIS.exe --run-pipeline <job_id>`` and
app.__main__ calls :func:`run_pipeline`, which runs the catalog target via
runpy exactly as ``-m module <argv>`` / ``script <argv>`` would.
"""

from __future__ import annotations

import runpy
import sys

from core.paths import app_root
from app.jobs import catalog


def _exit_code(exc: SystemExit) -> int:
    code = exc.code
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    return 1  # a string/other -> treat as failure


def run_pipeline(job_id: str, extra_args: list[str] | None = None) -> int:
    """Run a catalog pipeline in this process. Returns its exit code.

    ``extra_args`` are the parameter flags the parent appended after
    ``--run-pipeline <id>`` (e.g. ``--aact-dir ...``); they are forwarded to the
    pipeline's argv so a frozen build honours GUI form values.
    """
    # In a windowed frozen build sys.stdout/err are None; reattach the handles
    # the parent runner gave us (fd 1/2 -> the per-run log file).
    try:
        from app.main import ensure_streams
        ensure_streams()
    except Exception:  # noqa: BLE001
        pass

    entry = catalog.get_entry(job_id)
    if entry is None:
        print(f"[err] unknown pipeline: {job_id}")
        return 2

    tail = list(entry.get("argv", [])) + list(extra_args or [])
    try:
        if entry.get("module"):
            sys.argv = [entry["module"], *tail]
            runpy.run_module(entry["module"], run_name="__main__", alter_sys=True)
            return 0
        if entry.get("script"):
            path = app_root() / entry["script"]
            sys.argv = [str(path), *tail]
            runpy.run_path(str(path), run_name="__main__")
            return 0
    except SystemExit as exc:
        return _exit_code(exc)
    except Exception as exc:  # noqa: BLE001 -- surface to the job log
        print(f"[err] pipeline {job_id} crashed: {type(exc).__name__}: {exc}")
        return 1

    print(f"[err] pipeline {job_id} has no module/script target")
    return 2
