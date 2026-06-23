"""GET /api/dashboards.

Lists the canonical Weekly / Quarterly / Full dashboard HTML files that
live under ``paths.viz_dir()``. Only files that actually exist on disk
are returned, sorted in a stable display order.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from core.paths import viz_dir


router = APIRouter()
_log = logging.getLogger("alexis.api.dashboards")


# Filename -> {id, title}. Order in this dict drives sort order.
_DASHBOARD_MAP: list[tuple[str, dict[str, str]]] = [
    ("alexis_weekly_dashboard_live.html",    {"id": "weekly",    "title": "Weekly"}),
    ("alexis_quarterly_dashboard_live.html", {"id": "quarterly", "title": "Quarterly"}),
    ("alexis_dashboard_live.html",           {"id": "unified",   "title": "Full"}),
]


@router.get("/api/dashboards")
def list_dashboards() -> dict:
    try:
        root = viz_dir()
        available = []
        for filename, meta in _DASHBOARD_MAP:
            fp = root / filename
            if not fp.exists() or not fp.is_file():
                continue
            try:
                size = fp.stat().st_size
            except OSError:
                size = 0
            available.append({
                "id":         meta["id"],
                "filename":   filename,
                "title":      meta["title"],
                "exists":     True,
                "size_bytes": int(size),
                "url":        f"/dashboards/{filename}",
            })
        return {
            "available": available,
            "viz_dir":   str(root),
        }
    except Exception as exc:  # noqa: BLE001
        _log.exception("[err] list_dashboards failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"dashboard listing error: {type(exc).__name__}",
        )
