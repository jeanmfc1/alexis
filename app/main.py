"""ALEXIS desktop app entrypoint.

Boots an in-process FastAPI server on 127.0.0.1 (uvicorn in a daemon thread)
and opens a pywebview window that points at it. Designed to work identically
under ``python -m app`` (source checkout) and a future PyInstaller freeze
(``sys.frozen`` / ``sys._MEIPASS``-aware via ``core.paths``).

Public surface:
    run(*, dev=False, headless=False, port=None) -> int
"""

from __future__ import annotations

import contextlib
import logging
import socket
import sys
import time
from threading import Thread

from core.paths import is_frozen


_LOG = logging.getLogger("alexis.app")
_LOGGING_CONFIGURED = False

# Window defaults (kept here so __main__ and tools/run_app.py stay thin).
_WINDOW_TITLE = "ALEXIS"
_WINDOW_WIDTH = 1400
_WINDOW_HEIGHT = 900
_WINDOW_MIN_SIZE = (1100, 720)
_WINDOW_BG = "#07090F"

# How long we wait for uvicorn to flip server.started True.
_SERVER_START_TIMEOUT_S = 10.0
_SERVER_POLL_INTERVAL_S = 0.05
# How long we give uvicorn to drain after the window closes.
_SERVER_SHUTDOWN_TIMEOUT_S = 5.0


def ensure_streams() -> None:
    """Guarantee usable sys.stdout/sys.stderr.

    A windowed PyInstaller build sets both to None, which would crash any
    print()/logging. Reattach the inherited OS handles (fd 1/2) when present
    -- this is what lets a --run-pipeline child write to the log file its
    parent handed it -- and fall back to logs/app.log otherwise.
    """
    import io
    import os
    for name, fd in (("stdout", 1), ("stderr", 2)):
        existing = getattr(sys, name, None)
        if existing is not None:
            # Stream exists (e.g. a redirected pipe in a windowed exe) but may be
            # cp1252 -- force utf-8 so pipeline output containing unicode (e.g.
            # "2026-06-22 -> ...", box-drawing chars) does not crash with a
            # UnicodeEncodeError. PYTHONIOENCODING is not honoured for these
            # auto-created windowed streams, so reconfigure explicitly.
            try:
                existing.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 -- not all streams support it
                pass
            continue
        stream = None
        try:
            stream = os.fdopen(fd, "w", encoding="utf-8", buffering=1)
        except (OSError, ValueError):
            try:
                from core.paths import logs_dir, ensure_dir
                ensure_dir(logs_dir())
                stream = open(logs_dir() / "app.log", "a",
                              encoding="utf-8", buffering=1)
            except Exception:  # noqa: BLE001
                stream = io.StringIO()
        setattr(sys, name, stream)


def _configure_logging() -> None:
    """Configure root logging exactly once, on first call to run()."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return
    ensure_streams()
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    try:
        from core.paths import logs_dir, ensure_dir
        ensure_dir(logs_dir())
        handlers.append(logging.FileHandler(logs_dir() / "app.log", encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- logging must never crash startup
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    _LOGGING_CONFIGURED = True


def _find_free_port() -> int:
    """Ask the OS for an ephemeral free port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _build_uvicorn_server(app, port: int):
    """Construct a uvicorn.Server with the project-standard config.

    Subclasses ``uvicorn.Server`` to no-op ``capture_signals`` because we
    drive the server from a daemon thread. The default implementation calls
    ``signal.signal()``, which raises "signal only works in main thread of
    the main interpreter" when invoked off the main thread; the asyncio
    loop swallows the exception into a task and ``server.started`` never
    flips True (the start timeout then fires with a misleading error).
    Shutdown is driven by us setting ``server.should_exit = True``.
    """
    import uvicorn  # local import so module import stays side-effect free

    class _NoSignalsServer(uvicorn.Server):
        # capture_signals is a context manager in uvicorn >=0.30; return a
        # null context so uvicorn's `with self.capture_signals():` works.
        def capture_signals(self):  # type: ignore[override]
            return contextlib.nullcontext()

    cfg = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        loop="asyncio",
        http="h11",
        log_level="warning",
        access_log=False,
    )
    return _NoSignalsServer(cfg)


def _wait_until_started(server, timeout_s: float) -> bool:
    """Poll server.started until True or timeout. Returns True on success."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if getattr(server, "started", False):
            return True
        time.sleep(_SERVER_POLL_INTERVAL_S)
    return bool(getattr(server, "started", False))


def _block_for_keyboard_interrupt(url: str) -> int:
    """Headless mode: print URL and wait until the user hits Ctrl+C."""
    print("[info] ALEXIS server listening at " + url)
    print("[info] Headless mode -- open the URL in your browser.")
    print("[info] Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("[info] KeyboardInterrupt -- shutting down.")
        return 0


# Reference to the live pywebview window, so the API can open native dialogs
# (folder picker). None in headless mode.
_WINDOW = None


def get_window():
    """Return the live pywebview window (or None in headless mode)."""
    return _WINDOW


def _open_window(url: str) -> int:
    """Open the pywebview window. Blocks until the user closes it.

    Returns 0 on clean exit, 1 if pywebview is unavailable.
    """
    global _WINDOW
    try:
        import webview  # type: ignore
    except ImportError:
        print("[err] pywebview not installed. Run: pip install pywebview")
        return 1

    _WINDOW = webview.create_window(
        _WINDOW_TITLE,
        url=url,
        width=_WINDOW_WIDTH,
        height=_WINDOW_HEIGHT,
        min_size=_WINDOW_MIN_SIZE,
        background_color=_WINDOW_BG,
    )
    # Do NOT pin a gui backend -- on Windows pywebview picks Edge WebView2,
    # which is what we want.
    webview.start()
    return 0


def run(*, dev: bool = False, headless: bool = False, port: int | None = None) -> int:
    """Boot the in-process server and (unless headless) open the desktop window.

    Parameters
    ----------
    dev:
        Reserved for future dev-only conveniences (e.g. extra logging). The
        server config is identical either way for now.
    headless:
        If True, skip pywebview and just keep the server alive. Useful for
        smoke-testing in a regular browser.
    port:
        Explicit port to bind. ``None`` (default) asks the OS for a free one.

    Returns
    -------
    int
        Process exit code (0 = clean, 1 = error).
    """
    _configure_logging()

    if dev:
        _LOG.setLevel(logging.DEBUG)
        _LOG.debug("[info] dev mode flags enabled")

    # Resolve port early so logs are accurate.
    chosen_port = int(port) if port else _find_free_port()
    url = "http://127.0.0.1:" + str(chosen_port) + "/"

    # Build the FastAPI app via the server factory.
    try:
        from app.server import create_app
    except ImportError as e:
        _LOG.error("[err] could not import app.server.create_app: %s", e)
        print("[err] could not import app.server.create_app: " + str(e))
        return 1

    try:
        fastapi_app = create_app()
    except Exception as e:  # noqa: BLE001 -- top-level boundary
        _LOG.exception("[err] create_app() failed")
        print("[err] create_app() failed: " + str(e))
        return 1

    server = _build_uvicorn_server(fastapi_app, chosen_port)

    thread = Thread(target=server.run, name="alexis-uvicorn", daemon=True)
    thread.start()
    _LOG.info("[info] uvicorn starting on %s (frozen=%s)", url, is_frozen())

    if not _wait_until_started(server, _SERVER_START_TIMEOUT_S):
        _LOG.error("[err] server failed to start within %.1fs", _SERVER_START_TIMEOUT_S)
        print("[err] server failed to start within " + str(_SERVER_START_TIMEOUT_S) + "s")
        server.should_exit = True
        thread.join(timeout=_SERVER_SHUTDOWN_TIMEOUT_S)
        return 1

    _LOG.info("[ok] server ready at %s", url)

    exit_code = 0
    try:
        if headless:
            exit_code = _block_for_keyboard_interrupt(url)
        else:
            exit_code = _open_window(url)
    except Exception as e:  # noqa: BLE001 -- top-level boundary
        _LOG.exception("[err] UI loop crashed")
        print("[err] UI loop crashed: " + str(e))
        exit_code = 1
    finally:
        _LOG.info("[info] shutting down server")
        server.should_exit = True
        thread.join(timeout=_SERVER_SHUTDOWN_TIMEOUT_S)
        if thread.is_alive():
            _LOG.warning("[warn] uvicorn thread did not exit cleanly")

    return exit_code


__all__ = ["run"]
