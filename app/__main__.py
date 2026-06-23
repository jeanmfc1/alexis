"""``python -m app`` entrypoint.

Parses a minimal CLI and delegates to ``app.main.run``. Exit code is the
return value of ``run``.
"""

from __future__ import annotations

import argparse
import sys

from app.main import run


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
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    return run(dev=args.dev, headless=args.headless, port=args.port)


if __name__ == "__main__":
    raise SystemExit(main())
