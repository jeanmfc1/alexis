from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from storage.models_v2 import ClinicalTrialSignalV2, InterventionV2, MeshTermV2


@dataclass(frozen=True)
class SnapshotMetadataV2:
    # Same idea as v01 SnapshotMetadata, but explicitly v2 to avoid confusion.
    source: str
    window_basis: str
    as_of: date
    window_start: date
    window_end: date
    condition_query: Optional[str] = None
    page_size: Optional[int] = None
    max_studies: Optional[int] = None


def _date_to_str(d: date) -> str:
    return d.isoformat()


def _mesh_term_to_dict(m: MeshTermV2) -> Dict[str, Any]:
    return {
        "id": m.id,
        "term": m.term,
    }


def _intervention_to_dict(iv: InterventionV2) -> Dict[str, Any]:
    return {
        "name": iv.name,
        "type": iv.type,
        "role": iv.role,
        "arm_group_labels": list(iv.arm_group_labels or []),
        "other_names": list(iv.other_names or []),
        "description": iv.description,
    }


def _trial_to_dict(t: ClinicalTrialSignalV2) -> Dict[str, Any]:
    # Keep explicit and stable (avoid dumping __dict__ blindly), like v01.
    return {
        "nct_id": t.nct_id,
        "title": t.title,
        "study_type": t.study_type,
        "phase": t.phase,
        "sponsor_class": t.sponsor_class,
        "conditions": list(t.conditions or []),

        # v2 dates are Union[date,str,None] (see models_v2)
        "first_posted_date": t.first_posted_date.isoformat() if hasattr(t.first_posted_date, "isoformat") else t.first_posted_date,
        "last_update_posted_date": t.last_update_posted_date.isoformat() if hasattr(t.last_update_posted_date, "isoformat") else t.last_update_posted_date,

        # structured interventions (only experimental drugs after normalize_v2)
        "interventions": [_intervention_to_dict(iv) for iv in (t.interventions or [])],
        "interventions_text": list(t.interventions_text or []),
        "arm_group_map": dict(t.arm_group_map or {}),

        # meshes
        "intervention_meshes": [_mesh_term_to_dict(m) for m in (t.intervention_meshes or [])],
        "intervention_mesh_ancestors": [_mesh_term_to_dict(m) for m in (t.intervention_mesh_ancestors or [])],
        "condition_meshes": [_mesh_term_to_dict(m) for m in (t.condition_meshes or [])],
        "condition_mesh_ancestors": [_mesh_term_to_dict(m) for m in (t.condition_mesh_ancestors or [])],

        # classification outputs (set by pipeline)
        "therapeutic_area": getattr(t, "therapeutic_area", None),
        "is_drug_trial": getattr(t, "is_drug_trial", None),
        "modality": getattr(t, "modality", None),

        # INFO flags (v2)
        "info_flags": list(getattr(t, "info_flags", []) or []),
    }


def save_trial_snapshot_v2(
    base_dir: str,
    basis_folder: str,
    metadata: SnapshotMetadataV2,
    trials: List[ClinicalTrialSignalV2],
    summary: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Writes a V2 JSON snapshot to:
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
            "format": "ALEXIS_SNAPSHOT_V2",
        },
        "trials": [_trial_to_dict(t) for t in trials],
    }

    if summary is not None:
        payload["summary"] = summary

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)

    return path
