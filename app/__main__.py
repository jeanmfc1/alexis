"""``python -m app`` entrypoint.

Parses a minimal CLI and delegates to ``app.main.run``. Exit code is the
return value of ``run``.
"""

from __future__ import annotations

import argparse
import sys


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="alexis",
        description="ALEXIS desktop app (MVP). Boots a localhost FastAPI server "
        "and opens a pywebview window.",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Enable dev-mode logging.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Do not open a window; just serve on localhost and wait for Ctrl+C.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Explicit port to bind on 127.0.0.1. Default: an OS-assigned free port.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)

    # Frozen-build pipeline dispatch: the job runner re-launches the exe as
    # `ALEXIS.exe --run-pipeline <job_id>`. Intercept this BEFORE the GUI
    # argparse so the pipeline can own sys.argv (it parses its own flags).
    if raw and raw[0] == "--run-pipeline":
        if len(raw) < 2:
            print("[err] --run-pipeline requires a job id")
            return 2
        from app.jobs.dispatch import run_pipeline
        return run_pipeline(raw[1], extra_args=raw[2:])

    # Frozen-build module dispatch: some pipelines spawn a FRESH subprocess of a
    # helper module for RAM isolation (e.g. enrich_weekly -> analytics.update_
    # categorizer). They can't use `python -m mod` because sys.executable is the
    # exe, so they call `ALEXIS.exe --run-module <mod> [args]` and we run it here
    # via runpy -- the same mechanism dispatch.py uses for pipeline modules.
    if raw and raw[0] == "--run-module":
        if len(raw) < 2:
            print("[err] --run-module requires a module name")
            return 2
        import runpy
        mod = raw[1]
        sys.argv = [mod, *raw[2:]]
        try:
            runpy.run_module(mod, run_name="__main__", alter_sys=True)
            return 0
        except SystemExit as exc:
            code = exc.code
            return code if isinstance(code, int) else (0 if code is None else 1)

    from app.main import run
    args = _parse_args(raw)
    return run(dev=args.dev, headless=args.headless, port=args.port)


if __name__ == "__main__":
    # CRITICAL for the packaged (PyInstaller) build: classification uses
    # multiprocessing, and on Windows each worker re-launches this exe. Without
    # freeze_support() the worker would re-run the whole app (spawn storm /
    # "failed to extract archive" errors). This must be the first thing the
    # frozen entry point does, before any argument parsing.
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
