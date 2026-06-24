"""PyInstaller entry point for ALEXIS.exe.

Thin wrapper around app.__main__:main so the frozen exe behaves exactly like
``python -m app`` (including ``ALEXIS.exe --run-pipeline <id>`` for the job
runner and ``--headless`` for a browser smoke test).
"""

import multiprocessing
import sys

from app.__main__ import main

if __name__ == "__main__":
    # Give every process (incl. any multiprocessing worker, which is a windowed
    # subprocess with sys.stdout/stderr = None) usable streams BEFORE the
    # multiprocessing bootstrap runs -- otherwise a worker error crashes in
    # _bootstrap with "'NoneType' has no attribute 'write'".
    try:
        from app.main import ensure_streams
        ensure_streams()
    except Exception:
        pass
    # MUST be first real action: in the frozen exe each multiprocessing worker
    # re-launches THIS entry point. freeze_support() makes those launches run
    # the worker and exit, instead of re-starting the whole app.
    multiprocessing.freeze_support()
    sys.exit(main())
