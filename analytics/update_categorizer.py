"""
update_categorizer.py
─────────────────────
Categorizes clinical trial updates by diffing pulse snapshots against
the master DB. Implements the ALEXIS 13-category taxonomy with
directional tags and tiered impact scoring.

Pipeline steps implemented:
  1. Load & Index
  2. Split New vs. Existing  (+ inactive_update handling)
  3. Field-Level Diff
  4. Categorize Changes
  7. Tag & Save              (enriched snapshot)
  8. Generate Changelog       (human-readable report)

Steps 5 (Phase Linkage) and 6 (Outcome Assessment) are deferred.

Usage:
  python update_categorizer.py \
      --master  "storage/snapshots/clinical_trials_v2/active_universe/master_DB.json" \
      --snapshot "storage/snapshots/clinical_trials_v2/last_update/2026-02-21_2026-02-24_v1.json" \
      --drug-only \
      --output-enriched enriched_snapshot.json \
      --output-changelog changelog.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
_UTC = timezone.utc
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════════
# TAXONOMY DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

ACTIVE_STATUSES = {
    "RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION",
    "ACTIVE_NOT_RECRUITING", "AVAILABLE",
}

TERMINAL_STATUSES = {
    "COMPLETED", "TERMINATED", "WITHDRAWN", "SUSPENDED",
}

RECRUITING_STATUSES = {"RECRUITING", "ENROLLING_BY_INVITATION"}

STOP_STATUSES = {"TERMINATED", "WITHDRAWN", "SUSPENDED"}


# Fields to compare, grouped by tier
TIER1_FIELDS = [
    "overall_status", "phase", "enrollment", "enrollment_type", "why_stopped",
]

TIER2_FIELDS = [
    "sponsor_name", "sponsor_class", "study_type",
    "start_date", "completion_date", "primary_completion_date",
    "primary_outcomes", "secondary_outcomes",
    "facilities", "facility_count",
]

TIER3_FIELDS = [
    "title", "conditions",
    "interventions_text", "arm_group_map",
    "therapeutic_area", "is_drug_trial", "modality",
    "study_intent", "study_category",
    "last_update_posted_date",
]

ALL_COMPARE_FIELDS = TIER1_FIELDS + TIER2_FIELDS + TIER3_FIELDS


def _field_tier(field: str) -> int:
    if field in TIER1_FIELDS:
        return 1
    if field in TIER2_FIELDS:
        return 2
    return 3


# ═══════════════════════════════════════════════════════════════════════════
# COMPARISON HELPERS
# ═══════════════════════════════════════════════════════════════════════════

_DATE_FIELDS = {
    "start_date", "completion_date", "primary_completion_date",
    "first_posted_date", "last_update_posted_date",
}


def _dates_equivalent(a: Any, b: Any) -> bool:
    """Precision-aware date comparison."""
    if a == b:
        return True
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    sa, sb = a.strip(), b.strip()
    min_len = min(len(sa), len(sb))
    return sa[:min_len] == sb[:min_len]


def _normalize_for_compare(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, list) and len(val) == 0:
        return None
    if isinstance(val, dict) and len(val) == 0:
        return None
    return val


_IV_TYPE_PREFIX = re.compile(r'^[a-z]+:\s*', re.IGNORECASE)


def _normalize_text_list(val: Any) -> list:
    """Normalize a text list for comparison: strip type prefixes, lowercase, strip, sort, dedupe."""
    if not val or not isinstance(val, list):
        return []
    normed = set()
    for s in val:
        if isinstance(s, str) and s.strip():
            clean = _IV_TYPE_PREFIX.sub('', s.strip()).lower()
            if clean:
                normed.add(clean)
    return sorted(normed)


_LIST_FIELDS_NORMALIZE = {"interventions_text"}


def _is_meaningful_change(field: str, old: Any, new: Any) -> bool:
    old_n = _normalize_for_compare(old)
    new_n = _normalize_for_compare(new)
    if old_n == new_n:
        return False
    if field in _DATE_FIELDS and _dates_equivalent(old, new):
        return False
    # Normalized comparison for text lists (ignore ordering/whitespace/case)
    if field in _LIST_FIELDS_NORMALIZE:
        return _normalize_text_list(old) != _normalize_text_list(new)
    return True


# ═══════════════════════════════════════════════════════════════════════════
# STEP 3: FIELD-LEVEL DIFF
# ═══════════════════════════════════════════════════════════════════════════

def diff_trial(master: Dict, snapshot: Dict) -> List[Dict[str, Any]]:
    """Diff two trial dicts. Returns list of change records with tier info."""
    changes = []
    for field in ALL_COMPARE_FIELDS:
        old = master.get(field)
        new = snapshot.get(field)
        if _is_meaningful_change(field, old, new):
            change = {
                "field": field,
                "tier": _field_tier(field),
                "old": old,
                "new": new,
            }
            if isinstance(old, (int, float)) and isinstance(new, (int, float)):
                change["delta"] = new - old
                if old != 0:
                    change["delta_pct"] = round(100 * (new - old) / old, 1)
            changes.append(change)
    return changes


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4: CATEGORIZE CHANGES
# ═══════════════════════════════════════════════════════════════════════════

def _categorize_status_change(old_status: str, new_status: str) -> Optional[Dict]:
    """Categorize a status field change."""
    if new_status in RECRUITING_STATUSES and old_status not in RECRUITING_STATUSES:
        return {
            "category": "status_to_recruiting",
            "tier": 1,
            "direction": f"from_{old_status.lower()}",
            "old_value": old_status,
            "new_value": new_status,
            "field": "overall_status",
        }

    if new_status == "COMPLETED" and old_status != "COMPLETED":
        return {
            "category": "status_to_completed",
            "tier": 1,
            "direction": "completed_unknown",  # outcome assessment deferred
            "old_value": old_status,
            "new_value": new_status,
            "field": "overall_status",
        }

    if new_status in STOP_STATUSES and old_status not in STOP_STATUSES:
        return {
            "category": "status_to_stopped",
            "tier": 1,
            "direction": new_status.lower(),
            "old_value": old_status,
            "new_value": new_status,
            "field": "overall_status",
        }

    if new_status == "ACTIVE_NOT_RECRUITING" and old_status in RECRUITING_STATUSES:
        return {
            "category": "status_to_active_not_recruiting",
            "tier": 1,
            "direction": f"from_{old_status.lower()}",
            "old_value": old_status,
            "new_value": new_status,
            "field": "overall_status",
        }

    # Catch-all for other transitions
    return {
        "category": "status_changed",
        "tier": 1,
        "direction": f"{old_status.lower()}_to_{new_status.lower()}",
        "old_value": old_status,
        "new_value": new_status,
        "field": "overall_status",
    }


def _categorize_enrollment_change(old_enroll: int, new_enroll: int, old_type: str, new_type: str) -> List[Dict]:
    """Categorize enrollment field changes."""
    cats = []
    if old_enroll != new_enroll and old_enroll is not None and new_enroll is not None:
        delta = new_enroll - old_enroll
        delta_pct = round(100 * delta / old_enroll, 1) if old_enroll != 0 else None
        direction = "enrollment_up" if delta > 0 else "enrollment_down"
        cats.append({
            "category": "enrollment_change",
            "tier": 2,
            "direction": direction,
            "old_value": old_enroll,
            "new_value": new_enroll,
            "delta": delta,
            "delta_pct": delta_pct,
            "field": "enrollment",
        })

    if old_type != new_type and old_type is not None and new_type is not None:
        cats.append({
            "category": "enrollment_type_change",
            "tier": 2,
            "direction": f"{(old_type or '').lower()}_to_{(new_type or '').lower()}",
            "old_value": old_type,
            "new_value": new_type,
            "field": "enrollment_type",
        })
    return cats


def _extract_intervention_names(interventions: Optional[List]) -> set:
    """Extract intervention names from interventions_all or interventions_text."""
    if not interventions:
        return set()
    names = set()
    for item in interventions:
        if isinstance(item, dict):
            name = item.get("name", "")
            if name:
                names.add(_IV_TYPE_PREFIX.sub('', name.strip()).lower())
        elif isinstance(item, str):
            names.add(_IV_TYPE_PREFIX.sub('', item.strip()).lower())
    return names


def _categorize_intervention_change(
    old_text: Any, new_text: Any,
    old_all: Any, new_all: Any,
) -> List[Dict]:
    """Categorize intervention changes — arms added/removed vs modified."""
    cats = []

    old_names = _extract_intervention_names(old_all or old_text)
    new_names = _extract_intervention_names(new_all or new_text)

    added = new_names - old_names
    removed = old_names - new_names

    if added:
        cats.append({
            "category": "new_arm_added",
            "tier": 1,
            "direction": "arm_added",
            "old_value": len(old_names),
            "new_value": len(new_names),
            "added": sorted(added),
            "field": "interventions",
        })
    if removed:
        cats.append({
            "category": "new_arm_added",
            "tier": 1,
            "direction": "arm_removed",
            "old_value": len(old_names),
            "new_value": len(new_names),
            "removed": sorted(removed),
            "field": "interventions",
        })

    # If same names but genuinely different text → intervention_changed (not new arm)
    if not added and not removed and _normalize_text_list(old_text) != _normalize_text_list(new_text):
        cats.append({
            "category": "intervention_changed",
            "tier": 2,
            "direction": "description_changed",
            "field": "interventions_text",
        })

    return cats


def _extract_outcome_measures(outcomes: Optional[List]) -> List[str]:
    """Extract measure names from outcomes list."""
    if not outcomes:
        return []
    measures = []
    for o in outcomes:
        if isinstance(o, dict):
            m = o.get("measure", "")
            if m:
                measures.append(m.strip().lower())
    return measures


def _categorize_endpoint_change(
    old_primary: Any, new_primary: Any,
    old_secondary: Any, new_secondary: Any,
) -> List[Dict]:
    """Categorize primary/secondary outcome changes."""
    cats = []

    old_pm = _extract_outcome_measures(old_primary)
    new_pm = _extract_outcome_measures(new_primary)
    if old_pm != new_pm and (old_pm or new_pm):
        old_set = set(old_pm)
        new_set = set(new_pm)
        added = new_set - old_set
        removed = old_set - new_set

        if added and not removed:
            direction = "endpoint_added"
        elif removed and not added:
            direction = "endpoint_removed"
        else:
            direction = "endpoint_modified"

        cats.append({
            "category": "endpoint_changed",
            "tier": 2,
            "direction": direction,
            "old_count": len(old_pm),
            "new_count": len(new_pm),
            "field": "primary_outcomes",
        })

    old_sm = _extract_outcome_measures(old_secondary)
    new_sm = _extract_outcome_measures(new_secondary)
    if old_sm != new_sm and (old_sm or new_sm):
        cats.append({
            "category": "secondary_endpoint_changed",
            "tier": 2,
            "direction": "modified",
            "old_count": len(old_sm),
            "new_count": len(new_sm),
            "field": "secondary_outcomes",
        })

    return cats


def _categorize_sites_change(old_count: Any, new_count: Any) -> Optional[Dict]:
    """Categorize facility count changes."""
    if old_count is None or new_count is None:
        return None
    if old_count == new_count:
        return None
    delta = new_count - old_count
    direction = "sites_added" if delta > 0 else "sites_removed"
    return {
        "category": "sites_changed",
        "tier": 2,
        "direction": direction,
        "old_value": old_count,
        "new_value": new_count,
        "delta": delta,
        "field": "facility_count",
    }


def _categorize_reclassification(
    old_ta: str, new_ta: str,
    old_mod: str, new_mod: str,
    has_condition_change: bool,
    has_intervention_change: bool,
) -> Optional[Dict]:
    """
    Detect ALEXIS reclassification vs real trial change.
    If TA/modality changed but conditions/interventions didn't, it's an ALEXIS
    policy update, not a CT.gov change.
    """
    ta_changed = old_ta != new_ta and old_ta is not None and new_ta is not None
    mod_changed = old_mod != new_mod and old_mod is not None and new_mod is not None

    if not ta_changed and not mod_changed:
        return None

    # If conditions/interventions also changed → real change, not reclassification
    if has_condition_change or has_intervention_change:
        return None

    if ta_changed and mod_changed:
        direction = "both_changed"
    elif ta_changed:
        direction = "ta_changed"
    else:
        direction = "modality_changed"

    details = {}
    if ta_changed:
        details["old_ta"] = old_ta
        details["new_ta"] = new_ta
    if mod_changed:
        details["old_modality"] = old_mod
        details["new_modality"] = new_mod

    return {
        "category": "reclassified",
        "tier": 3,
        "direction": direction,
        **details,
        "field": "therapeutic_area" if ta_changed else "modality",
    }


def categorize_trial_changes(
    master_trial: Dict,
    snapshot_trial: Dict,
    raw_diffs: List[Dict],
) -> List[Dict]:
    """
    Given raw field diffs, produce a list of categorized update tags.
    Multiple categories per trial are allowed.
    """
    categories = []
    changed_fields = {d["field"] for d in raw_diffs}

    # Skip last_update_posted_date for business logic — it's always different
    business_fields = changed_fields - {"last_update_posted_date"}

    # ── Status transitions (Tier 1) ─────────────────────────────────
    if "overall_status" in changed_fields:
        old_status = master_trial.get("overall_status") or ""
        new_status = snapshot_trial.get("overall_status") or ""
        if old_status and new_status:
            cat = _categorize_status_change(old_status, new_status)
            if cat:
                categories.append(cat)

    # ── Why stopped (corroborates status_to_stopped) ────────────────
    if "why_stopped" in changed_fields:
        new_why = snapshot_trial.get("why_stopped")
        if new_why and not master_trial.get("why_stopped"):
            # Find existing stopped category and annotate
            for c in categories:
                if c["category"] == "status_to_stopped":
                    c["why_stopped"] = new_why
                    break

    # ── Enrollment changes (Tier 1/2) ───────────────────────────────
    if "enrollment" in changed_fields or "enrollment_type" in changed_fields:
        cats = _categorize_enrollment_change(
            master_trial.get("enrollment"),
            snapshot_trial.get("enrollment"),
            master_trial.get("enrollment_type"),
            snapshot_trial.get("enrollment_type"),
        )
        categories.extend(cats)

    # ── Intervention / arm changes (Tier 1 or 2) ────────────────────
    if "interventions_text" in changed_fields:
        cats = _categorize_intervention_change(
            master_trial.get("interventions_text"),
            snapshot_trial.get("interventions_text"),
            master_trial.get("interventions_all"),
            snapshot_trial.get("interventions_all"),
        )
        categories.extend(cats)

    # ── Endpoint changes (Tier 2) ───────────────────────────────────
    if "primary_outcomes" in changed_fields or "secondary_outcomes" in changed_fields:
        cats = _categorize_endpoint_change(
            master_trial.get("primary_outcomes"),
            snapshot_trial.get("primary_outcomes"),
            master_trial.get("secondary_outcomes"),
            snapshot_trial.get("secondary_outcomes"),
        )
        categories.extend(cats)

    # ── Sponsor changes (Tier 2) ────────────────────────────────────
    if "sponsor_name" in changed_fields:
        categories.append({
            "category": "sponsor_changed",
            "tier": 2,
            "direction": "sponsor_changed",
            "old_value": master_trial.get("sponsor_name"),
            "new_value": snapshot_trial.get("sponsor_name"),
            "field": "sponsor_name",
        })

    # ── Sites changed (Tier 2) ──────────────────────────────────────
    if "facility_count" in changed_fields:
        cat = _categorize_sites_change(
            master_trial.get("facility_count"),
            snapshot_trial.get("facility_count"),
        )
        if cat:
            categories.append(cat)

    # ── Phase change within same NCT (rare, Tier 1) ─────────────────
    if "phase" in changed_fields:
        old_phase = master_trial.get("phase") or ""
        new_phase = snapshot_trial.get("phase") or ""

        # Detect CT.gov format change: "PHASE1/PHASE2" → "PHASE1"
        # If old contains "/" and new is one of the components → formatting only
        is_format_change = (
            "/" in old_phase
            and new_phase in [p.strip() for p in old_phase.split("/")]
        )

        if is_format_change:
            categories.append({
                "category": "phase_format_change",
                "tier": 3,
                "direction": f"{old_phase}_to_{new_phase}",
                "old_value": old_phase,
                "new_value": new_phase,
                "field": "phase",
                "note": "CT.gov combined-phase display change, not a real phase transition",
            })
        else:
            categories.append({
                "category": "phase_changed",
                "tier": 1,
                "direction": f"{old_phase}_to_{new_phase}",
                "old_value": old_phase,
                "new_value": new_phase,
                "field": "phase",
            })

    # ── Reclassification check (Tier 3) ─────────────────────────────
    reclass = _categorize_reclassification(
        master_trial.get("therapeutic_area"),
        snapshot_trial.get("therapeutic_area"),
        master_trial.get("modality"),
        snapshot_trial.get("modality"),
        "conditions" in changed_fields,
        "interventions_text" in changed_fields,
    )
    if reclass:
        categories.append(reclass)

    # ── Metadata only (Tier 3) ──────────────────────────────────────
    # If no business categories assigned, tag as metadata_only
    if not categories and business_fields:
        # Has changes but only in low-signal fields
        categories.append({
            "category": "metadata_only",
            "tier": 3,
            "direction": None,
            "fields_changed": sorted(business_fields),
        })
    elif not categories and not business_fields:
        # Only last_update_posted_date changed
        categories.append({
            "category": "metadata_only",
            "tier": 3,
            "direction": "date_only",
            "fields_changed": ["last_update_posted_date"],
        })

    return categories


# ═══════════════════════════════════════════════════════════════════════════
# STEP 2: CLASSIFY NEW TRIALS
# ═══════════════════════════════════════════════════════════════════════════

def categorize_new_trial(trial: Dict) -> List[Dict]:
    """Categorize a trial that's not in the master DB."""
    status = trial.get("overall_status", "")

    if status in ACTIVE_STATUSES:
        return [{
            "category": "new_registration",
            "tier": 1,
            "direction": None,
            "status": status,
            "phase": trial.get("phase"),
        }]
    else:
        # Terminal status — was in CT.gov before, not in our active master
        return [{
            "category": "inactive_update",
            "tier": 3,
            "direction": None,
            "status": status,
            "phase": trial.get("phase"),
            "note": "Trial has terminal status; not added to active master",
        }]


# ═══════════════════════════════════════════════════════════════════════════
# STEP 8: CHANGELOG REPORT
# ═══════════════════════════════════════════════════════════════════════════

def generate_changelog(enriched_trials: List[Dict], metadata: Dict) -> Dict:
    """Generate structured changelog from enriched trials."""
    report = {
        "generated_at": datetime.now(tz=_UTC).isoformat(),
        "window": metadata.get("window", "unknown"),
        "summary": {},
        "tier1": [],
        "tier2": [],
        "tier3": [],
        "detail": [],
    }

    # Counters
    cat_counter = Counter()
    direction_counter = Counter()
    new_active = 0
    new_inactive = 0
    existing_with_changes = 0
    metadata_only_count = 0

    for trial in enriched_trials:
        update_type = trial.get("update_type")
        cats = trial.get("update_categories", [])
        nct = trial.get("nct_id", "?")

        for c in cats:
            cat_name = c["category"]
            cat_counter[cat_name] += 1
            if c.get("direction"):
                direction_counter[f"{cat_name}:{c['direction']}"] += 1

        if update_type == "new":
            if any(c["category"] == "new_registration" for c in cats):
                new_active += 1
            else:
                new_inactive += 1
        elif update_type == "new_inactive":
            new_inactive += 1
        elif update_type == "existing":
            if any(c["category"] == "metadata_only" for c in cats) and len(cats) == 1:
                metadata_only_count += 1
            else:
                existing_with_changes += 1

        # Detail row
        detail_row = {
            "nct_id": nct,
            "update_type": update_type,
            "categories": [c["category"] for c in cats],
            "tier1_categories": [c for c in cats if c.get("tier") == 1],
            "sponsor": trial.get("sponsor_name"),
            "therapeutic_area": trial.get("therapeutic_area"),
            "modality": trial.get("modality"),
            "phase": trial.get("phase"),
        }
        report["detail"].append(detail_row)

    # Summary
    report["summary"] = {
        "total_trials": len(enriched_trials),
        "new_active_registrations": new_active,
        "new_inactive_updates": new_inactive,
        "existing_with_business_changes": existing_with_changes,
        "existing_metadata_only": metadata_only_count,
        "category_counts": dict(cat_counter.most_common()),
        "direction_counts": dict(direction_counter.most_common()),
    }

    # Tier summaries
    tier1_cats = [
        "new_registration", "status_to_recruiting", "status_to_completed",
        "status_to_stopped", "status_to_active_not_recruiting",
        "status_changed", "new_arm_added", "phase_changed",
    ]
    tier2_cats = [
        "enrollment_change", "enrollment_type_change", "intervention_changed",
        "endpoint_changed", "secondary_endpoint_changed",
        "sponsor_changed", "sites_changed",
    ]
    tier3_cats = ["metadata_only", "reclassified", "inactive_update", "phase_format_change"]

    for cat_name in tier1_cats:
        if cat_counter[cat_name] > 0:
            # Get direction breakdown
            dirs = {k.split(":", 1)[1]: v for k, v in direction_counter.items()
                    if k.startswith(f"{cat_name}:")}
            report["tier1"].append({
                "category": cat_name,
                "count": cat_counter[cat_name],
                "directions": dirs,
            })

    for cat_name in tier2_cats:
        if cat_counter[cat_name] > 0:
            dirs = {k.split(":", 1)[1]: v for k, v in direction_counter.items()
                    if k.startswith(f"{cat_name}:")}
            report["tier2"].append({
                "category": cat_name,
                "count": cat_counter[cat_name],
                "directions": dirs,
            })

    for cat_name in tier3_cats:
        if cat_counter[cat_name] > 0:
            dirs = {k.split(":", 1)[1]: v for k, v in direction_counter.items()
                    if k.startswith(f"{cat_name}:")}
            report["tier3"].append({
                "category": cat_name,
                "count": cat_counter[cat_name],
                "directions": dirs,
            })

    return report


def print_changelog(report: Dict):
    """Print human-readable changelog."""
    summary = report["summary"]
    W = 60

    print(f"\n{'='*W}")
    print(f"  ALEXIS UPDATE CHANGELOG")
    print(f"  Window: {report.get('window', '?')}")
    print(f"  Generated: {report['generated_at']}")
    print(f"{'='*W}")

    print(f"\n  Total trials processed: {summary['total_trials']:,}")
    print(f"    New active registrations:    {summary['new_active_registrations']:,}")
    print(f"    New inactive updates:        {summary['new_inactive_updates']:,}")
    print(f"    Existing w/ business changes:{summary['existing_with_business_changes']:,}")
    print(f"    Existing metadata only:      {summary['existing_metadata_only']:,}")

    # Tier 1
    if report["tier1"]:
        print(f"\n{'─'*W}")
        print(f"  TIER 1 — HIGH IMPACT")
        print(f"{'─'*W}")
        for item in report["tier1"]:
            dirs_str = ""
            if item["directions"]:
                parts = [f"{v} {k}" for k, v in item["directions"].items()]
                dirs_str = f"  ({', '.join(parts)})"
            print(f"    {item['category']:<35s} {item['count']:>5,}{dirs_str}")

    # Tier 2
    if report["tier2"]:
        print(f"\n{'─'*W}")
        print(f"  TIER 2 — MEDIUM IMPACT")
        print(f"{'─'*W}")
        for item in report["tier2"]:
            dirs_str = ""
            if item["directions"]:
                parts = [f"{v} {k}" for k, v in item["directions"].items()]
                dirs_str = f"  ({', '.join(parts)})"
            print(f"    {item['category']:<35s} {item['count']:>5,}{dirs_str}")

    # Tier 3
    if report["tier3"]:
        print(f"\n{'─'*W}")
        print(f"  TIER 3 — SYSTEM")
        print(f"{'─'*W}")
        for item in report["tier3"]:
            dirs_str = ""
            if item["directions"]:
                parts = [f"{v} {k}" for k, v in item["directions"].items()]
                dirs_str = f"  ({', '.join(parts)})"
            print(f"    {item['category']:<35s} {item['count']:>5,}{dirs_str}")

    print()


# ═══════════════════════════════════════════════════════════════════════════
# INSTRUCTION FILE GENERATOR
# ═══════════════════════════════════════════════════════════════════════════

# Fields to strip from instruction records (internal enrichment, not master data)
_ENRICHMENT_FIELDS = {"update_type", "update_categories", "field_diffs"}


def _strip_enrichment(trial: Dict) -> Dict:
    """Return trial record without categorizer enrichment fields."""
    return {k: v for k, v in trial.items() if k not in _ENRICHMENT_FIELDS}


def generate_instructions(
    enriched_trials: List[Dict],
    master_index: Dict[str, Dict],
    pulse_window: str,
    base_master: str,
    sequence: int,
) -> Dict:
    """
    Generate a compact instruction file from enriched trials.

    Three operations:
      add    — full trial record for new active registrations
      patch  — only changed fields for existing trials with diffs
      remove — NCT IDs for trials that moved to terminal status

    Instruction files are designed to be replayed in sequence against a
    base master DB to produce a new quarterly master.
    """
    instructions = {
        "metadata": {
            "pulse_window": pulse_window,
            "base_master": base_master,
            "sequence": sequence,
            "generated_at": datetime.now(tz=_UTC).isoformat(),
            "schema_version": "1.0",
        },
        "add": [],
        "patch": {},
        "remove": [],
        "stats": {},
    }

    add_count = 0
    patch_count = 0
    patch_fields_total = 0
    remove_count = 0
    skip_count = 0

    for trial in enriched_trials:
        nct = trial.get("nct_id")
        cats = trial.get("update_categories", [])
        cat_names = {c["category"] for c in cats}
        update_type = trial.get("update_type")

        if update_type == "new":
            if "new_registration" in cat_names:
                # ADD: full record, strip enrichment fields
                instructions["add"].append(_strip_enrichment(trial))
                add_count += 1
            else:
                # inactive_update — skip, don't pollute master
                skip_count += 1

        elif update_type == "existing":
            field_diffs = trial.get("field_diffs", [])

            # Check if trial moved to terminal status → REMOVE
            status_cats = {"status_to_completed", "status_to_stopped"}
            if status_cats & cat_names:
                new_status = trial.get("overall_status", "")
                if new_status in TERMINAL_STATUSES:
                    instructions["remove"].append(nct)
                    remove_count += 1
                    continue

            # PATCH: only changed fields
            if field_diffs:
                patch = {}
                for diff in field_diffs:
                    field = diff["field"]
                    patch[field] = diff["new"]
                if patch:
                    instructions["patch"][nct] = patch
                    patch_count += 1
                    patch_fields_total += len(patch)

    instructions["stats"] = {
        "add": add_count,
        "patch": patch_count,
        "patch_fields_total": patch_fields_total,
        "patch_fields_avg": round(patch_fields_total / patch_count, 1) if patch_count else 0,
        "remove": remove_count,
        "skip_inactive": skip_count,
    }

    return instructions


def print_instructions_summary(instructions: Dict):
    """Print a compact summary of the instruction file."""
    stats = instructions["stats"]
    meta = instructions["metadata"]
    W = 60

    print(f"\n{'='*W}")
    print(f"  MASTER DB INSTRUCTION FILE")
    print(f"  Window: {meta['pulse_window']}")
    print(f"  Base:   {meta['base_master']}")
    print(f"  Seq:    {meta['sequence']}")
    print(f"{'='*W}")
    print(f"    ADD     {stats['add']:>5,}  trials  (new active registrations)")
    print(f"    PATCH   {stats['patch']:>5,}  trials  ({stats['patch_fields_total']:,} fields, avg {stats['patch_fields_avg']:.1f}/trial)")
    print(f"    REMOVE  {stats['remove']:>5,}  trials  (moved to terminal status)")
    print(f"    SKIP    {stats['skip_inactive']:>5,}  trials  (inactive updates, not added)")

    # Size estimate
    raw = json.dumps(instructions, default=str)
    kb = len(raw) / 1024
    print(f"\n    Estimated size: {kb:,.0f} KB")
    print()


def apply_instructions(master_trials: Dict[str, Dict], instructions: Dict) -> Dict[str, Dict]:
    """
    Apply a single instruction file to a master DB dict.
    Returns the modified master_trials dict (mutates in place).
    """
    for trial in instructions.get("add", []):
        nct = trial["nct_id"]
        master_trials[nct] = trial

    for nct, patch_fields in instructions.get("patch", {}).items():
        if nct in master_trials:
            master_trials[nct].update(patch_fields)

    for nct in instructions.get("remove", []):
        master_trials.pop(nct, None)

    return master_trials


def replay_all_instructions(
    base_master_path: str,
    instruction_paths: List[str],
    output_path: str,
):
    """
    Replay instruction files in sequence against a base master to produce
    a new quarterly master DB.

    Usage:
        replay_all_instructions(
            "master_DB_2025_Q4.json",
            sorted(glob("instructions_*.json")),  # chronological
            "master_DB_2026_Q1.json",
        )
    """
    with open(base_master_path, "r", encoding="utf-8") as f:
        master_data = json.load(f)
    master_trials = {t["nct_id"]: t for t in master_data.get("trials", [])}

    print(f"Base master: {len(master_trials):,} trials")

    for path in instruction_paths:
        with open(path, "r", encoding="utf-8") as f:
            inst = json.load(f)
        meta = inst.get("metadata", {})
        stats = inst.get("stats", {})
        seq = meta.get("sequence", "?")

        before = len(master_trials)
        apply_instructions(master_trials, inst)
        after = len(master_trials)

        print(f"  seq {seq}: +{stats.get('add',0)} add, "
              f"{stats.get('patch',0)} patch, "
              f"-{stats.get('remove',0)} remove → {after:,} trials")

    # Save new master
    new_master = {
        "metadata": {
            "generated_at": datetime.now(tz=_UTC).isoformat(),
            "base": base_master_path,
            "instructions_applied": len(instruction_paths),
        },
        "trials": list(master_trials.values()),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(new_master, f, indent=2, default=str)

    print(f"\nNew master: {len(master_trials):,} trials → {output_path}")
    return master_trials


# ═══════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="ALEXIS Update Categorizer")
    parser.add_argument("--master", required=True, help="Path to master_DB.json")
    parser.add_argument("--snapshot", required=True, help="Path to pulse snapshot JSON")
    parser.add_argument("--drug-only", action="store_true",
                        help="Only process trials where is_drug_trial=True")
    parser.add_argument("--output-enriched", help="Write enriched snapshot JSON")
    parser.add_argument("--output-changelog", help="Write changelog JSON")
    parser.add_argument("--output-instructions", help="Write master DB instruction file JSON")
    parser.add_argument("--base-master", default="master_DB_2025_Q4",
                        help="Name of the base master DB for instruction file (default: master_DB_2025_Q4)")
    parser.add_argument("--sequence", type=int, default=1,
                        help="Instruction file sequence number (for replay ordering)")
    parser.add_argument("--quiet", action="store_true", help="Suppress console output")
    args = parser.parse_args()

    # ── Step 1: Load & Index ────────────────────────────────────────
    master_path = Path(args.master)
    snapshot_path = Path(args.snapshot)

    for p in (master_path, snapshot_path):
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            sys.exit(1)

    if not args.quiet:
        print(f"Loading master:   {master_path}")
    with master_path.open("r", encoding="utf-8") as f:
        master_data = json.load(f)
    master_index = {t["nct_id"]: t for t in master_data.get("trials", [])}
    if not args.quiet:
        print(f"  {len(master_index):,} trials")

    if not args.quiet:
        print(f"Loading snapshot:  {snapshot_path}")
    with snapshot_path.open("r", encoding="utf-8") as f:
        snap_data = json.load(f)
    snap_trials = {t["nct_id"]: t for t in snap_data.get("trials", [])}
    if not args.quiet:
        print(f"  {len(snap_trials):,} trials")

    # Drug-only filter
    if args.drug_only:
        def _is_drug(t):
            return t.get("is_drug_trial") is True

        snap_filtered = {nct: t for nct, t in snap_trials.items()
                         if _is_drug(t) or _is_drug(master_index.get(nct, {}))}
        master_filtered = {nct: t for nct, t in master_index.items() if _is_drug(t)}

        if not args.quiet:
            print(f"\n  --drug-only filter:")
            print(f"    Master:   {len(master_index):,} → {len(master_filtered):,}")
            print(f"    Snapshot: {len(snap_trials):,} → {len(snap_filtered):,}")

        master_index = master_filtered
        snap_trials = snap_filtered

    # ── Step 2: Split New vs. Existing ──────────────────────────────
    enriched_trials = []

    new_count = 0
    new_inactive_count = 0
    existing_count = 0

    for nct, snap_trial in snap_trials.items():
        enriched = deepcopy(snap_trial)

        if nct not in master_index:
            # Not in the active-universe master DB.
            # If overall_status is terminal (COMPLETED / TERMINATED /
            # WITHDRAWN / SUSPENDED), this is a retrospective registration:
            # the trial was already finished when CT.gov first surfaced it.
            # Tag update_type="new_inactive" so charts filtering on
            # update_type == "new" automatically exclude these.
            cats = categorize_new_trial(snap_trial)
            enriched["update_categories"] = cats
            enriched["field_diffs"] = []
            status = (snap_trial.get("overall_status") or "").upper()
            if status in TERMINAL_STATUSES:
                enriched["update_type"] = "new_inactive"
                new_inactive_count += 1
            else:
                enriched["update_type"] = "new"
                new_count += 1
        else:
            # Existing trial — diff
            master_trial = master_index[nct]
            raw_diffs = diff_trial(master_trial, snap_trial)

            enriched["update_type"] = "existing"
            enriched["field_diffs"] = [
                {"field": d["field"], "tier": d["tier"],
                 "old": d["old"], "new": d["new"],
                 **({k: d[k] for k in ("delta", "delta_pct") if k in d})}
                for d in raw_diffs
            ]
            enriched["update_categories"] = categorize_trial_changes(
                master_trial, snap_trial, raw_diffs
            )
            existing_count += 1

        enriched_trials.append(enriched)

    if not args.quiet:
        print(f"\n  Processed: {new_count:,} new (active) + "
              f"{new_inactive_count:,} new_inactive (retrospective completed) + "
              f"{existing_count:,} existing = {len(enriched_trials):,} total")

    # ── Step 7: Tag & Save (enriched snapshot) ──────────────────────
    if args.output_enriched:
        enriched_path = Path(args.output_enriched)
        enriched_output = {
            "metadata": {
                "generated_at": datetime.now(tz=_UTC).isoformat(),
                "master_source": str(master_path),
                "snapshot_source": str(snapshot_path),
                "drug_only": args.drug_only,
                "trial_count": len(enriched_trials),
            },
            "trials": enriched_trials,
        }
        with enriched_path.open("w", encoding="utf-8") as f:
            json.dump(enriched_output, f, indent=2, default=str)
        if not args.quiet:
            print(f"\n  Enriched snapshot → {enriched_path}")

    # ── Step 8: Generate Changelog ──────────────────────────────────
    # Derive window from snapshot filename if possible
    snap_name = snapshot_path.stem  # e.g. "2026-02-21_2026-02-24_v1"
    window = snap_name.replace("_v1", "").replace("_v2", "").replace("_v3", "")

    changelog = generate_changelog(enriched_trials, {"window": window})

    if not args.quiet:
        print_changelog(changelog)

    if args.output_changelog:
        cl_path = Path(args.output_changelog)
        with cl_path.open("w", encoding="utf-8") as f:
            json.dump(changelog, f, indent=2, default=str)
        if not args.quiet:
            print(f"  Changelog → {cl_path}")

    # ── Step 9: Generate Instruction File ───────────────────────────
    instructions = generate_instructions(
        enriched_trials,
        master_index,
        pulse_window=window,
        base_master=args.base_master,
        sequence=args.sequence,
    )

    if not args.quiet:
        print_instructions_summary(instructions)

    if args.output_instructions:
        inst_path = Path(args.output_instructions)
        with inst_path.open("w", encoding="utf-8") as f:
            json.dump(instructions, f, indent=2, default=str)
        if not args.quiet:
            print(f"  Instructions → {inst_path}")

    if not args.quiet:
        print("Done.")


if __name__ == "__main__":
    main()
