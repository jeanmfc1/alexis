"""
build_master_from_aact.py
─────────────────────────
Reads an AACT monthly export (pipe-delimited flat files) and builds a
complete master_DB JSON file containing all classified drug trials.

Edit the CONFIGURATION block at the top of main(), then:
  python build_master_from_aact.py

Auto-resumes from checkpoint if the process was interrupted.
Set FRESH_START = True to ignore checkpoints and start over.

AACT tables used:
  studies.txt              → core identity, status, enrollment, dates
  sponsors.txt             → sponsor_name, sponsor_class (agency_class)
  conditions.txt           → conditions list
  interventions.txt        → interventions_text, interventions_all
  design_outcomes.txt      → primary_outcomes, secondary_outcomes
  facilities.txt           → facilities, facility_count
  browse_conditions.txt    → condition_meshes, condition_mesh_ancestors
  browse_interventions.txt → intervention_meshes, intervention_mesh_ancestors

Optional (for arm group roles):
  design_groups.txt              → arm_group_map

Optional (narrative text):
  brief_summaries.txt            → brief_summary
  detailed_descriptions.txt      → detailed_description
  eligibilities.txt              -> eligibility_criteria
"""

from __future__ import annotations

import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── ALEXIS imports (must be on sys.path) ────────────────────────────────
from storage.models_v2 import ClinicalTrialSignalV2, DesignOutcomeV2, FacilityV2, InterventionV2, MeshTermV2
from pipelines.weekly_pulse_clinical_v2 import classify_single_trial
from utils.parallel_processor import process_trials_parallel


# ═══════════════════════════════════════════════════════════════════════════
# AACT PARSING
# ═══════════════════════════════════════════════════════════════════════════

csv.field_size_limit(2147483647)  # AACT has large description fields


def _read_aact(path: Path) -> List[Dict[str, str]]:
    """Read a pipe-delimited AACT flat file into a list of dicts."""
    with path.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="|")
        return list(reader)


def _read_aact_filtered(path: Path, nct_ids: set) -> List[Dict[str, str]]:
    """
    Read a pipe-delimited AACT file, keeping ONLY rows whose nct_id
    is in the provided set.  Dramatically reduces memory for large tables
    like facilities.txt (~5M rows → ~200K).
    """
    kept = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="|")
        for row in reader:
            nct = (row.get("nct_id") or "").strip()
            if nct in nct_ids:
                kept.append(row)
    return kept


def _safe_int(val: Optional[str]) -> Optional[int]:
    if not val or not val.strip():
        return None
    try:
        return int(float(val.strip()))
    except (ValueError, TypeError):
        return None


def _safe_str(val: Optional[str]) -> Optional[str]:
    if not val or not val.strip():
        return None
    return val.strip()


# ═══════════════════════════════════════════════════════════════════════════
# AACT → CT.GOV NORMALIZATION
# ═══════════════════════════════════════════════════════════════════════════

def _normalize_phase(raw: Optional[str]) -> Optional[str]:
    """
    AACT: "Phase 1", "Phase 1/Phase 2", "Early Phase 1", "Not Applicable"
    CT.gov API: "PHASE1", "PHASE1/PHASE2", "EARLY_PHASE1", "NA"
    """
    if not raw:
        return None
    p = raw.strip()
    mapping = {
        "Phase 1": "PHASE1",
        "Phase 2": "PHASE2",
        "Phase 3": "PHASE3",
        "Phase 4": "PHASE4",
        "Phase 1/Phase 2": "PHASE1/PHASE2",
        "Phase 2/Phase 3": "PHASE2/PHASE3",
        "Early Phase 1": "EARLY_PHASE1",
        "Not Applicable": "NA",
    }
    return mapping.get(p, p.upper().replace(" ", ""))


def _normalize_status(raw: Optional[str]) -> Optional[str]:
    """
    AACT: "Recruiting", "Active, not recruiting", "Completed"
    CT.gov API: "RECRUITING", "ACTIVE_NOT_RECRUITING", "COMPLETED"
    """
    if not raw:
        return None
    s = raw.strip()
    mapping = {
        "Recruiting": "RECRUITING",
        "Active, not recruiting": "ACTIVE_NOT_RECRUITING",
        "Not yet recruiting": "NOT_YET_RECRUITING",
        "Completed": "COMPLETED",
        "Terminated": "TERMINATED",
        "Withdrawn": "WITHDRAWN",
        "Suspended": "SUSPENDED",
        "Enrolling by invitation": "ENROLLING_BY_INVITATION",
        "Available": "AVAILABLE",
        "No longer available": "NO_LONGER_AVAILABLE",
        "Temporarily not available": "TEMPORARILY_NOT_AVAILABLE",
        "Approved for marketing": "APPROVED_FOR_MARKETING",
        "Withheld": "WITHHELD",
        "Unknown status": "UNKNOWN",
    }
    return mapping.get(s, s.upper().replace(" ", "_").replace(",", ""))


def _normalize_study_type(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    return raw.strip().upper().replace(" ", "_")


def _normalize_enrollment_type(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    return raw.strip().upper()


def _normalize_sponsor_class(raw: Optional[str]) -> Optional[str]:
    """
    AACT agency_class: "Industry", "NIH", "U.S. Fed", "Other"
    CT.gov API: "INDUSTRY", "NIH", "FED", "OTHER"
    """
    if not raw:
        return None
    s = raw.strip()
    mapping = {
        "Industry": "INDUSTRY",
        "NIH": "NIH",
        "U.S. Fed": "FED",
        "Other": "OTHER",
    }
    return mapping.get(s, s.upper())


def _normalize_intervention_type(raw: Optional[str]) -> Optional[str]:
    """AACT: "Drug", "Biological", etc. → uppercase."""
    if not raw:
        return None
    return raw.strip().upper().replace(" ", "_")


# ═══════════════════════════════════════════════════════════════════════════
# STEP 1: BUILD LOOKUP TABLES
# ═══════════════════════════════════════════════════════════════════════════

def build_conditions_lookup(rows: List[Dict[str, str]]) -> Dict[str, List[str]]:
    """Pre-filtered rows from conditions.txt → {nct_id: [condition_name, ...]}"""
    lookup: Dict[str, List[str]] = defaultdict(list)
    for r in rows:
        nct = _safe_str(r.get("nct_id"))
        name = _safe_str(r.get("name"))
        if nct and name:
            lookup[nct].append(name)
    return dict(lookup)


def build_interventions_lookup(rows: List[Dict[str, str]]) -> Dict[str, List[Dict[str, Any]]]:
    """Pre-filtered rows from interventions.txt → {nct_id: [{name, type, description}, ...]}"""
    lookup: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        nct = _safe_str(r.get("nct_id"))
        name = _safe_str(r.get("name"))
        if nct and name:
            lookup[nct].append({
                "name": name,
                "type": _normalize_intervention_type(r.get("intervention_type")),
                "description": _safe_str(r.get("description")),
            })
    return dict(lookup)


def build_sponsor_lookup(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """Pre-filtered rows from sponsors.txt → {nct_id: {name, agency_class}}"""
    lookup: Dict[str, Dict[str, str]] = {}
    for r in rows:
        nct = _safe_str(r.get("nct_id"))
        role = _safe_str(r.get("lead_or_collaborator"))
        name = _safe_str(r.get("name"))
        if nct and name and role and role.lower() == "lead":
            lookup[nct] = {
                "name": name,
                "agency_class": _normalize_sponsor_class(r.get("agency_class")),
            }
    return lookup


def build_outcomes_lookup(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, List[Dict]]]:
    """Pre-filtered rows from design_outcomes.txt → {nct_id: {primary: [...], secondary: [...]}}"""
    lookup: Dict[str, Dict[str, List]] = {}
    for r in rows:
        nct = _safe_str(r.get("nct_id"))
        otype = _safe_str(r.get("outcome_type"))
        measure = _safe_str(r.get("measure"))
        if not nct or not otype or not measure:
            continue
        if nct not in lookup:
            lookup[nct] = {"primary": [], "secondary": []}

        entry = {
            "type": otype.upper(),
            "measure": measure,
            "time_frame": _safe_str(r.get("time_frame")),
            "description": _safe_str(r.get("description")),
        }
        key = otype.strip().lower()
        if key == "primary":
            lookup[nct]["primary"].append(entry)
        elif key == "secondary":
            lookup[nct]["secondary"].append(entry)
    return lookup


def build_facilities_lookup(rows: List[Dict[str, str]]) -> Dict[str, List[Dict[str, Any]]]:
    """Pre-filtered rows from facilities.txt → {nct_id: [{name, city, state, country, status}, ...]}"""
    lookup: Dict[str, List[Dict]] = defaultdict(list)
    for r in rows:
        nct = _safe_str(r.get("nct_id"))
        if not nct:
            continue
        lookup[nct].append({
            "name": _safe_str(r.get("name")),
            "city": _safe_str(r.get("city")),
            "state": _safe_str(r.get("state")),
            "country": _safe_str(r.get("country")),
            "status": _safe_str(r.get("status")),
        })
    return dict(lookup)


def _build_mesh_term_to_id(mesh_desc_path: Path) -> Dict[str, str]:
    """
    Build MeSH term-name → ID lookup from disk files.

    1. mesh_descriptors.json  → 30K D-prefix entries (diseases, drug classes)
    2. mesh_supplementary.json → 323K C-prefix entries (specific drugs like
       pembrolizumab, tislelizumab — these are missing from descriptors)

    Keys are lowercased term names to match AACT's browse table format.
    """
    term_to_id: Dict[str, str] = {}

    # ── Layer 1: Descriptors (D-prefix) ────────────────────────────
    if mesh_desc_path.exists():
        data = json.loads(mesh_desc_path.read_text(encoding="utf-8"))
        for desc_id, entry in data.items():
            name = entry.get("name", "").strip()
            if name:
                term_to_id[name.lower()] = desc_id
        del data
        print(f"    Descriptors: {len(term_to_id):,} term→ID mappings")

    # ── Layer 2: Supplementary Concepts (C-prefix) ─────────────────
    supp_path = mesh_desc_path.parent / "mesh_supplementary.json"
    before = len(term_to_id)
    if supp_path.exists():
        data = json.loads(supp_path.read_text(encoding="utf-8"))
        for supp_id, entry in data.items():
            name = entry.get("name", "").strip()
            if name:
                key = name.lower()
                # Don't overwrite descriptors — they have tree numbers directly
                if key not in term_to_id:
                    term_to_id[key] = supp_id
        del data
        added = len(term_to_id) - before
        print(f"    Supplementary: +{added:,} term→ID mappings")

    if not term_to_id:
        print(f"    ⚠ No MeSH files found — IDs will be None")

    print(f"    Total: {len(term_to_id):,} MeSH term→ID mappings")
    return term_to_id


# Will be initialized once in main() and passed to build_mesh_lookup
_MESH_TERM_TO_ID: Dict[str, str] = {}


def build_mesh_lookup(rows: List[Dict[str, str]], term_to_id: Dict[str, str] = None) -> Dict[str, Dict[str, List[Dict]]]:
    """
    Pre-filtered rows from browse_conditions.txt or browse_interventions.txt →
    {nct_id: {meshes: [{id, term}], ancestors: [{id, term}]}}

    AACT mesh_type: "mesh-list" → meshes, "mesh-ancestor" → ancestors
    Uses term_to_id to resolve MeSH descriptor IDs from term names.
    """
    if term_to_id is None:
        term_to_id = {}

    lookup: Dict[str, Dict[str, List[Dict]]] = {}
    resolved = 0
    unresolved = 0
    for r in rows:
        nct = _safe_str(r.get("nct_id"))
        term = _safe_str(r.get("mesh_term"))
        mesh_type = _safe_str(r.get("mesh_type"))
        if not nct or not term:
            continue
        if nct not in lookup:
            lookup[nct] = {"meshes": [], "ancestors": []}

        mid = term_to_id.get(term.lower()) or term_to_id.get(term)
        if mid:
            resolved += 1
        else:
            unresolved += 1
        entry = {"id": mid, "term": term}

        if mesh_type and "ancestor" in mesh_type.lower():
            lookup[nct]["ancestors"].append(entry)
        else:
            lookup[nct]["meshes"].append(entry)

    if term_to_id:
        total = resolved + unresolved
        pct = 100 * resolved / total if total else 0
        print(f"      MeSH ID resolution: {resolved:,}/{total:,} ({pct:.1f}%)")

    return lookup


def build_design_groups_lookup(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """
    Pre-filtered rows from design_groups.txt → {nct_id: {group_title: group_type}}
    For arm_group_map.
    """
    lookup: Dict[str, Dict[str, str]] = defaultdict(dict)
    for r in rows:
        nct = _safe_str(r.get("nct_id"))
        title = _safe_str(r.get("title"))
        group_type = _safe_str(r.get("group_type"))
        if nct and title:
            gtype = group_type.upper().replace(" ", "_") if group_type else ""
            lookup[nct][title] = gtype
    return dict(lookup)



def build_summaries_lookup(rows):
    """Pre-filtered rows from brief_summaries.txt -> {nct_id: description_text}"""
    lookup = {}
    for r in rows:
        nct = _safe_str(r.get("nct_id"))
        text = _safe_str(r.get("description"))
        if nct:
            lookup[nct] = text or ""
    return lookup


def build_descriptions_lookup(rows):
    """Pre-filtered rows from detailed_descriptions.txt -> {nct_id: description_text}"""
    lookup = {}
    for r in rows:
        nct = _safe_str(r.get("nct_id"))
        text = _safe_str(r.get("description"))
        if nct:
            lookup[nct] = text or ""
    return lookup


def build_eligibility_lookup(rows: List[Dict[str, str]]) -> Dict[str, str]:
    """Pre-filtered rows from eligibilities.txt -> {nct_id: criteria_text}"""
    lookup: Dict[str, str] = {}
    for r in rows:
        nct = _safe_str(r.get("nct_id"))
        criteria = _safe_str(r.get("criteria"))
        if nct and criteria:
            lookup[nct] = criteria
    return lookup


# ═══════════════════════════════════════════════════════════════════════════
# STEP 2: ASSEMBLE TRIAL OBJECTS
# ═══════════════════════════════════════════════════════════════════════════

def build_trial_from_aact(
    study_row: Dict[str, str],
    conditions: List[str],
    interventions_raw: List[Dict],
    sponsor_info: Optional[Dict[str, str]],
    outcomes: Optional[Dict[str, List]],
    facilities_list: Optional[List[Dict]],
    condition_mesh: Optional[Dict[str, List[Dict]]],
    intervention_mesh: Optional[Dict[str, List[Dict]]],
    arm_group_map: Optional[Dict[str, str]],
    brief_summary: str = "",
    detailed_description: str = "",
    eligibility_criteria: Optional[str] = None,
) -> ClinicalTrialSignalV2:
    """Assemble a ClinicalTrialSignalV2 from AACT lookup data."""

    nct_id = _safe_str(study_row.get("nct_id")) or ""

    # Title: prefer official_title, fallback to brief_title
    title = _safe_str(study_row.get("official_title")) or _safe_str(study_row.get("brief_title")) or ""

    # Phase normalization
    phase = _normalize_phase(study_row.get("phase"))

    # Status
    overall_status = _normalize_status(study_row.get("overall_status"))

    # Enrollment
    enrollment = _safe_int(study_row.get("enrollment"))
    enrollment_type = _normalize_enrollment_type(study_row.get("enrollment_type"))

    # Sponsor
    sponsor_class = sponsor_info["agency_class"] if sponsor_info else None
    sponsor_name = sponsor_info["name"] if sponsor_info else None

    # Build InterventionV2 objects
    arm_map = arm_group_map or {}
    all_interventions: List[InterventionV2] = []
    interventions_text: List[str] = []
    seen_names = set()

    for iv in interventions_raw:
        name = iv["name"]
        iv_obj = InterventionV2(
            name=name,
            type=iv.get("type"),
            description=iv.get("description"),
            arm_group_labels=[],   # AACT doesn't directly link interventions to arms
            other_names=[],
            role=None,             # Cannot assign without arm-intervention linkage
        )
        all_interventions.append(iv_obj)
        if name not in seen_names:
            interventions_text.append(name)
            seen_names.add(name)

    # Outcomes
    oc = outcomes or {"primary": [], "secondary": []}

    # Facilities
    fac_list = facilities_list or []
    facility_count = len(fac_list) if fac_list else 0

    # MeSH
    cond_mesh = condition_mesh or {"meshes": [], "ancestors": []}
    iv_mesh = intervention_mesh or {"meshes": [], "ancestors": []}

    def _to_mesh_list(items: List[Dict]) -> List[MeshTermV2]:
        return [MeshTermV2(id=m.get("id"), term=m["term"]) for m in items]

    # Dates
    def _clean_date(val: Optional[str]) -> Optional[str]:
        """AACT dates can be full (2025-12-01) or partial (2025-12). Keep as-is."""
        s = _safe_str(val)
        if not s:
            return None
        return s

    return ClinicalTrialSignalV2(
        nct_id=nct_id,
        title=title,
        brief_summary=brief_summary,
        detailed_description=detailed_description,
        conditions=conditions,
        study_type=_normalize_study_type(study_row.get("study_type")),
        phase=phase,
        sponsor_class=sponsor_class,

        # Status & enrollment
        overall_status=overall_status,
        enrollment=enrollment,
        enrollment_type=enrollment_type,
        why_stopped=_safe_str(study_row.get("why_stopped")),
        eligibility_criteria=eligibility_criteria,

        # Sponsor identity
        sponsor_name=sponsor_name,

        # Outcomes
        primary_outcomes=[DesignOutcomeV2(type=o["type"], measure=o["measure"], time_frame=o.get("time_frame"), description=o.get("description")) for o in oc["primary"]],
        secondary_outcomes=[DesignOutcomeV2(type=o["type"], measure=o["measure"], time_frame=o.get("time_frame"), description=o.get("description")) for o in oc["secondary"]],

        # Facilities
        facilities=[FacilityV2(name=f.get("name"), city=f.get("city"), state=f.get("state"), country=f.get("country"), status=f.get("status")) for f in fac_list],
        facility_count=facility_count,

        # Dates
        start_date=_clean_date(study_row.get("start_date")),
        completion_date=_clean_date(study_row.get("completion_date")),
        primary_completion_date=_clean_date(study_row.get("primary_completion_date")),
        first_posted_date=_clean_date(study_row.get("study_first_posted_date")),
        last_update_posted_date=_clean_date(study_row.get("last_update_posted_date")),

        # Interventions
        interventions_all=all_interventions,
        interventions=[],              # Populated by classifier (needs arm roles)
        interventions_text=interventions_text,
        arm_group_map=arm_map,

        # MeSH
        condition_meshes=_to_mesh_list(cond_mesh["meshes"]),
        condition_mesh_ancestors=_to_mesh_list(cond_mesh["ancestors"]),
        intervention_meshes=_to_mesh_list(iv_mesh["meshes"]),
        intervention_mesh_ancestors=_to_mesh_list(iv_mesh["ancestors"]),
    )


# ═══════════════════════════════════════════════════════════════════════════
# CHUNKED CLASSIFICATION WITH CHECKPOINTS
# ═══════════════════════════════════════════════════════════════════════════

def _classify_in_chunks(
    classified_so_far: list,
    remaining: list,
    chunk_size: int,
    start_chunk: int,
    checkpoint_dir: Path,
    num_workers: Optional[int] = None,
) -> tuple:
    """
    Classify trials in chunks, saving a pickle checkpoint after each.
    If the process dies, re-running auto-resumes from the last checkpoint.
    """
    import pickle

    total_remaining = len(remaining)
    chunk_idx = start_chunk

    while remaining:
        chunk = remaining[:chunk_size]
        remaining = remaining[chunk_size:]

        n_done = len(classified_so_far)
        n_total = n_done + len(chunk) + len(remaining)
        print(f"\n  Chunk {chunk_idx}: classifying {len(chunk):,} trials "
              f"({n_done:,}/{n_total:,} done, {len(remaining):,} remaining)")

        t0 = time.time()
        classified_chunk = process_trials_parallel(
            trials=chunk,
            classifier_function=classify_single_trial,
            num_workers=num_workers,
        )
        elapsed = time.time() - t0
        per_sec = len(classified_chunk) / elapsed if elapsed > 0 else 0
        print(f"    {elapsed:.1f}s ({per_sec:.0f} trials/sec)")

        classified_so_far.extend(classified_chunk)

        # Save checkpoint
        checkpoint = {
            "classified": classified_so_far,
            "remaining": remaining,
            "next_chunk": chunk_idx + 1,
            "timestamp": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
        }
        ckpt_path = checkpoint_dir / f"checkpoint_chunk{chunk_idx:03d}.pkl"
        with ckpt_path.open("wb") as f:
            pickle.dump(checkpoint, f)
        print(f"    Checkpoint → {ckpt_path} ({len(classified_so_far):,} classified)")

        chunk_idx += 1

    # Clean up old checkpoints on success
    for old_ckpt in checkpoint_dir.glob("checkpoint_*.pkl"):
        old_ckpt.unlink()
    print(f"  Classification complete. Checkpoints cleaned up.")

    return classified_so_far, remaining


def _save_master(trials: list, output_path: Path, aact_dir: Path, W: int = 60):
    """Serialize classified trials and write master DB JSON."""
    from storage.snapshots_io_v2 import _trial_to_dict

    print(f"\n{'─'*W}")
    print(f"  SAVING MASTER DB")
    print(f"{'─'*W}")

    def _trial_to_master_dict(t) -> Dict[str, Any]:
        """Serialize trial to master DB format with all expanded fields."""
        d = _trial_to_dict(t)
        d.setdefault("overall_status", getattr(t, "overall_status", None))
        d.setdefault("enrollment", getattr(t, "enrollment", None))
        d.setdefault("enrollment_type", getattr(t, "enrollment_type", None))
        d.setdefault("why_stopped", getattr(t, "why_stopped", None))
        d.setdefault("sponsor_name", getattr(t, "sponsor_name", None))
        d.setdefault("start_date", getattr(t, "start_date", None))
        d.setdefault("completion_date", getattr(t, "completion_date", None))
        d.setdefault("primary_completion_date", getattr(t, "primary_completion_date", None))

        def _ser_outcomes(items):
            out = []
            for o in (items or []):
                if isinstance(o, dict):
                    out.append(o)
                elif hasattr(o, "measure"):
                    out.append({
                        "type": getattr(o, "type", None),
                        "measure": o.measure,
                        "time_frame": getattr(o, "time_frame", None),
                        "description": getattr(o, "description", None),
                    })
            return out

        d.setdefault("primary_outcomes", _ser_outcomes(getattr(t, "primary_outcomes", [])))
        d.setdefault("secondary_outcomes", _ser_outcomes(getattr(t, "secondary_outcomes", [])))

        def _ser_facilities(items):
            out = []
            for f_item in (items or []):
                if isinstance(f_item, dict):
                    out.append(f_item)
                elif hasattr(f_item, "name"):
                    out.append({
                        "name": getattr(f_item, "name", None),
                        "city": getattr(f_item, "city", None),
                        "state": getattr(f_item, "state", None),
                        "country": getattr(f_item, "country", None),
                        "status": getattr(f_item, "status", None),
                    })
            return out

        d.setdefault("facilities", _ser_facilities(getattr(t, "facilities", [])))
        d.setdefault("facility_count", getattr(t, "facility_count", 0))
        return d

    trial_dicts = [_trial_to_master_dict(t) for t in trials]

    # ── Full summary (matches weekly pulse output) ──────────────────
    from analytics.summary_v2 import (
        ta_modality_counts_true_drugs,
        drug_trial_counts,
        info_flag_counts_true_drugs,
        drug_modality_summary,
        drug_therapeutic_area_summary,
        drug_info_overview,
        intervention_type_summary_all_trials,
        study_type_summary_all_trials,
        drug_modality_provenance_summary,
        drug_ta_provenance_summary,
        drug_study_intent_summary,
        ta_by_phase,
        modality_by_phase,
        ta_by_sponsor_class,
        multi_ta_rate_by_phase,
        drug_mesh_missing_condition_summary,
        non_disease_study_category_summary,
    )

    summary = {
        "ta_modality_counts_true_drugs": ta_modality_counts_true_drugs(trials),
        "drug_trial_counts": drug_trial_counts(trials),
        "info_flag_counts_true_drugs": info_flag_counts_true_drugs(trials),
        "drug_info_overview": drug_info_overview(trials),
        "intervention_type_summary": intervention_type_summary_all_trials(trials),
        "study_type_summary": study_type_summary_all_trials(trials),
        "drug_modality_provenance": drug_modality_provenance_summary(trials),
        "drug_ta_provenance": drug_ta_provenance_summary(trials),
        "drug_study_intent": drug_study_intent_summary(trials),
        "ta_by_phase": ta_by_phase(trials),
        "modality_by_phase": modality_by_phase(trials),
        "ta_by_sponsor_class": ta_by_sponsor_class(trials),
        "multi_ta_rate_by_phase": multi_ta_rate_by_phase(trials),
        "drug_mesh_missing_condition": drug_mesh_missing_condition_summary(trials),
        "non_disease_study_categories": non_disease_study_category_summary(trials),
    }

    master = {
        "metadata": {
            "source": "AACT monthly export",
            "aact_dir": str(aact_dir),
            "export_date": aact_dir.name,
            "generated_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat() + "Z",
            "trial_count": len(trial_dicts),
            "filter": "is_drug_trial=True, study_type=INTERVENTIONAL, status=ACTIVE",
            "format": "ALEXIS_MASTER_V2",
        },
        "summary": summary,
        "trials": trial_dicts,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(master, f, indent=2, default=str)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  Saved: {output_path}")
    print(f"    {len(trial_dicts):,} drug trials")
    print(f"    {size_mb:.1f} MB")

    # ── Print summary ───────────────────────────────────────────────
    print("\nTA × Modality counts (TRUE DRUGS ONLY):")
    for ta, mods in summary["ta_modality_counts_true_drugs"].items():
        for modality, count in mods.items():
            print(f"  {ta:20} | {modality:22} | {count}")

    print("\nModality INFO summary (TRUE DRUGS ONLY):")
    for flag, count in summary["info_flag_counts_true_drugs"].items():
        print(f"  {flag}: {count}")

    print("\nDrug trial overview:")
    for k, v in summary["drug_info_overview"].items():
        print(f"  {k}: {v}")

    print("\nDrug trials by modality:")
    for k, v in sorted(drug_modality_summary(trials).items()):
        print(f"  {k:25} | {v}")

    print("\nDrug trials by therapeutic area:")
    for k, v in sorted(drug_therapeutic_area_summary(trials).items()):
        print(f"  {k:25} | {v}")

    print("\nStudyType summary (ALL trials):")
    for st, count in summary.get("study_type_summary", {}).items():
        print(f"  {st}: {count}")

    ctgov = summary.get("intervention_type_summary")
    if ctgov:
        print("\nCT.gov Intervention Category Summary (SOURCE LAYER):")
        print(f"  Layer: {ctgov.get('_layer')}")
        print(f"  Requires: {ctgov.get('_requires')}")
        print(f"  Valid on snapshots: {ctgov.get('_valid_on_snapshots')}")
        print("\n  Category                 | Trials with Category")
        print("  -----------------------------------------------")
        for tp, count in ctgov.get("trials_with_category", {}).items():
            print(f"  {tp:25} | {count}")

    print("\nDrug modality provenance (drug trials):")
    for k, v in summary["drug_modality_provenance"].items():
        print(f"  {k:20} | {v}")

    print("\nTherapeutic area provenance (drug trials):")
    for k, v in summary["drug_ta_provenance"].items():
        print(f"  {k:20} | {v}")

    print("\nDrug study intent:")
    for k, v in summary["drug_study_intent"].items():
        print(f"  {k:15} | {v}")

    print("\nDrug mesh-missing condition (DATA COMPLETENESS, NOT INTENT):")
    for k, v in summary["drug_mesh_missing_condition"].items():
        print(f"  {k:25} | {v}")

    print("\nTA × Phase:")
    for ta, phases in summary["ta_by_phase"].items():
        for phase, count in phases.items():
            print(f"  {ta:20} | {phase:10} | {count}")

    print("\nModality × Phase:")
    for mod, phases in summary["modality_by_phase"].items():
        for phase, count in phases.items():
            print(f"  {mod:20} | {phase:10} | {count}")

    print("\nTA × Sponsor class:")
    for ta, sponsors in summary["ta_by_sponsor_class"].items():
        for sponsor, count in sponsors.items():
            print(f"  {ta:20} | {sponsor:15} | {count}")

    print("\nMulti-TA rate by phase:")
    for phase, rate in summary["multi_ta_rate_by_phase"].items():
        print(f"  {phase:10} | {rate:.2%}")

    print("\nNon-disease study categories:")
    for k, v in summary.get("non_disease_study_categories", {}).items():
        print(f"  {k:25} | {v}")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def _prompt_aact_dir(universe_dir: Path) -> Path:
    """
    Scan active_universe for subdirectories and let the user pick one.
    Only shows directories that contain at least studies.txt (i.e. look like
    real AACT exports).  Falls back to a free-text entry if nothing is found.
    """
    W = 60
    print(f"\n{'═'*W}")
    print(f"  SELECT AACT SOURCE FOLDER")
    print(f"  Scanning: {universe_dir}")
    print(f"{'─'*W}")

    candidates = []
    if universe_dir.is_dir():
        for p in sorted(universe_dir.iterdir()):
            if p.is_dir() and (p / "studies.txt").exists():
                candidates.append(p)

    if not candidates:
        print("  No AACT export folders found (need studies.txt inside).")
        raw = input("  Enter full path to AACT folder: ").strip()
        chosen = Path(raw)
        if not chosen.is_dir():
            print(f"  ERROR: '{chosen}' is not a directory.")
            sys.exit(1)
        return chosen

    for i, p in enumerate(candidates, 1):
        # Show a quick file count as a sanity hint
        txt_count = len(list(p.glob("*.txt")))
        print(f"  [{i}] {p.name}  ({txt_count} .txt files)")

    print(f"{'─'*W}")
    while True:
        raw = input(f"  Choose folder [1-{len(candidates)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(candidates):
            return candidates[int(raw) - 1]
        print(f"  Please enter a number between 1 and {len(candidates)}.")


def _prompt_output_path(universe_dir: Path) -> Path:
    """Ask the user for the output JSON filename (no path needed)."""
    W = 60
    print(f"\n{'─'*W}")
    print(f"  OUTPUT FILE NAME")
    print(f"  Output will be saved in: {universe_dir}")
    print(f"  Tip: use a name like  master_DB_2026_Q1.json")
    print(f"{'─'*W}")

    while True:
        raw = input("  File name: ").strip()
        if not raw:
            print("  Name cannot be empty.")
            continue
        if not raw.endswith(".json"):
            raw += ".json"
            print(f"  → Added .json extension: {raw}")
        return universe_dir / raw




# ═══════════════════════════════════════════════════════════════════════════
# PROVENANCE BACKFILL (modality_source / therapeutic_area_source)
# ═══════════════════════════════════════════════════════════════════════════

# Literal TA values — kept inline to avoid heavy policy import chain at module
# load time (workers fork from this file).
_TA_NON_DISEASE = "Non-disease drug study"
_TA_UNASSIGNED  = "Unassigned drug study"


def _apply_source_fields(trial) -> None:
    """
    Set trial.modality_source and trial.therapeutic_area_source in place,
    using the same derivation logic as pipelines/backfill_source_fields.py.

    Must be called AFTER classify_single_trial has populated modality /
    therapeutic_area / therapeutic_areas_detected / info_flags.
    """
    if not getattr(trial, "is_drug_trial", False):
        trial.modality_source = None
        trial.therapeutic_area_source = None
        return

    # ── modality_source ────────────────────────────────────────────────
    mesh_available = bool(getattr(trial, "intervention_meshes", None))
    mesh_failed = "mesh_available_but_not_used" in (getattr(trial, "info_flags", None) or [])

    if mesh_available and not mesh_failed:
        trial.modality_source = "mesh_tree"
    else:
        # Re-run text matcher to distinguish text vs intervention_type paths.
        # Imported lazily so module load stays light for worker forks.
        from policy.text_modality_policy_v2 import text_modality_from_text
        text_blob = " ".join(
            (getattr(trial, "interventions_text", None) or [])
            + [getattr(trial, "title", None) or ""]
        )
        text_hit = text_modality_from_text(text_blob, getattr(trial, "modality", None))
        trial.modality_source = "text" if text_hit else "intervention_type"

    # ── therapeutic_area_source ────────────────────────────────────────
    ta = getattr(trial, "therapeutic_area", None)
    ta_detected = getattr(trial, "therapeutic_areas_detected", None) or []

    if ta_detected:
        trial.therapeutic_area_source = "mesh_evidence"
    elif ta == _TA_NON_DISEASE:
        trial.therapeutic_area_source = "enabling_signal"
    elif ta == _TA_UNASSIGNED:
        trial.therapeutic_area_source = "unassigned_fallback"
    elif ta:
        trial.therapeutic_area_source = "text_matching"
    else:
        trial.therapeutic_area_source = None


def main():
    import gc

    # ═══════════════════════════════════════════════════════════════
    # FIXED SETTINGS
    # ═══════════════════════════════════════════════════════════════

    UNIVERSE_DIR  = Path("storage/snapshots/clinical_trials_v2/active_universe")
    FRESH_START   = False    # True = ignore checkpoints, start over
    BATCH_SIZE    = 1000     # process this many trials at a time
    NUM_WORKERS   = None     # None = auto-detect (cpu_count - 1)

    # ═══════════════════════════════════════════════════════════════
    # INTERACTIVE SELECTION
    # ═══════════════════════════════════════════════════════════════

    aact_dir    = _prompt_aact_dir(UNIVERSE_DIR)
    output_path = _prompt_output_path(UNIVERSE_DIR)

    W = 60

    print(f"\n{'='*W}")
    print(f"  BUILD MASTER DB FROM AACT (batched)")
    print(f"  Source : {aact_dir}")
    print(f"  Output : {output_path}")
    print(f"  Batches: {BATCH_SIZE:,} trials each")
    print(f"{'='*W}")

    # ── Verify required files ───────────────────────────────────────
    required = ["studies.txt", "conditions.txt", "interventions.txt", "sponsors.txt"]
    optional = ["design_outcomes.txt", "facilities.txt",
                "browse_conditions.txt", "browse_interventions.txt",
                "design_groups.txt",
                "brief_summaries.txt", "detailed_descriptions.txt",
                "eligibilities.txt"]

    for fname in required:
        if not (aact_dir / fname).exists():
            print(f"  ERROR: required file missing: {aact_dir / fname}")
            sys.exit(1)

    for fname in optional:
        if (aact_dir / fname).exists():
            print(f"  ✓ {fname}")
        else:
            print(f"  ⚠ {fname} not found (optional, skipping)")

    # ── Step 1: Read studies.txt → filter → get target NCT IDs ────
    print(f"\n{'─'*W}")
    print(f"  STEP 1: Reading studies.txt & filtering")
    print(f"{'─'*W}")

    t0 = time.time()

    ACTIVE_STATUSES_RAW = {
        "RECRUITING", "ACTIVE_NOT_RECRUITING", "NOT_YET_RECRUITING",
        "ENROLLING_BY_INVITATION", "AVAILABLE",
    }

    print("  Reading studies.txt ...")
    studies_rows = _read_aact(aact_dir / "studies.txt")
    print(f"    {len(studies_rows):,} total studies")

    # Filter: interventional + active status
    studies_by_nct = {}
    for r in studies_rows:
        nct = _safe_str(r.get("nct_id"))
        if not nct:
            continue
        stype = _safe_str(r.get("study_type"))
        status = _safe_str(r.get("overall_status"))
        if stype and stype.upper() == "INTERVENTIONAL" and status in ACTIVE_STATUSES_RAW:
            studies_by_nct[nct] = r

    del studies_rows  # free ~560K rows
    gc.collect()

    nct_list = list(studies_by_nct.keys())
    total_ncts = len(nct_list)
    num_batches = (total_ncts + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"    Interventional + active: {total_ncts:,}")
    print(f"    Batches: {num_batches} × {BATCH_SIZE:,}")

    # ── Pre-load MeSH disk cache (shared across all batches) ──────
    from policy.mesh_tree_modality_policy_v2 import warm_cache
    warm_cache()

    # ── Step 2: Read all tables once ──────────────────────────────
    print(f"\n{'─'*W}")
    print(f"  STEP 2: Reading tables (filtered to {total_ncts:,} NCTs)")
    print(f"{'─'*W}")

    target_ncts = set(nct_list)

    def _read_filtered(filename: str) -> List[Dict[str, str]]:
        path = aact_dir / filename
        if not path.exists():
            print(f"    ⚠ {filename} not found, skipping")
            return []
        rows = _read_aact_filtered(path, target_ncts)
        print(f"    {filename}: {len(rows):,} rows")
        return rows

    print("  Loading MeSH term→ID resolver ...")
    mesh_term_to_id = _build_mesh_term_to_id(Path("storage/mesh/mesh_descriptors.json"))
    condition_mesh_lookup = build_mesh_lookup(_read_filtered("browse_conditions.txt"), mesh_term_to_id)
    intervention_mesh_lookup = build_mesh_lookup(_read_filtered("browse_interventions.txt"), mesh_term_to_id)
    del mesh_term_to_id
    gc.collect()

    conditions_lookup = build_conditions_lookup(_read_filtered("conditions.txt"))
    interventions_lookup = build_interventions_lookup(_read_filtered("interventions.txt"))
    sponsors_lookup = build_sponsor_lookup(_read_filtered("sponsors.txt"))
    outcomes_lookup = build_outcomes_lookup(_read_filtered("design_outcomes.txt"))
    facilities_lookup = build_facilities_lookup(_read_filtered("facilities.txt"))
    arm_groups_lookup = build_design_groups_lookup(_read_filtered("design_groups.txt"))
    summaries_lookup = build_summaries_lookup(_read_filtered("brief_summaries.txt"))
    descriptions_lookup = build_descriptions_lookup(_read_filtered("detailed_descriptions.txt"))
    eligibility_lookup = build_eligibility_lookup(_read_filtered("eligibilities.txt"))

    t1 = time.time()
    print(f"\n  All tables loaded in {t1 - t0:.1f}s")

    # ── Steps 3-4: Assemble + classify in batches ─────────────────
    print(f"\n{'─'*W}")
    print(f"  STEPS 3-4: Assembling & classifying in {num_batches} batches")
    print(f"{'─'*W}")

    total_assembled = 0
    total_skipped = 0
    batch_dir = output_path.parent / ".batches"
    batch_dir.mkdir(parents=True, exist_ok=True)

    for batch_idx in range(num_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, total_ncts)
        batch_ncts = nct_list[start:end]

        print(f"\n  ── Batch {batch_idx+1}/{num_batches}: "
              f"NCTs {start+1:,}-{end:,} ({len(batch_ncts):,} trials) ──")

        # Skip if already processed
        batch_file = batch_dir / f"batch_{batch_idx:04d}.pkl"
        if batch_file.exists():
            print(f"    Already saved, skipping")
            total_assembled += len(batch_ncts)
            continue

        # Assemble this batch only
        trials: List[ClinicalTrialSignalV2] = []
        skipped = 0
        for nct_id in batch_ncts:
            study_row = studies_by_nct[nct_id]
            try:
                trial = build_trial_from_aact(
                    study_row=study_row,
                    conditions=conditions_lookup.get(nct_id, []),
                    interventions_raw=interventions_lookup.get(nct_id, []),
                    sponsor_info=sponsors_lookup.get(nct_id),
                    outcomes=outcomes_lookup.get(nct_id),
                    facilities_list=facilities_lookup.get(nct_id),
                    condition_mesh=condition_mesh_lookup.get(nct_id),
                    intervention_mesh=intervention_mesh_lookup.get(nct_id),
                    arm_group_map=arm_groups_lookup.get(nct_id),
                    brief_summary=summaries_lookup.get(nct_id, ""),
                    detailed_description=descriptions_lookup.get(nct_id, ""),
                    eligibility_criteria=eligibility_lookup.get(nct_id),
                )
                trials.append(trial)
            except Exception as e:
                skipped += 1
                if total_skipped + skipped <= 5:
                    print(f"    ⚠ Skipped {nct_id}: {e}")

        total_assembled += len(trials)
        total_skipped += skipped

        # Classify
        t_cls = time.time()
        classified = process_trials_parallel(
            trials=trials,
            classifier_function=classify_single_trial,
            num_workers=NUM_WORKERS,
        )
        elapsed_cls = time.time() - t_cls
        per_sec = len(classified) / elapsed_cls if elapsed_cls > 0 else 0

        # Keep drug trials only — save to disk
        drug = [t for t in classified if t.is_drug_trial]

        # Backfill provenance fields in-place so master DB is complete
        # (matches pipelines/backfill_source_fields.py logic).
        for _t in drug:
            _apply_source_fields(_t)

        if drug:
            import pickle
            batch_file = batch_dir / f"batch_{batch_idx:04d}.pkl"
            with batch_file.open("wb") as bf:
                pickle.dump(drug, bf)

        print(f"    Assembled: {len(trials)} | Classified: {elapsed_cls:.1f}s "
              f"({per_sec:.0f}/sec) | Drug: {len(drug)}")

        del trials, classified, drug
        gc.collect()

    del studies_by_nct, conditions_lookup, interventions_lookup
    del sponsors_lookup, outcomes_lookup, facilities_lookup
    del condition_mesh_lookup, intervention_mesh_lookup, arm_groups_lookup
    del summaries_lookup, descriptions_lookup, eligibility_lookup
    gc.collect()

    # ── Step 5: Merge batches, deduplicate ──────────────────────────
    print(f"\n{'─'*W}")
    print(f"  STEP 5: Merge batches & save")
    print(f"{'─'*W}")

    print(f"  Total assembled: {total_assembled:,} ({total_skipped} skipped)")

    import pickle
    dedup = {}
    for batch_file in sorted(batch_dir.glob("batch_*.pkl")):
        with batch_file.open("rb") as bf:
            batch_trials = pickle.load(bf)
        for t in batch_trials:
            if t.nct_id:
                dedup[t.nct_id] = t
        del batch_trials
    
    trials = list(dedup.values())
    del dedup
    gc.collect()
    
    print(f"  Total drug trials (deduped): {len(trials):,}")

    # ── Step 6: Save ────────────────────────────────────────────────
    _save_master(trials, output_path, aact_dir, W)

    # Clean up batch files
    for bf in batch_dir.glob("batch_*.pkl"):
        bf.unlink()
    batch_dir.rmdir()

    elapsed = time.time() - t0
    print(f"\n  Total time: {elapsed:.1f}s")
    print(f"  Done.")


if __name__ == "__main__":
    main()
