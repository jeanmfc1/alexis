"""POST /api/classify_trial.

Sync handler (FastAPI runs it in a threadpool) so heavy classifier work
never blocks the event loop. All errors flow through the global exception
handler in ``app.server`` so stack traces never leak to the client.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.services.classifier_service import classify_one


router = APIRouter()
_log = logging.getLogger("alexis.api.classify")


@router.post("/api/classify_trial")
def classify_trial(request: Request, payload: dict) -> dict:  # noqa: ARG001
    try:
        return classify_one(payload)
    except HTTPException:
        # Validation errors propagate as-is (FastAPI renders them).
        raise
    except Exception as exc:  # noqa: BLE001
        _log.exception("[err] classify_trial failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"classifier error: {type(exc).__name__}",
        )
