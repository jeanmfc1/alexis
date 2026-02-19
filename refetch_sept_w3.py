#!/usr/bin/env python3
"""
Re-fetch the missing 2024_sep_w3 snapshot from ClinicalTrials.gov
"""

from datetime import date
from pathlib import Path

from collectors.clinicaltrials.clinicaltrials_fetch import fetch_studies_raw
from collectors.clinicaltrials.clinicaltrials_normalize_v2 import normalize_clinicaltrials_study_v2
from storage.snapshots_io_v2 import SnapshotMetadataV2, save_trial_snapshot_v2
from config.settings import CLINICALTRIALS_PAGE_SIZE
from pipelines.weekly_pulse_clinical_v2 import classify_single_trial
from utils.parallel_processor import process_trials_parallel
from analytics.summary_v2 import (
    ta_modality_counts_true_drugs,
    drug_trial_counts,
    info_flag_counts_true_drugs,
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
    non_disease_study_category_summary,
)

# Week 3 of Sept 2024: Sept 9-15
week_start = date(2024, 9, 9)
week_end = date(2024, 9, 15)

print(f"Fetching trials updated between {week_start} and {week_end}...")

raw = fetch_studies_raw(
    updated_from=week_start,
    updated_to=week_end,
    page_size=CLINICALTRIALS_PAGE_SIZE,
    max_studies=100000,
)

print(f"\nRaw studies returned: {len(raw)}")

if len(raw) == 0:
    print("\n⚠️  WARNING: ClinicalTrials.gov returned 0 trials for this week!")
    print("This could mean:")
    print("  1. No trials were updated during this week (unlikely)")
    print("  2. The API is having issues")
    print("  3. The date range is invalid")
    import sys
    sys.exit(1)

# Normalize
trials = []
for study in raw:
    try:
        trials.append(
            normalize_clinicaltrials_study_v2(
                study,
                skip_non_essential=True
            )
        )
    except Exception as e:
        print(f"  Error normalizing {study.get('protocolSection', {}).get('identificationModule', {}).get('nctId', 'UNKNOWN')}: {e}")
        continue

# Deduplicate
dedup = {}
for t in trials:
    if t.nct_id:
        dedup[t.nct_id] = t
trials = list(dedup.values())

print(f"Normalized + deduped trials: {len(trials)}")

# Classify
trials = process_trials_parallel(
    trials=trials,
    classifier_function=classify_single_trial,
    num_workers=None,
)

print(f"Classification complete: {len(trials)} trials")

# Summary
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

# Metadata
metadata = SnapshotMetadataV2(
    source="clinicaltrials.gov",
    window_basis="LastUpdatePostDate",
    as_of=week_end,
    window_start=week_start,
    window_end=week_end,
    page_size=CLINICALTRIALS_PAGE_SIZE,
    max_studies=100000,
)

# Save
path = save_trial_snapshot_v2(
    base_dir="storage/snapshots/clinical_trials_v2",
    basis_folder="last_update",
    metadata=metadata,
    trials=trials,
    summary=summary,
)

print(f"\n✓ Saved snapshot: {path}")
print(f"  Trials: {len(trials)}")
print(f"  Drug trials: {summary['drug_trial_counts']['drug_trials']}")
