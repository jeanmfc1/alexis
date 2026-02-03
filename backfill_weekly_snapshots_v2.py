from datetime import date, timedelta
from pathlib import Path
import time

from utils.parallel_processor import process_trials_parallel

from collectors.clinicaltrials.clinicaltrials_fetch import fetch_studies_raw
from collectors.clinicaltrials.clinicaltrials_normalize_v2 import normalize_clinicaltrials_study_v2

from storage.snapshots_io_v2 import SnapshotMetadataV2, save_trial_snapshot_v2
from config.settings import CLINICALTRIALS_PAGE_SIZE

from pipelines.weekly_pulse_clinical_v2 import classify_single_trial
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

BASE_OUT_DIR = "storage/snapshots/clinical_trials_v2"
BASIS_FOLDER = "last_update"
MAX_STUDIES = 100_000


def iter_weeks(start: date, end: date):
    """
    Yield (week_start, week_end) using ISO weeks.
    week_start = Monday
    week_end   = Sunday
    """
    cur = start
    while cur <= end:
        week_start = cur - timedelta(days=cur.weekday())
        week_end = week_start + timedelta(days=6)
        yield week_start, min(week_end, end)
        cur = week_end + timedelta(days=1)


def run_week(week_start: date, week_end: date):
    print(f"\n=== Processing week {week_start} → {week_end} ===")

    raw = fetch_studies_raw(
        updated_from=week_start,
        updated_to=week_end,
        page_size=CLINICALTRIALS_PAGE_SIZE,
        max_studies=MAX_STUDIES,
    )

    print(f"Raw studies returned: {len(raw)}")

    trials = []
    for study in raw:
        try:
            trials.append(
                normalize_clinicaltrials_study_v2(
                    study,
                    skip_non_essential=True
                )
            )
        except Exception:
            continue

    # Deduplicate by NCT
    dedup = {}
    for t in trials:
        if t.nct_id:
            dedup[t.nct_id] = t
    trials = list(dedup.values())

    print(f"Normalized + deduped trials: {len(trials)}")

    # Classify
    start_time = time.time()
    trials = process_trials_parallel(
        trials=trials,
        classifier_function=classify_single_trial,
        num_workers=None,
    )
    elapsed = time.time() - start_time
    print(f"Classification done in {elapsed:.1f}s")

    # Metadata
    metadata = SnapshotMetadataV2(
        source="clinicaltrials.gov",
        window_basis="LastUpdatePostDate",
        as_of=week_end,
        window_start=week_start,
        window_end=week_end,
        page_size=CLINICALTRIALS_PAGE_SIZE,
        max_studies=MAX_STUDIES,
    )

    # Summary (same as weekly runner)
    if not trials:
        summary = {}
    else:
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

    path = save_trial_snapshot_v2(
        base_dir=BASE_OUT_DIR,
        basis_folder=BASIS_FOLDER,
        metadata=metadata,
        trials=trials,
        summary=summary,
    )

    print(f"Saved snapshot: {path}")


def main():
    start_date = date(2024, 9, 9)
    end_date = date.today()

    for week_start, week_end in iter_weeks(start_date, end_date):
        run_week(week_start, week_end)


if __name__ == "__main__":
    main()
