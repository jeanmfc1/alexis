from __future__ import annotations
import time
from utils.parallel_processor import process_trials_parallel
from tqdm import tqdm
import json
from pathlib import Path
from datetime import date
from typing import List
from policy.ta_policy import TA_NON_DISEASE, select_primary_ta, TA_UNASSIGNED

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
    drug_modality_summary,
    drug_therapeutic_area_summary,
    drug_info_overview,
    intervention_type_summary_all_trials,
    study_type_summary_all_trials,
    drug_modality_provenance_summary,
    drug_ta_provenance_summary,
    drug_study_intent_summary,
    non_disease_drug_subtype_summary,
    ta_by_phase,
    modality_by_phase,
    ta_by_sponsor_class,
    multi_ta_rate_by_phase,
    drug_mesh_missing_condition_summary,
    has_enabling_signal,
    assign_non_disease_study_category,
    non_disease_study_category_summary,
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
        
        # -------------------------------------------------
        # Structured interventions reconstruction (AUTHORITATIVE)
        # -------------------------------------------------
        # Snapshot schema:
        #   interventions_all = ALL structured interventions (canonical)
        #   interventions     = subset (new experimental drugs only)
        #
        # Reclassification MUST preserve this invariant.

        all_iv_objs = [
            InterventionV2(
                name=iv.get("name"),
                type=iv.get("type"),
                role=iv.get("role"),
                arm_group_labels=iv.get("arm_group_labels") or [],
                other_names=iv.get("other_names") or [],
                description=iv.get("description"),
            )
            for iv in (t.get("interventions_all") or [])
            if isinstance(iv, dict)
        ]

        subset_iv_objs = [
            InterventionV2(
                name=iv.get("name"),
                type=iv.get("type"),
                role=iv.get("role"),
                arm_group_labels=iv.get("arm_group_labels") or [],
                other_names=iv.get("other_names") or [],
                description=iv.get("description"),
            )
            for iv in (t.get("interventions") or [])
            if isinstance(iv, dict)
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
            interventions=subset_iv_objs,
            interventions_all=all_iv_objs,
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
def classify_single_trial(trial: ClinicalTrialSignalV2) -> ClinicalTrialSignalV2:
    """
    Classify a single trial (drug status, TA, modality, etc.)
    
    This function is called by parallel workers and must be self-contained.
    
    Args:
        trial: Trial object to classify
    
    Returns:
        The same trial object with classification fields populated
    """
    # --- Pre-cache text for all downstream functions ---
    trial._cached_title_interventions = " ".join(
        (trial.interventions_text or []) + [trial.title or ""]
    ).lower()
    trial._cached_title_conditions = " ".join(
        [trial.title or ""] + (trial.conditions or [])
    ).lower()

    # --- Drug status FIRST (AUTHORITATIVE) ---
    trial.is_drug_trial = is_drug_trial_v2(trial)

    # OPTIMIZATION: Skip expensive processing for non-drug trials
    if not trial.is_drug_trial:
        trial.therapeutic_area = None
        trial.therapeutic_areas_detected = []
        trial.study_intent = None
        trial.study_category = None
        trial.study_category_evidence = []
        trial.mesh_missing_condition = False
        trial.modality = None
        return trial

    # --- Therapeutic Area (FIXED PROVENANCE) ---

    # 1) Detect multi-TA using MeSH ancestry
    ta_evidence = detect_therapeutic_area_evidence(trial)
    trial.therapeutic_areas_detected = sorted(ta_evidence.keys())

    primary_ta = select_primary_ta(trial.therapeutic_areas_detected)

    if primary_ta:
        trial.therapeutic_area = primary_ta

    else:
        # 2) Text-based TA fallback MUST run before non-disease
        text_ta = assign_therapeutic_area(trial)

        if text_ta and text_ta != "Other":
            trial.therapeutic_area = text_ta

        elif trial.is_drug_trial:
            if has_enabling_signal(trial):
                trial.therapeutic_area = TA_NON_DISEASE
            else:
                trial.therapeutic_area = TA_UNASSIGNED

        else:
            trial.therapeutic_area = None

    # --- Study intent (AUTHORITATIVE) ---
    if not trial.is_drug_trial:
        trial.study_intent = None
    elif trial.therapeutic_area == TA_NON_DISEASE:
        trial.study_intent = "non_disease"
    elif trial.therapeutic_area == TA_UNASSIGNED:
        trial.study_intent = None
    else:
        trial.study_intent = "disease"
    
    # --- Non-disease study category (new) ---
    if trial.is_drug_trial and trial.study_intent == "non_disease":
        cat, ev = assign_non_disease_study_category(trial)
        trial.study_category = cat
        trial.study_category_evidence = ev
    else:
        trial.study_category = None
        trial.study_category_evidence = []

    # --- Data completeness flag (NOT intent) ---
    trial.mesh_missing_condition = bool(
        trial.is_drug_trial and not trial.condition_meshes
    )

    # --- Modality (UNCHANGED) ---
    if trial.is_drug_trial:
        trial.modality = assign_trial_modality_v2(trial)
    else:
        trial.modality = None
    
    return trial

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
    # Re-run classifiers IN PARALLEL
    # -------------------------------------------------
    # 4) Classify all trials in parallel
    start_time = time.time()
    
    trials = process_trials_parallel(
        trials=trials,
        classifier_function=classify_single_trial,
        num_workers=None  # Auto-detect optimal worker count
    )
    
    elapsed = time.time() - start_time
    trials_per_sec = len(trials) / elapsed if elapsed > 0 else 0
    print(f"\n✓ Classification completed in {elapsed:.1f}s ({trials_per_sec:.1f} trials/sec)")

    # 6) Compute summaries and save snapshot (v2)
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
        "non_disease_drug_subtypes": non_disease_drug_subtype_summary(trials),
        "ta_by_phase": ta_by_phase(trials),
        "modality_by_phase": modality_by_phase(trials),
        "ta_by_sponsor_class": ta_by_sponsor_class(trials),
        "multi_ta_rate_by_phase": multi_ta_rate_by_phase(trials),
        "drug_mesh_missing_condition": drug_mesh_missing_condition_summary(trials),
        "non_disease_study_categories": non_disease_study_category_summary(trials),
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

    print("\nCT.gov Intervention Category Summary (SOURCE LAYER):")
    print(f"  Layer: {ctgov.get('_layer')}")
    print(f"  Requires: {ctgov.get('_requires')}")
    print(f"  Valid on snapshots: {ctgov.get('_valid_on_snapshots')}")

    print("\n  Category                 | Trials with Category")
    print("  -----------------------------------------------")

    for tp, count in ctgov["trials_with_category"].items():
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

    print("\nNon-disease drug study subtypes:")
    for k, v in sorted(summary["non_disease_drug_subtypes"].items()):
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


    # -------------------------------------------------
    # Metadata + Save
    # -------------------------------------------------

    metadata = SnapshotMetadataV2(
        source=old_metadata.get("source"),
        window_basis=old_metadata.get("window_basis"),
        as_of=date.fromisoformat(old_metadata["as_of"]) if old_metadata.get("as_of") else date.today(),
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
