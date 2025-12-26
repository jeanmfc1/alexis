# collectors/clinicaltrials/clinicaltrials_normalize.py

from datetime import datetime
from typing import Any, Dict, List, Optional

from storage.models import ClinicalTrialSignal


def _parse_date(date_str: Optional[str]):
    if not date_str:
        return None

    # Try full date first: YYYY-MM-DD
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        pass

    # Try year-month: YYYY-MM (assume day=1)
    try:
        return datetime.strptime(date_str, "%Y-%m").date()
    except ValueError:
        return None


def _as_list(x):
    return x if isinstance(x, list) else []


def _clean_text(s: str) -> str:
    return " ".join(s.strip().split())


def _dedupe_case_insensitive(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def normalize_single_study(raw: Dict[str, Any]) -> ClinicalTrialSignal:
    # Step 1: Identify the big container where most useful fields live
    protocol = raw.get("protocolSection", {}) or {}

    # Step 2: Pull out sub-sections (modules). Each module groups a type of information.
    ident = protocol.get("identificationModule", {}) or {}
    conds = protocol.get("conditionsModule", {}) or {}
    design = protocol.get("designModule", {}) or {}
    status = protocol.get("statusModule", {}) or {}
    arms_int = protocol.get("armsInterventionsModule", {}) or {}
    sponsors = protocol.get("sponsorCollaboratorsModule", {}) or {}

    # Step 2b: Extract study type (string or None)
    study_type = design.get("studyType")
    if not isinstance(study_type, str):
        study_type = None

    # Step 3: Extract core identity
    nct_id = _clean_text(str(ident.get("nctId") or ""))
    title = _clean_text(str(ident.get("briefTitle") or ident.get("officialTitle") or ""))

    # Step 4: Extract phase
    # In v2, phases are often stored as a list like ["PHASE2"]
    phases = design.get("phases") or []
    phase = phases[0] if isinstance(phases, list) and phases else None

    # Step 5: Extract conditions (usually a list of strings)
    conditions: List[str] = []
    for c in _as_list(conds.get("conditions")):
        if isinstance(c, str) and c.strip():
            conditions.append(_clean_text(c))

    # Step 6: Extract interventions (primary + fallback) and normalize text
    interventions: List[str] = []

    # Primary: armsInterventionsModule.interventions[].name
    for item in _as_list(arms_int.get("interventions")):
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                interventions.append(_clean_text(name))

    # Fallback: armsInterventionsModule.armGroups[].interventionNames[]
    if not interventions:
        for ag in _as_list(arms_int.get("armGroups")):
            if isinstance(ag, dict):
                for nm in _as_list(ag.get("interventionNames")):
                    if isinstance(nm, str) and nm.strip():
                        interventions.append(_clean_text(nm))

    interventions = _dedupe_case_insensitive(interventions)

    # Step 7: Extract dates and status
    start_date = _parse_date((status.get("startDateStruct") or {}).get("date"))
    last_update_date = _parse_date((status.get("lastUpdatePostDateStruct") or {}).get("date"))
    overall_status = status.get("overallStatus")

    # Step 8: Sponsor class (coarse)
    sponsor_type = (sponsors.get("leadSponsor") or {}).get("class")

    # Step 9: Create the internal object
    # Note: therapeutic_area and modality remain None for now (classifier fills later)
    return ClinicalTrialSignal(
        nct_id=nct_id,
        title=title,
        phase=phase,
        conditions=conditions,
        interventions=interventions,
        start_date=start_date,
        last_update_date=last_update_date,
        status=overall_status,
        therapeutic_area=None,
        modality=None,
        sponsor_type=sponsor_type,
        study_type=study_type,
    )


def normalize_studies(raw_studies: List[Dict[str, Any]]) -> List[ClinicalTrialSignal]:
    """
    Convert a list of raw studies into a list of ClinicalTrialSignal objects.
    Skip records missing an NCT ID.
    """
    out: List[ClinicalTrialSignal] = []

    for raw in raw_studies:
        trial = normalize_single_study(raw)
        if trial.nct_id:
            out.append(trial)

    return out
