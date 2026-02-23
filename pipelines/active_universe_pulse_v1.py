from datetime import date
import json
import time
import dataclasses
from pathlib import Path

from tqdm import tqdm

from collectors.clinicaltrials.clinicaltrials_fetch_active import fetch_active_studies_raw
from collectors.clinicaltrials.clinicaltrials_normalize_v2 import normalize_clinicaltrials_study_v2

from classifiers.therapeutic_area import (
    assign_therapeutic_area,
    detect_therapeutic_area_evidence,
)

from classifiers.drug_non_drug_v2 import is_drug_trial_v2

from storage.models_v2 import ClinicalTrialSignalV2, MeshTermV2, InterventionV2

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

# ------------------------------------------------------------------
# Checkpoint config
# ------------------------------------------------------------------
CHECKPOINT_DIR = Path("storage/checkpoints/active_universe")
CHECKPOINT_RAW = CHECKPOINT_DIR / "raw.json"
CHECKPOINT_NORMALIZED = CHECKPOINT_DIR / "normalized.json"
CHECKPOINT_CLASSIFIED_PREFIX = "classified_chunk_"
CHUNK_SIZE = 250


# ------------------------------------------------------------------
# JSON serialization
# ------------------------------------------------------------------

class DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)


# ------------------------------------------------------------------
# Checkpoint helpers
# ------------------------------------------------------------------

def save_raw_checkpoint(raw: list) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_RAW.write_text(json.dumps(raw))
    print(f"✓ Raw checkpoint saved ({len(raw)} studies) → {CHECKPOINT_RAW}")


def load_raw_checkpoint() -> list | None:
    if not CHECKPOINT_RAW.exists():
        return None
    print(f"↩ Loading raw from checkpoint: {CHECKPOINT_RAW}")
    return json.loads(CHECKPOINT_RAW.read_text())


def save_normalized_checkpoint(trials: list[ClinicalTrialSignalV2]) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    data = [dataclasses.asdict(t) for t in trials]
    CHECKPOINT_NORMALIZED.write_text(json.dumps(data, cls=DateEncoder))
    print(f"✓ Normalized checkpoint saved ({len(trials)} trials) → {CHECKPOINT_NORMALIZED}")


def load_normalized_checkpoint() -> list[dict] | None:
    if not CHECKPOINT_NORMALIZED.exists():
        return None
    print(f"↩ Loading normalized from checkpoint: {CHECKPOINT_NORMALIZED}")
    return json.loads(CHECKPOINT_NORMALIZED.read_text())


def save_classified_chunk(chunk: list[ClinicalTrialSignalV2], chunk_index: int) -> None:
    path = CHECKPOINT_DIR / f"{CHECKPOINT_CLASSIFIED_PREFIX}{chunk_index:04d}.json"
    data = [dataclasses.asdict(t) for t in chunk]
    path.write_text(json.dumps(data, cls=DateEncoder))
    print(f"  ✓ Chunk {chunk_index} saved ({len(chunk)} trials) → {path}")


def load_classified_chunks() -> tuple[list[dict], int]:
    chunks = sorted(CHECKPOINT_DIR.glob(f"{CHECKPOINT_CLASSIFIED_PREFIX}*.json"))
    if not chunks:
        return [], 0
    all_classified = []
    for c in chunks:
        all_classified.extend(json.loads(c.read_text()))
    next_index = int(chunks[-1].stem.replace(CHECKPOINT_CLASSIFIED_PREFIX, "")) + 1
    print(f"↩ Resuming classification: found {len(chunks)} chunks ({len(all_classified)} trials already classified)")
    return all_classified, next_index


def clear_checkpoints() -> None:
    for f in CHECKPOINT_DIR.glob("*.json"):
        f.unlink()
    print("✓ Checkpoints cleared.")


# ------------------------------------------------------------------
# Trial reconstruction from checkpoint dict
# ------------------------------------------------------------------

def reconstruct_trial(t: dict) -> ClinicalTrialSignalV2:
    def mesh_list(key):
        return [MeshTermV2(id=m.get("id"), term=m.get("term")) for m in (t.get(key) or [])]

    def iv_list(key):
        return [
            InterventionV2(
                name=iv.get("name"), type=iv.get("type"), role=iv.get("role"),
                arm_group_labels=iv.get("arm_group_labels") or [],
                other_names=iv.get("other_names") or [],
                description=iv.get("description"),
            )
            for iv in (t.get(key) or []) if isinstance(iv, dict)
        ]

    return ClinicalTrialSignalV2(
        nct_id=t.get("nct_id"),
        title=t.get("title"),
        study_type=t.get("study_type"),
        phase=t.get("phase"),
        sponsor_class=t.get("sponsor_class"),
        conditions=t.get("conditions") or [],
        first_posted_date=t.get("first_posted_date"),
        last_update_posted_date=t.get("last_update_posted_date"),
        interventions=iv_list("interventions"),
        interventions_all=iv_list("interventions_all"),
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

def main():
    as_of = date.today()
    max_studies = 500000

    # ---- STEP 1: Fetch (skip if raw checkpoint exists) ----
    raw = load_raw_checkpoint()
    if raw is None:
        raw = fetch_active_studies_raw(
            page_size=CLINICALTRIALS_PAGE_SIZE,
            max_studies=max_studies,
        )
        print(f"Raw studies returned: {len(raw)}")
        save_raw_checkpoint(raw)
    else:
        print(f"Raw studies loaded: {len(raw)}")

    # ---- STEP 2: Normalize (skip if normalized checkpoint exists) ----
    normalized_checkpoint = load_normalized_checkpoint()

    if normalized_checkpoint is not None:
        trials = [reconstruct_trial(t) for t in normalized_checkpoint]
        print(f"Loaded {len(trials)} trials from normalized checkpoint.")
    else:
        trials = []
        for study in raw:
            try:
                trials.append(normalize_clinicaltrials_study_v2(study, skip_non_essential=True))
            except Exception:
                continue
        print(f"Normalized trials (v2): {len(trials)}")

        dedup = {}
        for t in trials:
            if t.nct_id:
                dedup[t.nct_id] = t
        trials = list(dedup.values())
        print(f"Deduped trials (v2): {len(trials)}")

        save_normalized_checkpoint(trials)

    # ---- STEP 3: Classification in chunks (sequential, resumable) ----
    already_classified_raw, next_chunk_index = load_classified_chunks()
    already_classified_ids = {t["nct_id"] for t in already_classified_raw}
    remaining = [t for t in trials if t.nct_id not in already_classified_ids]
    print(f"Trials to classify: {len(remaining)} (skipping {len(already_classified_ids)} already done)")

    start_time = time.time()
    newly_classified: list[ClinicalTrialSignalV2] = []

    for i in range(0, len(remaining), CHUNK_SIZE):
        chunk = remaining[i: i + CHUNK_SIZE]
        chunk_index = next_chunk_index + (i // CHUNK_SIZE)
        print(f"\nClassifying chunk {chunk_index} ({len(chunk)} trials)...")

        classified_chunk = []
        for trial in tqdm(chunk, desc="Classifying trials", unit="trial", dynamic_ncols=True):
            try:
                classified_chunk.append(classify_single_trial(trial))
            except Exception as e:
                print(f"  ⚠ Skipping {trial.nct_id}: {e}")
                continue

        save_classified_chunk(classified_chunk, chunk_index)
        newly_classified.extend(classified_chunk)

    elapsed = time.time() - start_time
    total_classified = len(already_classified_raw) + len(newly_classified)
    print(f"\n✓ Classification completed in {elapsed:.1f}s ({total_classified} total trials)")

    prev_classified = [reconstruct_trial(t) for t in already_classified_raw]
    trials = prev_classified + newly_classified

    # ---- STEP 4: Metadata + summary + snapshot ----
    metadata = SnapshotMetadataV2(
        source="clinicaltrials.gov",
        window_basis="overallStatus",
        as_of=as_of,
        window_start=None,
        window_end=None,
        page_size=CLINICALTRIALS_PAGE_SIZE,
        max_studies=max_studies,
    )

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
        basis_folder="active_universe",
        metadata=metadata,
        trials=trials,
        summary=summary,
    )
    print(f"\nSaved snapshot (v2): {snapshot_path}")

    # Clear checkpoints only after successful save
    clear_checkpoints()


if __name__ == "__main__":
    main()
