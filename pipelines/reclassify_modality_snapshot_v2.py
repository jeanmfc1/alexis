# ALEXIS/pipelines/reclassify_modality_snapshot_v2.py

from __future__ import annotations

from tqdm import tqdm
import json
from pathlib import Path
from datetime import date
from typing import List
from policy.ta_policy import TA_NON_DISEASE, select_primary_ta

from classifiers.therapeutic_area import (
    assign_therapeutic_area,
    detect_therapeutic_area_evidence,
)
from classifiers.drug_non_drug_v2 import is_drug_trial_v2
from classifiers.trial_modality_v2 import assign_trial_modality_v2

from storage.models_v2 import ClinicalTrialSignalV2, MeshTermV2, InterventionV2
from storage.snapshots_io_v2 import save_trial_snapshot_v2, SnapshotMetadataV2

from analytics.summary_v2 import (
    ta_modality_counts_true_drugs,
    drug_trial_counts,
    info_flag_counts_true_drugs,
    drug_info_overview,
    intervention_type_summary_all_trials,
    study_type_summary_all_trials,
)

# -------------------------------------------------
# Snapshot loading
# -------------------------------------------------

def load_snapshot(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

# -------------------------------------------------
# Trial reconstruction (FIXED)
# -------------------------------------------------

def reconstruct_trials(raw_trials: List[dict]) -> List[ClinicalTrialSignalV2]:
    trials: List[ClinicalTrialSignalV2] = []

    for t in raw_trials:

        def mesh_list(key: str):
            return [
                MeshTermV2(id=m.get("id"), term=m.get("term"))
                for m in (t.get(key) or [])
            ]
        
        intervention_objs = [
            InterventionV2(
                name=iv.get("name"),
                type=iv.get("type"),
            )
            for iv in (t.get("interventions") or [])
        ]

        trial = ClinicalTrialSignalV2(
            nct_id=t.get("nct_id"),
            title=t.get("title"),
            study_type=t.get("study_type"),
            phase=t.get("phase"),
            sponsor_class=t.get("sponsor_class"),
            conditions=t.get("conditions") or [],
            first_posted_date=t.get("first_posted_date"),
            last_update_posted_date=t.get("last_update_posted_date"),
            interventions=intervention_objs,
            interventions_all=intervention_objs,   
            interventions_text=t.get("interventions_text") or [],
            arm_group_map=t.get("arm_group_map") or {},
            intervention_meshes=mesh_list("intervention_meshes"),
            intervention_mesh_ancestors=mesh_list("intervention_mesh_ancestors"),
            condition_meshes=mesh_list("condition_meshes"),
            condition_mesh_ancestors=mesh_list("condition_mesh_ancestors"),
            therapeutic_area=t.get("therapeutic_area"),
            is_drug_trial=t.get("is_drug_trial"),
            modality=t.get("modality"),
            info_flags=t.get("info_flags") or [],
        )

        trials.append(trial)

    return trials

# -------------------------------------------------
# Reclassification
# -------------------------------------------------

def reclassify_snapshot(
    snapshot_path: Path,
    output_base_dir: Path,
) -> Path:

    snapshot = load_snapshot(snapshot_path)
    raw_trials = snapshot.get("trials", [])
    old_metadata = snapshot.get("metadata", {})

    trials = reconstruct_trials(raw_trials)

    print(f"Loaded trials: {len(trials)}")

    # -------------------------------------------------
    # Re-run classifiers
    # -------------------------------------------------

    for t in tqdm(trials, desc="Classifying trials (v2)", unit="trial"):
        # --- Therapeutic Area (NEW LOGIC) ---

        # 1) Detect multi-TA using MeSH ancestry
        ta_evidence = detect_therapeutic_area_evidence(t)
        t.therapeutic_areas_detected = sorted(ta_evidence.keys())

        primary_ta = select_primary_ta(t.therapeutic_areas_detected)

        if primary_ta:
            t.therapeutic_area = primary_ta
        elif t.is_drug_trial and not t.condition_meshes:
            t.therapeutic_area = "Non-disease drug study"
        else:
            t.therapeutic_area = assign_therapeutic_area(t)

        # --- Drug / Modality (UNCHANGED) ---
        t.is_drug_trial = is_drug_trial_v2(t)
        if t.is_drug_trial:
            t.modality = assign_trial_modality_v2(t)
        else:
            t.modality = None

    # -------------------------------------------------
    # Summaries
    # -------------------------------------------------

    summary = {
        "ta_modality_counts_true_drugs": ta_modality_counts_true_drugs(trials),
        "drug_trial_counts": drug_trial_counts(trials),
        "info_flag_counts_true_drugs": info_flag_counts_true_drugs(trials),
        "drug_info_overview": drug_info_overview(trials),
        "intervention_type_summary": intervention_type_summary_all_trials(trials),
        "study_type_summary": study_type_summary_all_trials(trials),
    }

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

    print("\nStudyType summary (ALL trials):")
    for st, count in summary["study_type_summary"].items():
        print(f"  {st}: {count}")

    print("\nCT.gov Intervention Category Summary (ALL trials):")
    for tp, count in summary["intervention_type_summary"].items():
        print(f"  {tp:25} | {count}")


    # -------------------------------------------------
    # Metadata + Save
    # -------------------------------------------------

    metadata = SnapshotMetadataV2(
        source=old_metadata.get("source"),
        window_basis=old_metadata.get("window_basis"),
        as_of=date.today(),
        window_start=old_metadata.get("window_start"),
        window_end=old_metadata.get("window_end"),
        page_size=old_metadata.get("page_size"),
        max_studies=old_metadata.get("max_studies"),
        reclassified_from=str(snapshot_path),
    )

    out_path = save_trial_snapshot_v2(
        base_dir=str(output_base_dir),
        basis_folder="reclassified",
        metadata=metadata,
        trials=trials,
        summary=summary,
    )

    return out_path

# -------------------------------------------------
# CLI
# -------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Reclassify TA/modality for an existing V2 snapshot (no refetch)"
    )
    parser.add_argument(
        "--snapshot",
        required=True,
        help="Path to existing V2 snapshot JSON",
    )
    parser.add_argument(
        "--out",
        default="storage/snapshots/clinical_trials_v2",
        help="Base output directory",
    )

    args = parser.parse_args()

    out = reclassify_snapshot(
        snapshot_path=Path(args.snapshot),
        output_base_dir=Path(args.out),
    )

    print(f"\nReclassified snapshot saved to: {out}")
