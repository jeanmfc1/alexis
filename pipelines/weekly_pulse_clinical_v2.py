from datetime import date, timedelta

from tqdm import tqdm

from collectors.clinicaltrials.clinicaltrials_fetch import fetch_studies_raw
from collectors.clinicaltrials.clinicaltrials_normalize_v2 import normalize_clinicaltrials_study_v2

from classifiers.therapeutic_area import assign_therapeutic_area  # v01 TA classifier reused for now
from classifiers.drug_non_drug_v2 import is_drug_trial_v2
from classifiers.trial_modality_v2 import assign_trial_modality_v2

from analytics.summary import ta_modality_counts
from analytics.modality_info_audit import audit_modality_info_flags

from storage.snapshots_io_v2 import SnapshotMetadataV2, save_trial_snapshot_v2
from config.settings import CLINICALTRIALS_PAGE_SIZE


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
        t.therapeutic_area = assign_therapeutic_area(t)
        t.is_drug_trial = is_drug_trial_v2(t)
        # Only assign modality for drug trials (optional guard)
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
        "ta_modality_counts": ta_modality_counts(trials),
        "info_flag_counts": audit_modality_info_flags(trials),
    }

    print("\nTA × Modality counts (v2):")
    for ta, mods in summary["ta_modality_counts"].items():
        for modality, count in mods.items():
            print(f"  {ta:20} | {modality:22} | {count}")

    print("\nModality INFO summary (v2):")
    for flag, count in summary["info_flag_counts"].items():
        print(f"  {flag}: {count}")

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
