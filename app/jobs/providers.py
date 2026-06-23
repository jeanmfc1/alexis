"""Option providers for parameterized jobs (dropdowns in the GUI).

Each provider key resolves to a list of {value, label} options, newest first,
so the form can default to the most recent item.
"""

from __future__ import annotations

from pathlib import Path

from core.paths import snapshots_dir, data_root


def _file_opts(files: list[Path]) -> list[dict]:
    return [{"value": str(f), "label": f.name} for f in files]


def aact_folders() -> list[dict]:
    """Extracted AACT export folders (dirs containing studies.txt)."""
    roots = [snapshots_dir() / "active_universe", data_root() / "downloads"]
    found: list[Path] = []
    for root in roots:
        if root.is_dir():
            for p in sorted(root.iterdir()):
                if p.is_dir() and (p / "studies.txt").exists():
                    found.append(p)
    # newest-modified first
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"value": str(p), "label": p.name} for p in found]


def snapshots(kind: str) -> list[dict]:
    """JSON snapshots under snapshots_dir()/<kind>, newest first."""
    d = snapshots_dir() / kind
    if not d.is_dir():
        return []
    files = sorted(d.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    return _file_opts(files)


def resolve(provider: str) -> list[dict]:
    """Map a provider key from the catalog to its option list."""
    if provider == "aact_folders":
        return aact_folders()
    if provider.startswith("snap:"):
        return snapshots(provider.split(":", 1)[1])
    return []
