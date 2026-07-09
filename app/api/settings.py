"""GET/POST /api/settings, GET /api/info, GET /api/health.

All path computation goes through ``core.paths``. The data dir is
validated by ``paths.data_dir_is_valid`` (checks for a ``storage`` child
folder) before being persisted via ``paths.set_data_dir``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core import paths
from core.version import __version__ as _VERSION


router = APIRouter()
_log = logging.getLogger("alexis.api.settings")


def _settings_snapshot() -> dict:
    """Build the GET /api/settings response payload."""
    data_dir = paths.data_root()
    return {
        "data_dir":         str(data_dir),
        "is_valid":         bool(paths.data_dir_is_valid(data_dir)),
        "has_data":         bool(paths.data_dir_has_data(data_dir)),
        "is_frozen":        bool(paths.is_frozen()),
        "app_root":         str(paths.app_root()),
        "default_data_dir": str(paths.data_root()),
        "config_path":      str(paths.config_path()),
    }


def _validate_data_dir(raw: str) -> Path:
    """Normalise + harden a user-supplied data-dir path.

    Raises ``HTTPException(400)`` with a clear message if the path is not
    safe to persist. Returns the canonical absolute path on success.
    """
    try:
        candidate = paths.normalize_user_path(raw).expanduser()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid path: {exc}")

    if not candidate.is_absolute():
        raise HTTPException(
            status_code=400,
            detail="data_dir must be an absolute path (e.g. C:\\Users\\me\\ALEXIS)",
        )

    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError:
        raise HTTPException(
            status_code=400,
            detail=f"folder does not exist: {candidate}",
        )
    except OSError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"cannot resolve folder: {exc}",
        )

    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="path is not a directory")

    # Reject drive roots and one-component paths: those are almost always
    # a mistake (e.g. user typed "C:\" which technically contains a
    # storage subfolder somewhere underneath).
    if len(resolved.parts) <= 1 or resolved == resolved.parent:
        raise HTTPException(
            status_code=400,
            detail="refusing to use a drive root as the data folder",
        )

    # Any existing, writable folder is acceptable -- a brand-new empty folder is
    # fine; set_data_dir() creates the storage structure inside it.
    if not paths.data_dir_is_valid(resolved):
        raise HTTPException(status_code=400, detail="path is not a usable folder")
    return resolved


@router.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": _VERSION}


@router.get("/api/settings")
def get_settings() -> dict:
    try:
        return _settings_snapshot()
    except Exception as exc:  # noqa: BLE001
        _log.exception("[err] get_settings failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"settings error: {type(exc).__name__}",
        )


@router.post("/api/settings")
def set_settings(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")

    raw = payload.get("data_dir")
    if not raw or not str(raw).strip():
        raise HTTPException(status_code=400, detail="data_dir is required")

    resolved = _validate_data_dir(str(raw).strip())

    try:
        paths.set_data_dir(resolved)
    except PermissionError as exc:
        _log.exception("[err] set_data_dir permission denied: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=(
                "could not persist data_dir: permission denied writing config "
                f"to {paths.config_path()}"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        _log.exception("[err] set_data_dir failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"could not persist data_dir: {type(exc).__name__}",
        )

    snapshot = _settings_snapshot()
    snapshot["ok"] = True
    return snapshot


@router.post("/api/browse_folder")
def browse_folder() -> dict:
    """Open a native folder picker in the desktop window; return the chosen path.

    Only works when running as the desktop app (a window exists). In headless
    mode there's no window -> the UI falls back to typing a path.
    """
    try:
        from app.main import get_window
        import webview  # type: ignore
    except Exception:  # noqa: BLE001
        return {"path": None, "available": False}
    win = get_window()
    if win is None:
        return {"path": None, "available": False}
    try:
        result = win.create_file_dialog(webview.FOLDER_DIALOG)
    except Exception as exc:  # noqa: BLE001
        _log.exception("[err] folder dialog failed: %s", exc)
        return {"path": None, "available": True, "error": str(exc)}
    if not result:
        return {"path": None, "available": True}   # user cancelled
    path = result[0] if isinstance(result, (list, tuple)) else str(result)
    return {"path": str(path), "available": True}


@router.get("/api/info")
def info() -> dict:
    try:
        return {
            "version":      _VERSION,
            "python":       sys.version.split()[0],
            "platform":     sys.platform,
            "is_frozen":    bool(paths.is_frozen()),
            "app_root":     str(paths.app_root()),
            "data_root":    str(paths.data_root()),
            "viz_dir":      str(paths.viz_dir()),
            "storage_dir":  str(paths.storage_dir()),
            "config_path":  str(paths.config_path()),
        }
    except Exception as exc:  # noqa: BLE001
        _log.exception("[err] info failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"info error: {type(exc).__name__}",
        )
