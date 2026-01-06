from datetime import date, timedelta
import json
from pathlib import Path

from tqdm import tqdm

from collectors.clinicaltrials.clinicaltrials_fetch import fetch_studies_raw
from collectors.clinicaltrials.clinicaltrials_normalize_v2 import normalize_clinicaltrials_study_v2

from classifiers.therapeutic_area import assign_therapeutic_area  # v01 TA classifier reused for now
from classifiers.drug_non_drug_v2 import is_drug_trial_v2
from classifiers.trial_modality_v2 import assign_trial_modality_v2

from analytics.summary_v2 import (
    ta_modality_counts_true_drugs,
    drug_trial_counts,
    info_flag_counts_true_drugs,
    drug_info_overview,
    intervention_type_summary_all_trials,
    study_type_summary_all_trials,
)

from analytics.modality_info_audit import audit_modality_info_flags

from storage.snapshots_io_v2 import SnapshotMetadataV2, save_trial_snapshot_v2
from config.settings import CLINICALTRIALS_PAGE_SIZE

RAW_STORAGE_DIR = Path("/home/jeanmfc/projects/ALEXIS/storage/raw/ctgov/weekly")


def save_raw_ctgov(raw_payload):
    RAW_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    out_path = RAW_STORAGE_DIR / f"ctgov_raw_{date.today().isoformat()}.json"

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(raw_payload, f, indent=2, ensure_ascii=False)

    return out_path


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

    raw_path = save_raw_ctgov(raw)
    print(f"[RAW CTGOV SAVED] {raw_path}")

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
    for st, count in summary.get("study_type_summary", {}).items():
        print(f"  {st}: {count}")

    
    print("\nIntervention type summary (ALL trials):")
    for tp, count in summary.get("intervention_type_summary", {}).items():
        print(f"  {tp}: {count}")


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
