# pipelines/weekly_pulse_clinical_pubmed.py

from datetime import date, timedelta

from tqdm import tqdm

from collectors.clinicaltrials.clinicaltrials_fetch import fetch_studies_raw
from collectors.clinicaltrials.clinicaltrials_normalize import normalize_studies
from classifiers.therapeutic_area import assign_therapeutic_area
from classifiers.modality import assign_modality

from analytics.summary import ta_modality_counts
from storage.snapshots_io import SnapshotMetadata, save_trial_snapshot

from config.settings import CLINICALTRIALS_PAGE_SIZE
from classifiers.drug_non_drug import is_drug_trial


def main():
    # 1) Define the window FIRST (Design A)
    as_of = date.today()
    window_days = 7
    updated_from = as_of - timedelta(days=window_days)
    updated_to = as_of

    # 2) Fetch only studies in the window (pagination happens inside fetcher)
    max_studies = 100000  # keep runs manageable while developing
    raw = fetch_studies_raw(
        updated_from=updated_from,
        updated_to=updated_to,
        page_size=CLINICALTRIALS_PAGE_SIZE,
        max_studies=max_studies,
    )
    print(f"Raw studies returned: {len(raw)}")

    # 3) Normalize
    trials = normalize_studies(raw)
    print(f"Normalized trials: {len(trials)}")

    # Dedupe by nct_id (keep last occurrence deterministically)
    dedup = {}
    for t in trials:
        if t.nct_id:
            dedup[t.nct_id] = t
    trials = list(dedup.values())
    print(f"Deduped trials: {len(trials)}")

    # 4) Classify (write results onto the model objects) with progress bar
    for t in tqdm(trials, desc="Classifying trials", unit="trial"):
        t.therapeutic_area = assign_therapeutic_area(t)
        t.is_drug_trial = is_drug_trial(t)
        t.modality = assign_modality(t)

    # 5) Build snapshot metadata
    metadata = SnapshotMetadata(
        source="clinicaltrials.gov",
        window_basis="LastUpdatePostDate",
        as_of=as_of,
        window_start=updated_from,
        window_end=updated_to,
        page_size=CLINICALTRIALS_PAGE_SIZE,
        max_studies=max_studies,
    )

    # 6) Compute summary (quarterly-friendly) and save snapshot
    summary = {
        "ta_modality_counts": ta_modality_counts(trials),
    }

    print("\nTA × Modality counts:")
    for ta, mods in summary["ta_modality_counts"].items():
        for modality, count in mods.items():
            print(f"  {ta:20} | {modality:22} | {count}")

    snapshot_path = save_trial_snapshot(
        base_dir="storage/snapshots/clinical_trials",
        basis_folder="last_update",
        metadata=metadata,
        trials=trials,
        summary=summary,
    )
    print(f"\nSaved snapshot: {snapshot_path}")


if __name__ == "__main__":
    main()

