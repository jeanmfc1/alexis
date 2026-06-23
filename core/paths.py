"""Single source of truth for every ALEXIS filesystem path.

Two distinct roots:

* ``app_root()``  — bundled, read-only application assets (code, MeSH JSON,
  classifier models, viz template/components). In a PyInstaller one-folder
  freeze this is ``sys._MEIPASS``; in a source checkout it is the repo root.
* ``data_root()`` — the user's large, mutable data tree (``storage/snapshots``,
  ``storage/changelogs``, logs, scrape checkpoints). Resolved from, in order:
  the ``ALEXIS_HOME`` env var, the ``data_dir`` key in ``alexis_config.json``,
  then a sensible default (the repo in source mode, ``%LOCALAPPDATA%\\ALEXIS``
  when frozen).

Every module should import the accessors here instead of building paths from
``Path(__file__)`` or hardcoded strings, so the app is portable across the
WSL dev box, native Windows, and the packaged executable.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "ALEXIS"
_CONFIG_FILENAME = "alexis_config.json"


# ---------------------------------------------------------------------------
# Roots
# ---------------------------------------------------------------------------
def is_frozen() -> bool:
    """True when running inside a PyInstaller (or similar) frozen bundle."""
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """Root of bundled, read-only assets.

    Frozen  -> the PyInstaller extraction dir (``sys._MEIPASS``).
    Source  -> the repository root (parent of the ``core`` package).
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _config_dir() -> Path:
    """Folder where ``alexis_config.json`` lives.

    Frozen  -> ``%LOCALAPPDATA%\\ALEXIS`` (user-writable; the .exe may live
               under ``C:\\Program Files`` which is read-only without admin).
    Source  -> the repo root.
    """
    if is_frozen():
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return Path(base) / APP_NAME if base else Path.home() / APP_NAME
    return app_root()


def _config_path() -> Path:
    """Path to ``alexis_config.json`` (private; prefer :func:`config_path`)."""
    return _config_dir() / _CONFIG_FILENAME


def config_path() -> Path:
    """Public accessor for the alexis_config.json path."""
    return _config_path()


def _configured_data_dir() -> Path | None:
    cfg = _config_path()
    if not cfg.exists():
        return None
    try:
        d = json.loads(cfg.read_text(encoding="utf-8")).get("data_dir")
    except (json.JSONDecodeError, OSError):
        return None
    if not d:
        return None
    p = Path(d).expanduser()
    return p if p.exists() else None


def _default_data_dir() -> Path:
    # Source checkout: the data already sits inside the repo (storage/...).
    if not is_frozen():
        return app_root()
    # Frozen app: a per-user writable location.
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    return Path(base) / APP_NAME if base else Path.home() / APP_NAME


def data_root() -> Path:
    """Root of the user's mutable data tree (the folder containing ``storage``)."""
    env = os.environ.get("ALEXIS_HOME")
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return p
    configured = _configured_data_dir()
    if configured is not None:
        return configured
    return _default_data_dir()


def set_data_dir(path: str | os.PathLike) -> Path:
    """Persist the user-selected data directory to ``alexis_config.json``.

    Ensures the config directory exists before writing (matters on a fresh
    frozen install where ``%LOCALAPPDATA%\\ALEXIS`` may not yet exist).
    """
    p = Path(path).expanduser()
    cfg = _config_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {}
    if cfg.exists():
        try:
            payload = json.loads(cfg.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
    payload["data_dir"] = str(p)
    cfg.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def data_dir_is_valid(path: str | os.PathLike | None = None) -> bool:
    """A data dir is usable if it contains a ``storage`` folder."""
    root = Path(path).expanduser() if path is not None else data_root()
    return (root / "storage").is_dir()


# ---------------------------------------------------------------------------
# Mutable data locations (under data_root)
# ---------------------------------------------------------------------------
def storage_dir() -> Path:
    return data_root() / "storage"


def snapshots_dir() -> Path:
    return storage_dir() / "snapshots" / "clinical_trials_v2"


def changelogs_dir() -> Path:
    return storage_dir() / "changelogs"


def raw_weekly_dir() -> Path:
    """Raw ClinicalTrials.gov weekly pulls (was hardcoded to /home/jeanmfc/...)."""
    return storage_dir() / "raw" / "ctgov" / "weekly"


def downloads_dir() -> Path:
    """Drop folder watched for AACT export zips (was hardcoded to a Windows path)."""
    return data_root() / "downloads"


def logs_dir() -> Path:
    return data_root() / "logs"


# ---------------------------------------------------------------------------
# Bundled, read-only assets (under app_root — ship with the app)
# ---------------------------------------------------------------------------
def mesh_dir() -> Path:
    return app_root() / "storage" / "mesh"


def models_dir() -> Path:
    return app_root() / "classifiers"


def viz_dir() -> Path:
    return app_root() / "viz"


def policy_dir() -> Path:
    return app_root() / "policy"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def normalize_user_path(p: str | os.PathLike) -> Path:
    """Absorb a WSL ``/mnt/<drive>/...`` path into ``<DRIVE>:/...`` on Windows.

    Only applied at user-input boundaries (folder pickers, CLI args); internal
    code uses ``pathlib`` directly.
    """
    s = str(p)
    if sys.platform == "win32" and s.startswith("/mnt/") and len(s) > 6 and s[6] == "/":
        drive = s[5].upper()
        return Path(f"{drive}:/{s[7:]}")
    return Path(s)


def ensure_dir(path: Path) -> Path:
    """Create ``path`` (and parents) if missing; return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path
