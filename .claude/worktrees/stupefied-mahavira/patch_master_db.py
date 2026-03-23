"""
patch_master_db.py
──────────────────
Reads 4 AACT flat files and patches master_BD.json with the 14 new
ClinicalTrialSignalV2 fields that were missing before the schema expansion.

AACT sources:
  studies.txt         → overall_status, enrollment, enrollment_type,
                        why_stopped, start_date, completion_date,
                        primary_completion_date
  sponsors.txt        → sponsor_name  (lead sponsor only)
  design_outcomes.txt → primary_outcomes, secondary_outcomes
  facilities.txt      → facilities, facility_count

Usage:
  python patch_master_db.py \\
      --master  storage/snapshots/clinical_trials_v2/active_universe/master_BD.json \\
      --aact    "storage/snapshots/clinical_trials_v2/active_universe/raw 02-21-26"

Options:
  --dry-run   Print stats without overwriting master_BD.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── AACT parsing ────────────────────────────────────────────────────────────

def _read_aact(path: Path) -> List[Dict[str, str]]:
    """Read a pipe-delimited AACT flat file into a list of dicts."""
    with path.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="|")
        return list(reader)


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


# ── Build lookup tables ─────────────────────────────────────────────────────

def build_studies_lookup(aact_dir: Path) -> Dict[str, Dict[str, Any]]:
    """
    studies.txt → dict keyed by nct_id with:
      overall_status, enrollment, enrollment_type, why_stopped,
      start_date, completion_date, primary_completion_date
    """
    rows = _read_aact(aact_dir / "studies.txt")
    lookup: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        nct = _safe_str(r.get("nct_id"))
        if not nct:
            continue
        lookup[nct] = {
            "overall_status": _safe_str(r.get("overall_status")),
            "enrollment": _safe_int(r.get("enrollment")),
            "enrollment_type": _safe_str(r.get("enrollment_type")),
            "why_stopped": _safe_str(r.get("why_stopped")),
            "start_date": _safe_str(r.get("start_date")),
            "completion_date": _safe_str(r.get("completion_date")),
            "primary_completion_date": _safe_str(r.get("primary_completion_date")),
        }
    return lookup


def build_sponsor_lookup(aact_dir: Path) -> Dict[str, str]:
    """sponsors.txt → dict keyed by nct_id with lead sponsor name."""
    rows = _read_aact(aact_dir / "sponsors.txt")
    lookup: Dict[str, str] = {}
    for r in rows:
        nct = _safe_str(r.get("nct_id"))
        role = _safe_str(r.get("lead_or_collaborator"))
        name = _safe_str(r.get("name"))
        if nct and name and role and role.lower() == "lead":
            lookup[nct] = name
    return lookup


def build_outcomes_lookup(aact_dir: Path) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """
    design_outcomes.txt → dict keyed by nct_id with:
      {"primary": [...], "secondary": [...]}
    Each entry: {type, measure, time_frame, description}
    """
    rows = _read_aact(aact_dir / "design_outcomes.txt")
    lookup: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for r in rows:
        nct = _safe_str(r.get("nct_id"))
        if not nct:
            continue
        otype = _safe_str(r.get("outcome_type"))
        measure = _safe_str(r.get("measure"))
        if not otype or not measure:
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
        # OTHER outcome types are skipped

    return lookup


def build_facilities_lookup(aact_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    """
    facilities.txt → dict keyed by nct_id with list of facility dicts:
      {name, city, state, country, status}
    """
    rows = _read_aact(aact_dir / "facilities.txt")
    lookup: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        nct = _safe_str(r.get("nct_id"))
        if not nct:
            continue
        if nct not in lookup:
            lookup[nct] = []
        lookup[nct].append({
            "name": _safe_str(r.get("name")),
            "city": _safe_str(r.get("city")),
            "state": _safe_str(r.get("state")),
            "country": _safe_str(r.get("country")),
            "status": _safe_str(r.get("status")),
        })
    return lookup




def build_eligibility_lookup(aact_dir: Path) -> Dict[str, str]:
    """eligibilities.txt -> dict keyed by nct_id with criteria text."""
    path = aact_dir / "eligibilities.txt"
    if not path.exists():
        print(f"  WARNING: eligibilities.txt not found, skipping eligibility_criteria")
        return {}
    rows = _read_aact(path)
    lookup: Dict[str, str] = {}
    for r in rows:
        nct = _safe_str(r.get("nct_id"))
        criteria = _safe_str(r.get("criteria"))
        if nct and criteria:
            lookup[nct] = criteria
    return lookup


# ── Patch logic ─────────────────────────────────────────────────────────────

def patch_trial(
    trial: Dict[str, Any],
    studies: Dict[str, Dict[str, Any]],
    sponsors: Dict[str, str],
    outcomes: Dict[str, Dict[str, List[Dict[str, Any]]]],
    facilities: Dict[str, List[Dict[str, Any]]],
    eligibility: Dict[str, str] = None,
) -> int:
    """
    Patch a single trial dict in-place. Returns count of fields updated.
    """
    nct = trial.get("nct_id")
    if not nct:
        return 0

    patched = 0

    # ── studies.txt fields ──
    s = studies.get(nct)
    if s:
        for field in (
            "overall_status", "enrollment", "enrollment_type",
            "why_stopped", "start_date", "completion_date",
            "primary_completion_date",
        ):
            trial[field] = s[field]
            patched += 1

    # ── sponsor_name ──
    sp = sponsors.get(nct)
    if sp is not None:
        trial["sponsor_name"] = sp
        patched += 1

    # ── outcomes ──
    oc = outcomes.get(nct)
    if oc:
        trial["primary_outcomes"] = oc["primary"]
        trial["secondary_outcomes"] = oc["secondary"]
    else:
        trial["primary_outcomes"] = []
        trial["secondary_outcomes"] = []
    patched += 2

    # ── facilities ──
    fac = facilities.get(nct)
    if fac:
        trial["facilities"] = fac
        trial["facility_count"] = len(fac)
    else:
        trial["facilities"] = []
        trial["facility_count"] = 0
    patched += 2

    # ── eligibility_criteria ──
    if eligibility is not None:
        ec = eligibility.get(nct)
        trial["eligibility_criteria"] = ec
        if ec:
            patched += 1

    # ── update categorization placeholders (ensure keys exist) ──
    for key, default in [
        ("update_type", None),
        ("update_categories", []),
        ("linked_from", None),
        ("outcome", None),
    ]:
        if key not in trial:
            trial[key] = default

    return patched


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Patch master_BD.json with AACT fields")
    parser.add_argument("--master", required=True, help="Path to master_BD.json")
    parser.add_argument("--aact", required=True, help="Path to AACT raw folder")
    parser.add_argument("--dry-run", action="store_true", help="Print stats only, don't overwrite")
    args = parser.parse_args()

    master_path = Path(args.master)
    aact_dir = Path(args.aact)

    # Validate paths
    if not master_path.exists():
        print(f"ERROR: master file not found: {master_path}")
        sys.exit(1)
    for fname in ("studies.txt", "sponsors.txt", "design_outcomes.txt", "facilities.txt"):
        if not (aact_dir / fname).exists():
            print(f"ERROR: missing AACT file: {aact_dir / fname}")
            sys.exit(1)

    # Load master
    print(f"Loading {master_path} ...")
    with master_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    trials = data.get("trials", [])
    print(f"  {len(trials)} trials in master")

    # Build lookups
    print("Parsing AACT files ...")
    studies = build_studies_lookup(aact_dir)
    print(f"  studies.txt:         {len(studies):,} rows")
    sponsors = build_sponsor_lookup(aact_dir)
    print(f"  sponsors.txt:        {len(sponsors):,} lead sponsors")
    outcomes = build_outcomes_lookup(aact_dir)
    print(f"  design_outcomes.txt: {len(outcomes):,} trials with outcomes")
    fac = build_facilities_lookup(aact_dir)
    print(f"  facilities.txt:      {len(fac):,} trials with facilities")
    elig = build_eligibility_lookup(aact_dir)
    print(f"  eligibilities.txt:   {len(elig):,} trials with eligibility criteria")

    # Patch
    print("Patching trials ...")
    matched = 0
    unmatched = []
    for trial in trials:
        nct = trial.get("nct_id")
        if nct in studies:
            matched += 1
        else:
            unmatched.append(nct)
        patch_trial(trial, studies, sponsors, outcomes, fac, elig)

    print(f"  Matched:   {matched} / {len(trials)}")
    if unmatched:
        print(f"  Unmatched: {len(unmatched)} (not in AACT flat files)")
        if len(unmatched) <= 10:
            for u in unmatched:
                print(f"    {u}")

    # Population check
    print("\nPost-patch population rates:")
    check_fields = [
        "overall_status", "enrollment", "enrollment_type", "why_stopped",
        "sponsor_name", "start_date", "completion_date", "primary_completion_date",
        "primary_outcomes", "secondary_outcomes", "facilities", "facility_count",
        "eligibility_criteria",
    ]
    for k in check_fields:
        filled = sum(1 for t in trials if t.get(k) not in (None, [], 0))
        print(f"  {k:30s} {filled:5d} / {len(trials)}  ({100 * filled / len(trials):.1f}%)")

    if args.dry_run:
        print("\n[DRY RUN] No file written.")
    else:
        print(f"\nWriting {master_path} ...")
        with master_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=False)
        print("Done.")


if __name__ == "__main__":
    main()
