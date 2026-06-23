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


router = APIRouter()
_log = logging.getLogger("alexis.api.settings")


_VERSION = "0.1.0-mvp"


def _settings_snapshot() -> dict:
    """Build the GET /api/settings response payload."""
    data_dir = paths.data_root()
    return {
        "data_dir":         str(data_dir),
        "is_valid":         bool(paths.data_dir_is_valid(data_dir)),
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

    if not paths.data_dir_is_valid(resolved):
        raise HTTPException(
            status_code=400,
            detail=(
                "selected folder is not a valid ALEXIS data directory "
                "(must contain a 'storage' subfolder)"
            ),
        )
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
