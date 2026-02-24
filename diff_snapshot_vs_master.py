"""
diff_snapshot_vs_master.py
──────────────────────────
Compares a pulse snapshot (trials updated in a window) against the master DB
(all active trials) and produces a diagnostic diff report.

Since every trial in the snapshot is either new or updated, this script:
  1. Identifies NEW trials (in snapshot but not in master)
  2. For EXISTING trials, diffs every comparable field and reports changes
  3. Summarizes change frequency per field

Usage:
  python diff_snapshot_vs_master.py \
      --master  "storage/snapshots/clinical_trials_v2/active_universe/master_DB.json" \
      --snapshot "storage/snapshots/clinical_trials_v2/last_update/2026-02-22_2026-02-24_v3.json"

Options:
  --top N        Show top N most-changed fields (default: 20)
  --examples N   Show N example diffs per field (default: 3)
  --output FILE  Write full diff to JSON file
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Fields to compare ───────────────────────────────────────────────────────

# Tier 1: high-signal fields (status, enrollment, phase)
TIER1_FIELDS = [
    "overall_status", "phase", "enrollment", "enrollment_type", "why_stopped",
]

# Tier 2: protocol-level fields
TIER2_FIELDS = [
    "sponsor_name", "sponsor_class", "study_type",
    "start_date", "completion_date", "primary_completion_date",
    "primary_outcomes", "secondary_outcomes",
    "facilities", "facility_count",
]

# Tier 3: classification / metadata
TIER3_FIELDS = [
    "title", "conditions",
    "interventions_text", "arm_group_map",
    "therapeutic_area", "is_drug_trial", "modality",
    "study_intent", "study_category",
]

ALL_COMPARE_FIELDS = TIER1_FIELDS + TIER2_FIELDS + TIER3_FIELDS


# ── Comparison helpers ──────────────────────────────────────────────────────

def _normalize_for_compare(val: Any) -> Any:
    """Normalize values for comparison (handle None vs [] vs 0 edge cases)."""
    if val is None:
        return None
    if isinstance(val, list) and len(val) == 0:
        return None  # treat [] same as None for missing data
    if isinstance(val, dict) and len(val) == 0:
        return None
    return val


def _is_meaningful_change(field: str, old: Any, new: Any) -> bool:
    """Filter out noise: only report changes where both sides aren't empty."""
    old_n = _normalize_for_compare(old)
    new_n = _normalize_for_compare(new)
    if old_n == new_n:
        return False
    # If master had no data (pre-patch field was missing) and snapshot has data,
    # that's a "populated" not a real "change" — still worth reporting but flagged
    return True


def _summarize_value(val: Any, max_len: int = 80) -> str:
    """Short string repr for display."""
    if val is None:
        return "None"
    if isinstance(val, list):
        if len(val) == 0:
            return "[]"
        if len(val) <= 3:
            s = json.dumps(val, default=str)
        else:
            s = f"[{len(val)} items]"
        return s[:max_len]
    if isinstance(val, dict):
        if len(val) == 0:
            return "{}"
        s = json.dumps(val, default=str)
        return s[:max_len]
    s = str(val)
    return s[:max_len]


def diff_trial(
    master_trial: Dict[str, Any],
    snapshot_trial: Dict[str, Any],
    fields: List[str],
) -> List[Dict[str, Any]]:
    """
    Compare two trial dicts field by field.
    Returns list of change records.
    """
    changes = []
    for field in fields:
        old = master_trial.get(field)
        new = snapshot_trial.get(field)
        if _is_meaningful_change(field, old, new):
            change = {
                "field": field,
                "old": old,
                "new": new,
            }
            # Add delta for numeric fields
            if isinstance(old, (int, float)) and isinstance(new, (int, float)):
                change["delta"] = new - old
                if old != 0:
                    change["delta_pct"] = f"{100 * (new - old) / old:+.1f}%"
            changes.append(change)
    return changes


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Diff snapshot vs master DB")
    parser.add_argument("--master", required=True, help="Path to master_DB.json")
    parser.add_argument("--snapshot", required=True, help="Path to snapshot JSON")
    parser.add_argument("--top", type=int, default=20, help="Top N changed fields to show")
    parser.add_argument("--examples", type=int, default=3, help="Example diffs per field")
    parser.add_argument("--output", help="Write full diff to JSON file")
    parser.add_argument("--drug-only", action="store_true", help="Only compare trials where is_drug_trial=True")
    args = parser.parse_args()

    master_path = Path(args.master)
    snapshot_path = Path(args.snapshot)

    for p in (master_path, snapshot_path):
        if not p.exists():
            print(f"ERROR: {p} not found")
            sys.exit(1)

    # Load
    print(f"Loading master:   {master_path}")
    with master_path.open("r", encoding="utf-8") as f:
        master_data = json.load(f)
    master_trials = {t["nct_id"]: t for t in master_data.get("trials", [])}
    print(f"  {len(master_trials):,} trials")

    print(f"Loading snapshot:  {snapshot_path}")
    with snapshot_path.open("r", encoding="utf-8") as f:
        snap_data = json.load(f)
    snap_trials = {t["nct_id"]: t for t in snap_data.get("trials", [])}
    print(f"  {len(snap_trials):,} trials")

    # ── Drug-only filter ────────────────────────────────────────────────
    if args.drug_only:
        # A trial is a drug trial if EITHER source says so
        def _is_drug(t: Dict[str, Any]) -> bool:
            return t.get("is_drug_trial") is True

        snap_drug = {nct: t for nct, t in snap_trials.items()
                     if _is_drug(t) or _is_drug(master_trials.get(nct, {}))}
        master_drug = {nct: t for nct, t in master_trials.items() if _is_drug(t)}

        print(f"\n  --drug-only filter applied:")
        print(f"    Master:   {len(master_trials):,} → {len(master_drug):,} drug trials")
        print(f"    Snapshot: {len(snap_trials):,} → {len(snap_drug):,} drug trials")

        master_trials = master_drug
        snap_trials = snap_drug

    # ── Classify trials ─────────────────────────────────────────────────
    new_ncts = []
    existing_ncts = []
    for nct in snap_trials:
        if nct in master_trials:
            existing_ncts.append(nct)
        else:
            new_ncts.append(nct)

    print(f"\n{'='*60}")
    print(f"SNAPSHOT BREAKDOWN")
    print(f"{'='*60}")
    print(f"  Total in snapshot:  {len(snap_trials):,}")
    print(f"  New (not in master): {len(new_ncts):,}")
    print(f"  Existing (in master): {len(existing_ncts):,}")

    # ── Diff existing trials ────────────────────────────────────────────
    field_change_count = Counter()
    field_examples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    trials_with_changes = 0
    trials_no_changes = 0
    all_diffs: Dict[str, List[Dict[str, Any]]] = {}

    for nct in existing_ncts:
        changes = diff_trial(master_trials[nct], snap_trials[nct], ALL_COMPARE_FIELDS)
        if changes:
            trials_with_changes += 1
            all_diffs[nct] = changes
            for c in changes:
                f = c["field"]
                field_change_count[f] += 1
                if len(field_examples[f]) < args.examples:
                    field_examples[f].append({
                        "nct_id": nct,
                        "old": _summarize_value(c["old"]),
                        "new": _summarize_value(c["new"]),
                        "delta": c.get("delta"),
                        "delta_pct": c.get("delta_pct"),
                    })
        else:
            trials_no_changes += 1

    print(f"\n{'='*60}")
    print(f"EXISTING TRIAL DIFFS ({len(existing_ncts):,} trials)")
    print(f"{'='*60}")
    print(f"  With changes:    {trials_with_changes:,}")
    print(f"  No changes:      {trials_no_changes:,}")

    # ── Field-level summary ─────────────────────────────────────────────
    if field_change_count:
        print(f"\n{'='*60}")
        print(f"FIELD CHANGE FREQUENCY (top {args.top})")
        print(f"{'='*60}")
        print(f"  {'Field':<32s} {'Count':>6s}  {'%':>6s}  Tier")
        print(f"  {'-'*32} {'-'*6}  {'-'*6}  {'-'*4}")

        for field, count in field_change_count.most_common(args.top):
            pct = 100 * count / len(existing_ncts)
            if field in TIER1_FIELDS:
                tier = "T1"
            elif field in TIER2_FIELDS:
                tier = "T2"
            else:
                tier = "T3"
            print(f"  {field:<32s} {count:>6,}  {pct:>5.1f}%  {tier}")

    # ── Example diffs per field ─────────────────────────────────────────
    if field_change_count:
        print(f"\n{'='*60}")
        print(f"EXAMPLE CHANGES (up to {args.examples} per field)")
        print(f"{'='*60}")
        for field, _ in field_change_count.most_common(args.top):
            examples = field_examples[field]
            if not examples:
                continue
            print(f"\n  {field}:")
            for ex in examples:
                delta_str = ""
                if ex.get("delta") is not None:
                    delta_str = f"  (delta: {ex['delta']}"
                    if ex.get("delta_pct"):
                        delta_str += f", {ex['delta_pct']}"
                    delta_str += ")"
                print(f"    {ex['nct_id']}:  {ex['old']}  →  {ex['new']}{delta_str}")

    # ── New trials summary ──────────────────────────────────────────────
    if new_ncts:
        print(f"\n{'='*60}")
        print(f"NEW TRIALS ({len(new_ncts):,})")
        print(f"{'='*60}")

        # Status breakdown
        status_counts = Counter()
        phase_counts = Counter()
        for nct in new_ncts:
            t = snap_trials[nct]
            status_counts[t.get("overall_status", "Unknown")] += 1
            phase_counts[t.get("phase", "Unknown")] += 1

        print(f"\n  By status:")
        for s, c in status_counts.most_common():
            print(f"    {str(s or 'None'):<30s} {c:>5,}")

        print(f"\n  By phase:")
        for p, c in phase_counts.most_common():
            print(f"    {str(p or 'None'):<30s} {c:>5,}")

        print(f"\n  First 10:")
        for nct in new_ncts[:10]:
            t = snap_trials[nct]
            status = str(t.get('overall_status') or '?')
            phase = str(t.get('phase') or '?')
            title = str(t.get('title') or '')[:60]
            print(f"    {nct}  {status:<15s}  {phase:<12s}  {title}")

    # ── Trials with most changes ────────────────────────────────────────
    if all_diffs:
        print(f"\n{'='*60}")
        print(f"TRIALS WITH MOST CHANGES (top 10)")
        print(f"{'='*60}")
        ranked = sorted(all_diffs.items(), key=lambda x: len(x[1]), reverse=True)
        for nct, changes in ranked[:10]:
            changed_fields = [c["field"] for c in changes]
            t1_changes = [f for f in changed_fields if f in TIER1_FIELDS]
            print(f"  {nct}  ({len(changes)} changes, {len(t1_changes)} tier-1):  {', '.join(changed_fields)}")

    # ── Write full diff JSON ────────────────────────────────────────────
    if args.output:
        output_path = Path(args.output)
        report = {
            "summary": {
                "master_count": len(master_trials),
                "snapshot_count": len(snap_trials),
                "new_trials": len(new_ncts),
                "existing_trials": len(existing_ncts),
                "with_changes": trials_with_changes,
                "no_changes": trials_no_changes,
            },
            "field_change_counts": dict(field_change_count.most_common()),
            "new_trial_ids": new_ncts,
            "diffs": {
                nct: [
                    {
                        "field": c["field"],
                        "old": c["old"],
                        "new": c["new"],
                        **({"delta": c["delta"]} if "delta" in c else {}),
                        **({"delta_pct": c["delta_pct"]} if "delta_pct" in c else {}),
                    }
                    for c in changes
                ]
                for nct, changes in all_diffs.items()
            },
        }
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nFull diff written to: {output_path}")

    print(f"\nDone.")


if __name__ == "__main__":
    main()
