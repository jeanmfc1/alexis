from __future__ import annotations
from tqdm import tqdm
import json
from pathlib import Path
from datetime import date

from classifiers.therapeutic_area import assign_therapeutic_area  # v01 TA classifier reused for now
from storage.models_v2 import ClinicalTrialSignalV2, InterventionV2, MeshTermV2
from classifiers.drug_non_drug_v2 import is_drug_trial_v2
from classifiers.trial_modality_v2 import assign_trial_modality_v2
from analytics.summary_v2 import (
    ta_modality_counts_true_drugs,
    drug_trial_counts,
    info_flag_counts_true_drugs,
    drug_info_overview,
)
from storage.snapshots_io_v2 import save_trial_snapshot_v2, SnapshotMetadataV2


# -------------------------------------------------
# Snapshot loading (NO external dependency)
# -------------------------------------------------

def load_snapshot(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


from storage.models_v2 import ClinicalTrialSignalV2, InterventionV2, MeshTermV2


def reconstruct_trials(raw_trials: list[dict]) -> list[ClinicalTrialSignalV2]:
    trials = []

    for t in raw_trials:
        interventions = [
            InterventionV2(
                name=iv.get("name"),
                type=iv.get("type"),
                role=iv.get("role"),
                arm_group_labels=iv.get("arm_group_labels") or [],
                other_names=iv.get("other_names") or [],
                description=iv.get("description"),
            )
            for iv in (t.get("interventions") or [])
        ]

        def mesh_list(key: str):
            return [
                MeshTermV2(id=m.get("id"), term=m.get("term"))
                for m in (t.get(key) or [])
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
            interventions=interventions,
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

    trials = reconstruct_trials(snapshot["trials"])
    old_metadata = snapshot["metadata"]


# 4) Classify (write results onto model objects) with progress bar
    for t in tqdm(trials, desc="Reclassifying trials (v2)", unit="trial"):
        t.therapeutic_area = assign_therapeutic_area(t)
        t.is_drug_trial = is_drug_trial_v2(t)
        # Only assign modality for drug trials (optional guard)
        if t.is_drug_trial:
            t.modality = assign_trial_modality_v2(t)
        else:
            t.modality = None

    # --- Summary (V2, true drugs only) ---
    summary = {
        "ta_modality_counts_true_drugs": ta_modality_counts_true_drugs(trials),
        "drug_trial_counts": drug_trial_counts(trials),
        "info_flag_counts_true_drugs": info_flag_counts_true_drugs(trials),
        "drug_info_overview": drug_info_overview(trials),
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

    # --- Metadata ---
    metadata = SnapshotMetadataV2(
        source=old_metadata["source"],
        window_basis=old_metadata["window_basis"],
        as_of=date.today(),
        window_start=old_metadata["window_start"],
        window_end=old_metadata["window_end"],
        page_size=old_metadata["page_size"],
        max_studies=old_metadata["max_studies"],
        reclassified_from=str(snapshot_path),
    )

    # --- Save ---
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
        description="Reclassify modality for an existing V2 snapshot (no refetch)"
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

    print(f"Reclassified snapshot saved to: {out}")
