from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from storage.models_v2 import (
    ClinicalTrialSignalV2,
    DesignOutcomeV2,
    FacilityV2,
    InterventionV2,
    LinkedTrialV2,
    MeshTermV2,
    OutcomeAssessmentV2,
    UpdateCategoryV2,
)

from datetime import date

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
    reclassified_from: Optional[str] = None

def _ensure_date(d):
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        return date.fromisoformat(d)
    return None 

def _date_to_str(d) -> str:
    if d is None:
        return None
    if isinstance(d, str):
        return d
    return d.isoformat()

def _mesh_term_to_dict(m: MeshTermV2) -> Dict[str, Any]:
    return {
        "id": m.id,
        "term": m.term,
    }

def _outcome_to_dict(o: DesignOutcomeV2) -> Dict[str, Any]:
    return {
        "type": o.type,
        "measure": o.measure,
        "time_frame": o.time_frame,
        "description": o.description,
    }

def _facility_to_dict(f: FacilityV2) -> Dict[str, Any]:
    return {
        "name": f.name,
        "city": f.city,
        "state": f.state,
        "country": f.country,
        "status": f.status,
    }

def _update_category_to_dict(uc: UpdateCategoryV2) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "category": uc.category,
        "tier": uc.tier,
    }
    if uc.direction is not None:
        d["direction"] = uc.direction
    if uc.field_name is not None:
        d["field_name"] = uc.field_name
    if uc.old_value is not None:
        d["old_value"] = uc.old_value
    if uc.new_value is not None:
        d["new_value"] = uc.new_value
    if uc.delta is not None:
        d["delta"] = uc.delta
    if uc.delta_pct is not None:
        d["delta_pct"] = uc.delta_pct
    if uc.note is not None:
        d["note"] = uc.note
    return d

def _linked_trial_to_dict(lt: LinkedTrialV2) -> Dict[str, Any]:
    return {
        "nct_id": lt.nct_id,
        "phase": lt.phase,
        "link_confidence": lt.link_confidence,
        "link_type": lt.link_type,
    }

def _outcome_assessment_to_dict(oa: OutcomeAssessmentV2) -> Dict[str, Any]:
    return {
        "assessment": oa.assessment,
        "confidence": oa.confidence,
        "signals": list(oa.signals or []),
        "assessed_at": oa.assessed_at,
    }

def _week_of_month(d: date) -> int:
    """
    Week-of-month index with Monday as week start.
    w1 is the week that contains the 1st of the month.
    """
    first = d.replace(day=1)
    first_week_start = first - timedelta(days=first.weekday())  # Monday
    this_week_start = d - timedelta(days=d.weekday())          # Monday
    return 1 + ((this_week_start - first_week_start).days // 7)

def _snapshot_week_label(d: date) -> str:
    """
    Returns: YYYY_mon_wN where N restarts each month.
    Example: 2026_feb_w2
    """
    month = d.strftime("%b").lower()
    wom = _week_of_month(d)
    return f"{d.year}_{month}_w{wom}"

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

        # Status & enrollment (new)
        "overall_status": t.overall_status,
        "enrollment": t.enrollment,
        "enrollment_type": t.enrollment_type,
        "why_stopped": t.why_stopped,

        # Sponsor identity (new)
        "sponsor_name": t.sponsor_name,

        # Key protocol dates (new)
        "start_date": t.start_date,
        "completion_date": t.completion_date,
        "primary_completion_date": t.primary_completion_date,

        # v2 posting dates are Union[date,str,None] (see models_v2)
        "first_posted_date": t.first_posted_date.isoformat() if hasattr(t.first_posted_date, "isoformat") else t.first_posted_date,
        "last_update_posted_date": t.last_update_posted_date.isoformat() if hasattr(t.last_update_posted_date, "isoformat") else t.last_update_posted_date,

        # Outcomes (new)
        "primary_outcomes": [_outcome_to_dict(o) for o in (t.primary_outcomes or [])],
        "secondary_outcomes": [_outcome_to_dict(o) for o in (t.secondary_outcomes or [])],

        # Facilities (new)
        "facilities": [_facility_to_dict(f) for f in (t.facilities or [])],
        "facility_count": t.facility_count,

        # structured interventions (only experimental drugs after normalize_v2)
        "interventions": [_intervention_to_dict(iv) for iv in (t.interventions or [])],
        "interventions_text": list(t.interventions_text or []),
        "interventions_all": [_intervention_to_dict(iv) for iv in (t.interventions_all or [])],

        "arm_group_map": dict(t.arm_group_map or {}),

        # meshes
        "intervention_meshes": [_mesh_term_to_dict(m) for m in (t.intervention_meshes or [])],
        "intervention_mesh_ancestors": [_mesh_term_to_dict(m) for m in (t.intervention_mesh_ancestors or [])],
        "condition_meshes": [_mesh_term_to_dict(m) for m in (t.condition_meshes or [])],
        "condition_mesh_ancestors": [_mesh_term_to_dict(m) for m in (t.condition_mesh_ancestors or [])],

        # classification outputs (set by pipeline)
        "therapeutic_area": t.therapeutic_area,
        "is_drug_trial": t.is_drug_trial,
        "modality": t.modality,
        "modality_source": t.modality_source,
        "therapeutic_area_source": t.therapeutic_area_source,
        "therapeutic_areas_detected": list(t.therapeutic_areas_detected or []),

        # INFO flags (v2)
        "info_flags": list(t.info_flags or []),

        "study_intent": t.study_intent,
        "study_category": t.study_category,
        "study_category_evidence": list(t.study_category_evidence or []),
        "mesh_missing_condition": t.mesh_missing_condition,

        # Update categorization outputs (new)
        "update_type": t.update_type,
        "update_categories": [_update_category_to_dict(uc) for uc in (t.update_categories or [])],
        "linked_from": _linked_trial_to_dict(t.linked_from) if t.linked_from else None,
        "outcome": _outcome_assessment_to_dict(t.outcome) if t.outcome else None,
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

    label = _snapshot_week_label(metadata.as_of)

    if basis_folder == "reclassified":
        filename = f"reclassified_{label}.json"
    else:
        filename = f"{label}.json"

    path = out_dir / filename


    start = _ensure_date(metadata.window_start)
    end = _ensure_date(metadata.window_end)

    payload: Dict[str, Any] = {
        "metadata": {
            "source": metadata.source,
            "window_basis": metadata.window_basis,
            "as_of": _date_to_str(metadata.as_of),
            "window_start": _date_to_str(metadata.window_start),
            "window_end": _date_to_str(metadata.window_end),
            "window_days": (end - start).days if start and end else None,
            "condition_query": metadata.condition_query,
            "page_size": metadata.page_size,
            "max_studies": metadata.max_studies,
            "run_time": datetime.now().isoformat(timespec="seconds"),
            "run_id": _snapshot_week_label(metadata.as_of),
            "format": "ALEXIS_SNAPSHOT_V2",
        },
        "trials": [_trial_to_dict(t) for t in trials],
    }

    if summary is not None:
        payload["summary"] = summary

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)

    return path
