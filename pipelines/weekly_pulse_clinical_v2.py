from datetime import date, timedelta
import json
from pathlib import Path

from tqdm import tqdm

from collectors.clinicaltrials.clinicaltrials_fetch import fetch_studies_raw
from collectors.clinicaltrials.clinicaltrials_normalize_v2 import normalize_clinicaltrials_study_v2

from analytics.modality_info_audit import audit_modality_info_flags

from classifiers.therapeutic_area import (
    assign_therapeutic_area,
    detect_therapeutic_area_evidence,
)
from classifiers.drug_non_drug_v2 import is_drug_trial_v2
from classifiers.trial_modality_v2 import assign_trial_modality_v2
from policy.ta_policy import TA_NON_DISEASE, select_primary_ta, TA_UNASSIGNED
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

from storage.snapshots_io_v2 import SnapshotMetadataV2, save_trial_snapshot_v2
from config.settings import CLINICALTRIALS_PAGE_SIZE

RAW_STORAGE_DIR = Path("/home/jeanmfc/projects/ALEXIS/storage/raw/ctgov/weekly")

def main():
    # 1) Define the window FIRST (same as v01)
    as_of = date.today()
    window_days = 7
    updated_from = as_of - timedelta(days=window_days)
    updated_to = as_of

    # 2) Fetch only studies in the window (same as v01)
    max_studies = 100000
    raw = fetch_studies_raw(
        updated_from=updated_from,
        updated_to=updated_to,
        page_size=CLINICALTRIALS_PAGE_SIZE,
        max_studies=max_studies,
    )

    print(f"Raw studies returned: {len(raw)}")


    # 3) Normalize (v2)
    trials = []
    for study in raw:
        try:
            trials.append(normalize_clinicaltrials_study_v2(study))
        except Exception:
            # Keep runner robust; skip bad records deterministically
            continue
    print(f"Normalized trials (v2): {len(trials)}")

    # Dedupe by nct_id (same as v01)
    dedup = {}
    for t in trials:
        if t.nct_id:
            dedup[t.nct_id] = t
    trials = list(dedup.values())
    print(f"Deduped trials (v2): {len(trials)}")

    # 4) Classify (write results onto model objects) with progress bar
    for t in tqdm(trials, desc="Classifying trials (v2)", unit="trial"):
        # --- Pre-cache text for all downstream functions ---
        t._cached_title_interventions = " ".join(
            (t.interventions_text or []) + [t.title or ""]
        ).lower()
        t._cached_title_conditions = " ".join(
            [t.title or ""] + (t.conditions or [])
        ).lower()
    
        # --- Drug status FIRST (AUTHORITATIVE) ---
        t.is_drug_trial = is_drug_trial_v2(t)

        # --- Therapeutic Area (FIXED PROVENANCE) ---

        # 1) Detect multi-TA using MeSH ancestry
        ta_evidence = detect_therapeutic_area_evidence(t)
        t.therapeutic_areas_detected = sorted(ta_evidence.keys())

        primary_ta = select_primary_ta(t.therapeutic_areas_detected)

        if primary_ta:
            t.therapeutic_area = primary_ta

        else:
            # 2) Text-based TA fallback MUST run before non-disease
            text_ta = assign_therapeutic_area(t)

            if text_ta and text_ta != "Other":
                t.therapeutic_area = text_ta

            elif t.is_drug_trial:
                if has_enabling_signal(t):
                    t.therapeutic_area = TA_NON_DISEASE
                else:
                    t.therapeutic_area = TA_UNASSIGNED

            else:
                t.therapeutic_area = None

        # --- Study intent (AUTHORITATIVE) ---
        if not t.is_drug_trial:
            t.study_intent = None
        elif t.therapeutic_area == TA_NON_DISEASE:
            t.study_intent = "non_disease"
        elif t.therapeutic_area == TA_UNASSIGNED:
            t.study_intent = None
        else:
            t.study_intent = "disease"
        
        # --- Non-disease study category (new) ---
        if t.is_drug_trial and t.study_intent == "non_disease":
            cat, ev = assign_non_disease_study_category(t)
            t.study_category = cat
            t.study_category_evidence = ev
        else:
            t.study_category = None
            t.study_category_evidence = []

        # --- Data completeness flag (NOT intent) ---
        t.mesh_missing_condition = bool(
            t.is_drug_trial and not t.condition_meshes
        )

        # --- Modality (UNCHANGED) ---
        if t.is_drug_trial:
            t.modality = assign_trial_modality_v2(t)
        else:
            t.modality = None

    # 5) Build snapshot metadata (v2)
    metadata = SnapshotMetadataV2(
        source="clinicaltrials.gov",
        window_basis="LastUpdatePostDate",
        as_of=as_of,
        window_start=updated_from,
        window_end=updated_to,
        page_size=CLINICALTRIALS_PAGE_SIZE,
        max_studies=max_studies,
    )

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

    snapshot_path = save_trial_snapshot_v2(
        base_dir="storage/snapshots/clinical_trials_v2",
        basis_folder="last_update",
        metadata=metadata,
        trials=trials,
        summary=summary,
    )
    print(f"\nSaved snapshot (v2): {snapshot_path}")

if __name__ == "__main__":
    main()
