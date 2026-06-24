"""PyInstaller entry point for ALEXIS.exe.

Thin wrapper around app.__main__:main so the frozen exe behaves exactly like
``python -m app`` (including ``ALEXIS.exe --run-pipeline <id>`` for the job
runner and ``--headless`` for a browser smoke test).
"""

import multiprocessing
import sys

from app.__main__ import main

if __name__ == "__main__":
    # MUST be first: classification uses multiprocessing, and in the frozen exe
    # each worker re-launches THIS entry point. freeze_support() makes those
    # worker launches run the worker and exit, instead of re-starting the whole
    # app (which caused the "failed to extract archive" storm + stuck classify).
    multiprocessing.freeze_support()
    sys.exit(main())
