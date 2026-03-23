from __future__ import annotations
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Union

from storage.models_v2 import (
    ClinicalTrialSignalV2,
    DesignOutcomeV2,
    FacilityV2,
    InterventionV2,
    MeshTermV2,
)

ParsedDate = Union[date, str, None]

# --------------------------------
# Internal helpers
# --------------------------------

def _get(d: Dict[str, Any], path: List[str], default=None):
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur

def _parse_date(value: Optional[str]) -> ParsedDate:
    """
    Parses ClinicalTrials.gov date strings and returns:
      - date for fully specified yyyy-MM-dd or yyyy-MM-dd'T'HH:mm
      - explicit partial date for yyyy or yyyy-MM
      - None otherwise
    """
    if not value or not isinstance(value, str):
        return None
    v = value.strip()

    # Full date
    try:
        if len(v) == 10 and v[4] == "-" and v[7] == "-":
            return datetime.strptime(v, "%Y-%m-%d").date()
    except ValueError:
        pass

    # DateTimeMinutes
    try:
        if "T" in v and len(v) >= 16:
            return datetime.strptime(v[:16], "%Y-%m-%dT%H:%M").date()
    except ValueError:
        pass

    # Partial: yyyy
    if len(v) == 4 and v.isdigit():
        return v
    # Partial: yyyy-MM
    if (
        len(v) == 7
        and v[4] == "-"
        and v[:4].isdigit()
        and v[5:7].isdigit()
    ):
        return v
    return None
# --------------------------------
# Arm groups extraction
# --------------------------------
def _normalize_arm_type(value: str) -> str:
    """
    Normalize CT.gov arm group types to canonical enum form.
    Examples:
      "EXPERIMENTAL" -> "EXPERIMENTAL"
      "Experimental" -> "EXPERIMENTAL"
      "Active Comparator" -> "ACTIVE_COMPARATOR"
    """
    return value.strip().upper().replace(" ", "_")

def extract_arm_groups(study: Dict[str, Any]) -> Dict[str, str]:
    """
    Returns mapping: arm label -> arm type
    Example: {"Arm 1": "Experimental", "Arm 2": "Active Comparator"}
    """
    arm_map: Dict[str, str] = {}
    raw = _get(study, ["protocolSection", "armsInterventionsModule", "armGroups"], default=[]) or []
    if not isinstance(raw, list):
        return arm_map
    for ag in raw:
        if not isinstance(ag, dict):
            continue
        label = ag.get("label")
        arm_type = ag.get("type")
        if isinstance(label, str) and label.strip():
            if isinstance(arm_type, str):
                arm_map[label.strip()] = _normalize_arm_type(arm_type)
            else:
                arm_map[label.strip()] = ""
    return arm_map

# --------------------------------
# Intervention role assignment
# --------------------------------

def assign_intervention_role(iv: InterventionV2, arm_map: Dict[str, str]) -> str:
    """
    Assigns one of:
      - experimental_drug
      - active_control_drug
      - placebo_control
      - other
    based on arm group types.
    """

    # Build a set of arm types this intervention appears in
    roles = {arm_map.get(lbl, "") for lbl in iv.arm_group_labels}

    # If any of its arms is labeled "Experimental", treat this as the experimental drug
    if "EXPERIMENTAL" in roles:
        return "experimental_drug"

    # Otherwise, if any of its arms is labeled "Active Comparator",
    # treat it as a positive control drug
    if "ACTIVE_COMPARATOR" in roles:
        return "active_control_drug"

    # If any arm is "Placebo Comparator", treat it as placebo control
    if "PLACEBO_COMPARATOR" in roles:
        return "placebo_control"

    # Otherwise, it’s not one of those known roles
    return "other"

# --------------------------------
# Structured interventions
# --------------------------------
def extract_all_structured_interventions(
    study: Dict[str, Any],
    arm_group_map: Dict[str, str],
) -> List[InterventionV2]:
    """
    Extract ALL interventions with role tagging.
    No filtering by role or type.
    """
    raw = _get(
        study,
        ["protocolSection", "armsInterventionsModule", "interventions"],
        default=[],
    ) or []

    out: List[InterventionV2] = []

    for iv in raw:
        if not isinstance(iv, dict):
            continue

        name = iv.get("name")
        if not isinstance(name, str) or not name.strip():
            continue

        iv_type = iv.get("type")

        arm_labels = iv.get("armGroupLabels") or []
        other_names = iv.get("otherNames") or []

        candidate = InterventionV2(
            name=name.strip(),
            type=iv_type if isinstance(iv_type, str) else None,
            description=iv.get("description"),
            arm_group_labels=[lbl for lbl in arm_labels if isinstance(lbl, str)],
            other_names=[nm for nm in other_names if isinstance(nm, str)],
            role=None,
        )

        candidate.role = assign_intervention_role(candidate, arm_group_map)
        out.append(candidate)

    return out

def extract_structured_interventions(
    study: Dict[str, Any],
    arm_group_map: Dict[str, str],
) -> List[InterventionV2]:
    """
    Extracts intervention objects with role tagging.
    Only include experimental drugs.
    """
    raw = _get(
        study,
        ["protocolSection", "armsInterventionsModule", "interventions"],
        default=[],
    ) or []

    interventions: List[InterventionV2] = []
    for iv in raw:
        if not isinstance(iv, dict):
            continue

        name = iv.get("name")
        if not isinstance(name, str) or not name.strip():
            continue

        iv_type = iv.get("type")  # could be "Drug", "Biological", etc.

        arm_labels = iv.get("armGroupLabels") or []
        if not isinstance(arm_labels, list):
            arm_labels = []
        other_names = iv.get("otherNames") or []
        if not isinstance(other_names, list):
            other_names = []

        # Construct initial object (role assigned later)
        candidate = InterventionV2(
            name=name.strip(),
            type=iv_type if isinstance(iv_type, str) else None,
            description=iv.get("description"),
            arm_group_labels=[lbl for lbl in arm_labels if isinstance(lbl, str)],
            other_names=[nm for nm in other_names if isinstance(nm, str)],
            role=None,
        )

        # Assign role
        candidate.role = assign_intervention_role(candidate, arm_group_map)

        # **FILTER**: Only keep *new experimental drugs*
        # i.e., type indicates pharma AND role is "experimental_drug"
        if candidate.role == "experimental_drug" and isinstance(candidate.type, str):
            # Normalize type string check
            if candidate.type.strip().lower() in {"drug", "biological", "vaccine", "genetic"}:
                interventions.append(candidate)

    return interventions

# --------------------------------
# Fallback text names
# --------------------------------

def extract_interventions_text(study: Dict[str, Any]) -> List[str]:
    """
    Legacy list of intervention names (de-duplicated).
    Used only for debugging or optional fallback.
    """
    raw_names = []
    for iv in _get(study, ["protocolSection", "armsInterventionsModule", "interventions"], default=[]) or []:
        name = iv.get("name")
        if isinstance(name, str) and name.strip():
            raw_names.append(name.strip())

    arm_groups = _get(study, ["protocolSection", "armsInterventionsModule", "armGroups"], default=[]) or []
    for ag in arm_groups:
        if not isinstance(ag, dict):
            continue
        for n in ag.get("interventionNames") or []:
            if isinstance(n, str) and n.strip():
                raw_names.append(n.strip())

    seen = set()
    out = []
    for n in raw_names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out

# --------------------------------
# MeSH extraction (optional)
# --------------------------------

def extract_mesh_terms(study: Dict[str, Any]):
    """
    Extract MeSH terms if present.
    Not used for drug/non-drug, only for modality if needed.
    """
    meshes = _get(
        study,
        ["derivedSection", "interventionBrowseModule", "meshes"],
        default=[],
    ) or []
    ancestors = _get(
        study,
        ["derivedSection", "interventionBrowseModule", "ancestors"],
        default=[],
    ) or []

    def parse(items) -> List[MeshTermV2]:
        out_list = []
        if not isinstance(items, list):
            return out_list
        for ent in items:
            if not isinstance(ent, dict):
                continue
            term = ent.get("term")
            mid = ent.get("id")
            if isinstance(term, str) and term.strip():
                out_list.append(MeshTermV2(id=mid if isinstance(mid, str) else None, term=term.strip()))
        return out_list

    return parse(meshes), parse(ancestors)

def extract_condition_mesh_terms(study: Dict[str, Any]) -> tuple[list[MeshTermV2], list[MeshTermV2]]:
    """
    Extract condition MeSH and ancestor terms from:
      derivedSection.conditionBrowseModule
    """
    meshes = _get(
        study,
        ["derivedSection", "conditionBrowseModule", "meshes"],
        default=[],
    ) or []

    ancestors = _get(
        study,
        ["derivedSection", "conditionBrowseModule", "ancestors"],
        default=[],
    ) or []

    def parse(items) -> list[MeshTermV2]:
        out = []
        if not isinstance(items, list):
            return out
        for it in items:
            if not isinstance(it, dict):
                continue
            term = it.get("term")
            mid = it.get("id")
            if isinstance(term, str) and term.strip():
                out.append(
                    MeshTermV2(
                        id=mid if isinstance(mid, str) else None,
                        term=term.strip(),
                    )
                )
        return out

    return parse(meshes), parse(ancestors)

# --------------------------------
# Outcome measures extraction
# --------------------------------

def extract_outcomes(study: Dict[str, Any]) -> tuple[List[DesignOutcomeV2], List[DesignOutcomeV2]]:
    """
    Extract primary and secondary outcome measures from:
      protocolSection.outcomesModule.primaryOutcomes
      protocolSection.outcomesModule.secondaryOutcomes
    """
    def _parse_outcomes(items: list, outcome_type: str) -> List[DesignOutcomeV2]:
        out: List[DesignOutcomeV2] = []
        if not isinstance(items, list):
            return out
        for item in items:
            if not isinstance(item, dict):
                continue
            measure = item.get("measure")
            if not isinstance(measure, str) or not measure.strip():
                continue
            out.append(DesignOutcomeV2(
                type=outcome_type,
                measure=measure.strip(),
                time_frame=item.get("timeFrame"),
                description=item.get("description"),
            ))
        return out

    primary_raw = _get(study, ["protocolSection", "outcomesModule", "primaryOutcomes"], default=[]) or []
    secondary_raw = _get(study, ["protocolSection", "outcomesModule", "secondaryOutcomes"], default=[]) or []

    return _parse_outcomes(primary_raw, "PRIMARY"), _parse_outcomes(secondary_raw, "SECONDARY")


# --------------------------------
# Facilities extraction
# --------------------------------

def extract_facilities(study: Dict[str, Any]) -> List[FacilityV2]:
    """
    Extract study site / facility records from:
      protocolSection.contactsLocationsModule.locations
    """
    raw = _get(study, ["protocolSection", "contactsLocationsModule", "locations"], default=[]) or []
    out: List[FacilityV2] = []
    if not isinstance(raw, list):
        return out
    for loc in raw:
        if not isinstance(loc, dict):
            continue
        out.append(FacilityV2(
            name=loc.get("facility"),
            city=loc.get("city"),
            state=loc.get("state"),
            country=loc.get("country"),
            status=loc.get("status"),
        ))
    return out


# --------------------------------
# Main normalization
# --------------------------------

def normalize_clinicaltrials_study_v2(study: Dict[str, Any], skip_non_essential: bool = True) -> ClinicalTrialSignalV2:
    """
    Normalizes a CT.gov study into a V2 signal object that contains
    only new experimental drugs in `interventions`.
    
    Args:
        study: Raw JSON from ClinicalTrials.gov API
        skip_non_essential: If True, skip parsing fields not used in classification (faster)
    """
    # Identity
    nct_id = _get(study, ["protocolSection", "identificationModule", "nctId"], default="")
    if not nct_id:
        nct_id = _get(study, ["idInfo", "nctId"], default="")

    title = (
        _get(study, ["protocolSection", "identificationModule", "officialTitle"])
        or _get(study, ["protocolSection", "identificationModule", "briefTitle"])
        or ""
    )

    # Conditions
    conditions = _get(study, ["protocolSection", "conditionsModule", "conditions"], default=[]) or []
    conditions = [c for c in conditions if isinstance(c, str)]
    condition_mesh_terms, condition_mesh_ancestors = extract_condition_mesh_terms(study)

    # Metadata
    study_type = _get(study, ["protocolSection", "designModule", "studyType"])
    phase = _get(study, ["protocolSection", "designModule", "phases"])
    if isinstance(phase, list):
        phase = phase[0] if phase else None

    sponsor_class = _get(
        study,
        ["protocolSection", "sponsorCollaboratorsModule", "leadSponsor", "class"],
        default=None,
    )

    # NEW: Sponsor name
    sponsor_name = _get(
        study,
        ["protocolSection", "sponsorCollaboratorsModule", "leadSponsor", "name"],
        default=None,
    )

    # NEW: Overall status
    overall_status = _get(
        study,
        ["protocolSection", "statusModule", "overallStatus"],
        default=None,
    )

    # NEW: Enrollment
    enrollment_raw = _get(study, ["protocolSection", "designModule", "enrollmentInfo", "count"], default=None)
    enrollment = int(enrollment_raw) if enrollment_raw is not None else None
    enrollment_type = _get(study, ["protocolSection", "designModule", "enrollmentInfo", "type"], default=None)

    # NEW: Why stopped
    why_stopped = _get(study, ["protocolSection", "statusModule", "whyStopped"], default=None)

    # NEW: Key protocol dates
    start_date = _parse_date(
        _get(study, ["protocolSection", "statusModule", "startDateStruct", "date"])
    )
    completion_date = _parse_date(
        _get(study, ["protocolSection", "statusModule", "completionDateStruct", "date"])
    )
    primary_completion_date = _parse_date(
        _get(study, ["protocolSection", "statusModule", "primaryCompletionDateStruct", "date"])
    )

    # Posting dates (existing)
    first_posted_date = _parse_date(
        _get(study, ["protocolSection", "statusModule", "studyFirstPostDateStruct", "date"])
    )
    last_update_date = _parse_date(
        _get(study, ["protocolSection", "statusModule", "lastUpdatePostDateStruct", "date"])
    )

    # Arms (only parse if not skipping non-essential fields)
    if skip_non_essential:
        arm_group_map = {}  # Empty dict, not used in classification
    else:
        arm_group_map = extract_arm_groups(study)

    # Interventions — preserve ALL, then filter experimental
    all_interventions = extract_all_structured_interventions(study, arm_group_map)
    structured_interventions = extract_structured_interventions(study, arm_group_map)


    # Legacy text
    interventions_text = extract_interventions_text(study)

    # MeSH (optional)
    mesh_terms, mesh_ancestors = extract_mesh_terms(study)

    # NEW: Outcomes
    primary_outcomes, secondary_outcomes = extract_outcomes(study)

    # NEW: Facilities (always extracted — needed for sites_changed categorizer)
    facilities = extract_facilities(study)
    facility_count = len(facilities) if facilities else 0

    return ClinicalTrialSignalV2(
        nct_id=str(nct_id),
        title=str(title),
        conditions=conditions,
        study_type=study_type,
        phase=phase,
        sponsor_class=sponsor_class,

        # NEW: Status & enrollment
        overall_status=overall_status,
        enrollment=enrollment,
        enrollment_type=enrollment_type,
        why_stopped=why_stopped,

        # NEW: Sponsor identity
        sponsor_name=sponsor_name,

        # NEW: Outcomes
        primary_outcomes=primary_outcomes,
        secondary_outcomes=secondary_outcomes,

        # NEW: Facilities
        facilities=facilities,
        facility_count=facility_count,

        # NEW: Key dates
        start_date=start_date if isinstance(start_date, str) else (start_date.isoformat() if start_date else None),
        completion_date=completion_date if isinstance(completion_date, str) else (completion_date.isoformat() if completion_date else None),
        primary_completion_date=primary_completion_date if isinstance(primary_completion_date, str) else (primary_completion_date.isoformat() if primary_completion_date else None),

        # Posting dates (existing)
        first_posted_date=first_posted_date,
        last_update_posted_date=last_update_date,

        # Interventions
        interventions_all=all_interventions,
        interventions=structured_interventions,
        interventions_text=interventions_text,
        arm_group_map=arm_group_map,

        # MeSH
        intervention_meshes=mesh_terms,
        intervention_mesh_ancestors=mesh_ancestors,
        condition_meshes=condition_mesh_terms,
        condition_mesh_ancestors=condition_mesh_ancestors,
    )

