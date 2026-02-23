"""
pulse_window_v1.py — Fetch and classify trials for a user-defined date window.

Usage:
    python -m pipelines.pulse_window_v1 --from 2026-02-22 --to 2026-02-23
    python -m pipelines.pulse_window_v1 --from 2026-02-22          # --to defaults to today
    python -m pipelines.pulse_window_v1 --days 7                   # last N days ending today
"""

from datetime import date, timedelta
import time
from pathlib import Path

from utils.parallel_processor import process_trials_parallel

from collectors.clinicaltrials.clinicaltrials_fetch import fetch_studies_raw
from collectors.clinicaltrials.clinicaltrials_normalize_v2 import normalize_clinicaltrials_study_v2

from classifiers.therapeutic_area import (
    assign_therapeutic_area,
    detect_therapeutic_area_evidence,
)
from classifiers.drug_non_drug_v2 import is_drug_trial_v2
from classifiers.trial_modality_v2 import assign_trial_modality_v2

from storage.models_v2 import ClinicalTrialSignalV2

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


# ------------------------------------------------------------------
# Versioned save (never overwrites existing files)
# ------------------------------------------------------------------

def _versioned_save(base_dir: str, basis_folder: str, label: str, metadata, trials, summary) -> Path:
    out_dir = Path(base_dir) / basis_folder
    out_dir.mkdir(parents=True, exist_ok=True)

    version = 1
    while (out_dir / f"{label}_v{version}.json").exists():
        version += 1

    tmp_path = save_trial_snapshot_v2(
        base_dir=base_dir,
        basis_folder=basis_folder,
        metadata=metadata,
        trials=trials,
        summary=summary,
    )
    final_path = out_dir / f"{label}_v{version}.json"
    tmp_path.rename(final_path)
    return final_path


# ------------------------------------------------------------------
# Classifier
# ------------------------------------------------------------------

def classify_single_trial(trial: ClinicalTrialSignalV2) -> ClinicalTrialSignalV2:
    trial._cached_title_interventions = " ".join(
        (trial.interventions_text or []) + [trial.title or ""]
    ).lower()
    trial._cached_title_conditions = " ".join(
        [trial.title or ""] + (trial.conditions or [])
    ).lower()

    trial.is_drug_trial = is_drug_trial_v2(trial)

    if not trial.is_drug_trial:
        trial.therapeutic_area = None
        trial.therapeutic_areas_detected = []
        trial.study_intent = None
        trial.study_category = None
        trial.study_category_evidence = []
        trial.mesh_missing_condition = False
        trial.modality = None
        return trial

    ta_evidence = detect_therapeutic_area_evidence(trial)
    trial.therapeutic_areas_detected = sorted(ta_evidence.keys())
    primary_ta = select_primary_ta(trial.therapeutic_areas_detected)

    if primary_ta:
        trial.therapeutic_area = primary_ta
    else:
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

    if not trial.is_drug_trial:
        trial.study_intent = None
    elif trial.therapeutic_area == TA_NON_DISEASE:
        trial.study_intent = "non_disease"
    elif trial.therapeutic_area == TA_UNASSIGNED:
        trial.study_intent = None
    else:
        trial.study_intent = "disease"

    if trial.is_drug_trial and trial.study_intent == "non_disease":
        cat, ev = assign_non_disease_study_category(trial)
        trial.study_category = cat
        trial.study_category_evidence = ev
    else:
        trial.study_category = None
        trial.study_category_evidence = []

    trial.mesh_missing_condition = bool(
        trial.is_drug_trial and not trial.condition_meshes
    )
    trial.modality = assign_trial_modality_v2(trial) if trial.is_drug_trial else None

    return trial


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def prompt_window() -> tuple[date, date]:
    """
    Interactively prompt the user for a date window at runtime.
    Supports two modes: explicit dates or last-N-days shortcut.
    """
    today = date.today()

    print()
    print("=" * 55)
    print("  ALEXIS Pulse — Window Configuration")
    print("=" * 55)
    print(f"  Today: {today}")
    print()
    print("  Options:")
    print("    1) Explicit date range   (e.g. 2026-02-22 → 2026-02-23)")
    print("    2) Last N days           (e.g. last 7 days ending today)")
    print()

    while True:
        mode = input("  Select mode [1/2]: ").strip()
        if mode in ("1", "2"):
            break
        print("  Please enter 1 or 2.")

    if mode == "2":
        while True:
            raw = input("  Number of days: ").strip()
            try:
                n = int(raw)
                if n < 1:
                    raise ValueError
                return today - timedelta(days=n), today
            except ValueError:
                print("  Please enter a positive integer.")

    # Mode 1: explicit dates
    while True:
        raw = input("  Start date (YYYY-MM-DD, inclusive): ").strip()
        try:
            updated_from = date.fromisoformat(raw)
            break
        except ValueError:
            print("  Invalid format. Use YYYY-MM-DD.")

    while True:
        raw = input(f"  End date   (YYYY-MM-DD, inclusive) [default: {today}]: ").strip()
        if not raw:
            updated_to = today
            break
        try:
            updated_to = date.fromisoformat(raw)
            break
        except ValueError:
            print("  Invalid format. Use YYYY-MM-DD.")

    return updated_from, updated_to


def main():
    as_of = date.today()
    updated_from, updated_to = prompt_window()

    if updated_from > updated_to:
        raise ValueError(f"Start date ({updated_from}) must be before end date ({updated_to})")

    max_studies = 100000
    window_days = (updated_to - updated_from).days
    print(f"\nWindow: {updated_from} → {updated_to} ({window_days} days)")

    # ---- Fetch ----
    raw = fetch_studies_raw(
        updated_from=updated_from,
        updated_to=updated_to,
        page_size=CLINICALTRIALS_PAGE_SIZE,
        max_studies=max_studies,
    )
    print(f"Raw studies returned: {len(raw)}")

    # ---- Normalize ----
    trials = []
    for study in raw:
        try:
            trials.append(normalize_clinicaltrials_study_v2(study, skip_non_essential=True))
        except Exception:
            continue
    print(f"Normalized trials: {len(trials)}")

    dedup = {}
    for t in trials:
        if t.nct_id:
            dedup[t.nct_id] = t
    trials = list(dedup.values())
    print(f"Deduped trials: {len(trials)}")

    # ---- Classify ----
    start_time = time.time()
    trials = process_trials_parallel(
        trials=trials,
        classifier_function=classify_single_trial,
        num_workers=None,
    )
    elapsed = time.time() - start_time
    print(f"\n✓ Classification completed in {elapsed:.1f}s ({len(trials) / elapsed:.1f} trials/sec)")

    # ---- Metadata ----
    metadata = SnapshotMetadataV2(
        source="clinicaltrials.gov",
        window_basis="LastUpdatePostDate",
        as_of=as_of,
        window_start=updated_from,
        window_end=updated_to,
        page_size=CLINICALTRIALS_PAGE_SIZE,
        max_studies=max_studies,
    )

    if not trials:
        print("\nNo trials found for this window. Nothing to save.")
        return

    # ---- Summary ----
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
        "ta_by_phase": ta_by_phase(trials),
        "modality_by_phase": modality_by_phase(trials),
        "ta_by_sponsor_class": ta_by_sponsor_class(trials),
        "multi_ta_rate_by_phase": multi_ta_rate_by_phase(trials),
        "drug_mesh_missing_condition": drug_mesh_missing_condition_summary(trials),
        "non_disease_study_categories": non_disease_study_category_summary(trials),
    }

    # ---- Print ----
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

    print("\nNon-disease study categories:")
    for k, v in summary.get("non_disease_study_categories", {}).items():
        print(f"  {k:25} | {v}")

    # ---- Save ----
    label = f"{updated_from}_{updated_to}"
    snapshot_path = _versioned_save(
        base_dir="storage/snapshots/clinical_trials_v2",
        basis_folder="last_update",
        label=label,
        metadata=metadata,
        trials=trials,
        summary=summary,
    )
    print(f"\nSaved snapshot: {snapshot_path}")


if __name__ == "__main__":
    main()
