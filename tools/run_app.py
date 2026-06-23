"""Convenience launcher: double-click via ``py tools/run_app.py``.

Equivalent to ``python -m app`` with no flags. Kept intentionally tiny so
non-developers don't have to remember the module form.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make sure the repo root is on sys.path when this script is invoked directly,
# e.g. via Explorer / a desktop shortcut, not via ``python -m``.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.main import run  # noqa: E402 -- sys.path tweak must run first


if __name__ == "__main__":
    raise SystemExit(run())
