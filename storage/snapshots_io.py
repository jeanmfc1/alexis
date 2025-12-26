# storage/snapshots_io.py

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from storage.models import ClinicalTrialSignal


@dataclass(frozen=True)
class SnapshotMetadata:
    source: str                 # e.g. "clinicaltrials.gov"
    window_basis: str           # e.g. "LastUpdatePostDate"
    as_of: date
    window_start: date
    window_end: date
    condition_query: Optional[str] = None
    page_size: Optional[int] = None
    max_studies: Optional[int] = None


def _date_to_str(d: date) -> str:
    return d.isoformat()


def _trial_to_dict(t: ClinicalTrialSignal) -> Dict[str, Any]:
    # Keep this explicit and stable (avoid dumping __dict__ blindly)
    return {
        "nct_id": t.nct_id,
        "title": t.title,
        "phase": t.phase,
        "conditions": t.conditions,
        "interventions": t.interventions,
        "start_date": t.start_date.isoformat() if t.start_date else None,
        "last_update_date": t.last_update_date.isoformat() if t.last_update_date else None,
        "status": t.status,
        "sponsor_type": t.sponsor_type,
        "study_type": getattr(t, "study_type", None),
        "therapeutic_area": t.therapeutic_area,
        "modality": t.modality,
    }


def save_trial_snapshot(
    base_dir: str,
    basis_folder: str,
    metadata: SnapshotMetadata,
    trials: List[ClinicalTrialSignal],
    summary: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Writes a JSON snapshot to:
      {base_dir}/{basis_folder}/{as_of}T{HH-MM-SS}.json

    If summary is provided, it is written under payload["summary"].
    """
    out_dir = Path(base_dir) / basis_folder
    out_dir.mkdir(parents=True, exist_ok=True)

    run_ts = datetime.now().strftime("%H-%M-%S")
    path = out_dir / f"{_date_to_str(metadata.as_of)}T{run_ts}.json"

    payload: Dict[str, Any] = {
        "metadata": {
            "source": metadata.source,
            "window_basis": metadata.window_basis,
            "as_of": _date_to_str(metadata.as_of),
            "window_start": _date_to_str(metadata.window_start),
            "window_end": _date_to_str(metadata.window_end),
            "window_days": (metadata.window_end - metadata.window_start).days,
            "condition_query": metadata.condition_query,
            "page_size": metadata.page_size,
            "max_studies": metadata.max_studies,
            "run_time": datetime.now().isoformat(timespec="seconds"),
            "run_id": f"{_date_to_str(metadata.as_of)}T{run_ts}",
        },
        "trials": [_trial_to_dict(t) for t in trials],
    }

    if summary is not None:
        payload["summary"] = summary

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)

    return path


def load_trial_snapshot(path: str) -> Dict[str, Any]:
    """
    Loads snapshot JSON. For now returns dict; later you can rehydrate into objects if needed.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
