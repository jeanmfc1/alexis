"""
Prints all summaries from an existing active universe snapshot.

Usage:
    python -m pipelines.print_active_universe_summary
    python -m pipelines.print_active_universe_summary --snapshot storage/snapshots/clinical_trials_v2/active_universe/2026_feb_w4.json
"""

import json
import argparse
from pathlib import Path

from analytics.summary_v2 import drug_modality_summary, drug_therapeutic_area_summary


def print_summary(summary: dict) -> None:

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
    for k, v in sorted(summary.get("drug_modality_summary", {}).items()):
        print(f"  {k:25} | {v}")

    print("\nDrug trials by therapeutic area:")
    for k, v in sorted(summary.get("drug_therapeutic_area_summary", {}).items()):
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
    for k, v in summary.get("drug_modality_provenance", {}).items():
        print(f"  {k:20} | {v}")

    print("\nTherapeutic area provenance (drug trials):")
    for k, v in summary.get("drug_ta_provenance", {}).items():
        print(f"  {k:20} | {v}")

    print("\nDrug study intent:")
    for k, v in summary.get("drug_study_intent", {}).items():
        print(f"  {k:15} | {v}")

    print("\nDrug mesh-missing condition (DATA COMPLETENESS, NOT INTENT):")
    for k, v in summary.get("drug_mesh_missing_condition", {}).items():
        print(f"  {k:25} | {v}")

    print("\nNon-disease drug study subtypes:")
    for k, v in sorted(summary.get("non_disease_drug_subtypes", {}).items()):
        print(f"  {k:25} | {v}")

    print("\nTA × Phase:")
    for ta, phases in summary.get("ta_by_phase", {}).items():
        for phase, count in phases.items():
            print(f"  {ta:20} | {phase:10} | {count}")

    print("\nModality × Phase:")
    for mod, phases in summary.get("modality_by_phase", {}).items():
        for phase, count in phases.items():
            print(f"  {mod:20} | {phase:10} | {count}")

    print("\nTA × Sponsor class:")
    for ta, sponsors in summary.get("ta_by_sponsor_class", {}).items():
        for sponsor, count in sponsors.items():
            print(f"  {ta:20} | {sponsor:15} | {count}")

    print("\nMulti-TA rate by phase:")
    for phase, rate in summary.get("multi_ta_rate_by_phase", {}).items():
        print(f"  {phase:10} | {rate:.2%}")

    print("\nNon-disease study categories:")
    for k, v in summary.get("non_disease_study_categories", {}).items():
        print(f"  {k:25} | {v}")


def main():
    parser = argparse.ArgumentParser(description="Print summaries from an active universe snapshot")
    parser.add_argument(
        "--snapshot",
        default=None,
        help="Path to snapshot JSON (default: latest in storage/snapshots/clinical_trials_v2/active_universe/)"
    )
    args = parser.parse_args()

    if args.snapshot:
        snapshot_path = Path(args.snapshot)
    else:
        # Auto-find latest snapshot
        base = Path("storage/snapshots/clinical_trials_v2/active_universe")
        snapshots = sorted(base.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not snapshots:
            print(f"No snapshots found in {base}")
            return
        snapshot_path = snapshots[0]
        print(f"Using latest snapshot: {snapshot_path}")

    print(f"Loading {snapshot_path}...")
    data = json.loads(snapshot_path.read_text())
    summary = data.get("summary", {})

    if not summary:
        print("No summary found in snapshot.")
        return

    print_summary(summary)


if __name__ == "__main__":
    main()
