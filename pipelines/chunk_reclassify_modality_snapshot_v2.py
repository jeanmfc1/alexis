from __future__ import annotations
import dataclasses
import time
import json
from pathlib import Path
from datetime import date
from typing import List

from tqdm import tqdm
from multiprocessing import Pool, cpu_count

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
# Checkpoint config
# -------------------------------------------------

CHUNK_SIZE = 250
CHECKPOINT_DIR = Path("storage/checkpoints/reclassify")
CHECKPOINT_PREFIX = "reclassify_chunk_"


class DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)


def _ensure_checkpoint_dir() -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


def save_chunk(chunk: List[ClinicalTrialSignalV2], chunk_index: int) -> None:
    _ensure_checkpoint_dir()
    path = CHECKPOINT_DIR / f"{CHECKPOINT_PREFIX}{chunk_index:04d}.json"
    data = [dataclasses.asdict(t) for t in chunk]
    path.write_text(json.dumps(data, cls=DateEncoder))
    print(f"  ✓ Chunk {chunk_index:04d} saved ({len(chunk)} trials) → {path}")


def load_chunks() -> tuple[list[dict], int]:
    """Returns (already_classified_dicts, next_chunk_index)."""
    chunks = sorted(CHECKPOINT_DIR.glob(f"{CHECKPOINT_PREFIX}*.json"))
    if not chunks:
        return [], 0
    all_classified = []
    for c in chunks:
        all_classified.extend(json.loads(c.read_text()))
    next_index = int(chunks[-1].stem.replace(CHECKPOINT_PREFIX, "")) + 1
    print(
        f"↩  Resuming: found {len(chunks)} chunks "
        f"({len(all_classified)} trials already classified, next chunk: {next_index})"
    )
    return all_classified, next_index


def clear_checkpoints() -> None:
    _ensure_checkpoint_dir()
    removed = 0
    for f in CHECKPOINT_DIR.glob(f"{CHECKPOINT_PREFIX}*.json"):
        f.unlink()
        removed += 1
    print(f"✓ Cleared {removed} checkpoint files.")


# -------------------------------------------------
# Snapshot loading
# -------------------------------------------------

def load_snapshot(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# -------------------------------------------------
# Trial reconstruction
# -------------------------------------------------

def reconstruct_trials(raw_trials: List[dict]) -> List[ClinicalTrialSignalV2]:
    trials: List[ClinicalTrialSignalV2] = []
    for t in raw_trials:
        def mesh_list(key: str):
            return [
                MeshTermV2(id=m.get("id"), term=m.get("term"))
                for m in (t.get(key) or [])
            ]

        all_iv_objs = [
            InterventionV2(
                name=iv.get("name"), type=iv.get("type"), role=iv.get("role"),
                arm_group_labels=iv.get("arm_group_labels") or [],
                other_names=iv.get("other_names") or [],
                description=iv.get("description"),
            )
            for iv in (t.get("interventions_all") or [])
            if isinstance(iv, dict)
        ]
        subset_iv_objs = [
            InterventionV2(
                name=iv.get("name"), type=iv.get("type"), role=iv.get("role"),
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
            therapeutic_areas_detected=t.get("therapeutic_areas_detected") or [],
            is_drug_trial=t.get("is_drug_trial"),
            modality=t.get("modality"),
            info_flags=t.get("info_flags") or [],
            study_intent=t.get("study_intent"),
            study_category=t.get("study_category"),
            study_category_evidence=t.get("study_category_evidence") or [],
            mesh_missing_condition=t.get("mesh_missing_condition") or False,
        )
        trials.append(trial)
    return trials


# -------------------------------------------------
# Batch worker (top-level for multiprocessing pickling)
# Matches the pattern in utils/parallel_processor.py
# -------------------------------------------------

def _classify_batch(args: tuple) -> list:
    trials_batch, classifier_fn, batch_id, total_batches = args
    results = []
    for trial in trials_batch:
        try:
            results.append(classifier_fn(trial))
        except Exception as e:
            import traceback
            print(f"Error classifying {trial.nct_id}: {e}\n{traceback.format_exc()}")
            results.append(trial)
    return results


# -------------------------------------------------
# Single trial classification (identical to original)
# -------------------------------------------------

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

    if trial.is_drug_trial:
        trial.modality = assign_trial_modality_v2(trial)
    else:
        trial.modality = None

    return trial


# -------------------------------------------------
# Chunked classification with resume support
# -------------------------------------------------

def classify_in_chunks(
    trials: List[ClinicalTrialSignalV2],
    start_chunk: int,
) -> List[ClinicalTrialSignalV2]:
    already_done = trials[: start_chunk * CHUNK_SIZE]
    remaining = trials[start_chunk * CHUNK_SIZE :]

    if not remaining:
        print("Nothing to classify — all chunks already done.")
        return trials

    from contextlib import nullcontext
    num_workers = max(1, cpu_count() - 1)  # leave 1 core free
    print(
        f"Classifying {len(remaining)} trials in chunks of {CHUNK_SIZE} "
        f"(starting at chunk {start_chunk}, {num_workers} workers)..."
    )

    classified_remaining = []
    chunk_index = start_chunk
    BATCH_SIZE = 10  # Match original: small batches for smooth progress bar

    from classifiers.therapeutic_area import _load_mesh
    _load_mesh()
    print(f"  MeSH descriptors pre-loaded.")

    use_pool = num_workers > 1
    pool_ctx = Pool(num_workers) if use_pool else nullcontext(None)
    with pool_ctx as pool:
        for i in tqdm(range(0, len(remaining), CHUNK_SIZE), desc="Chunks"):
            chunk = remaining[i : i + CHUNK_SIZE]

            batches = [chunk[j : j + BATCH_SIZE] for j in range(0, len(chunk), BATCH_SIZE)]
            worker_args = [(b, classify_single_trial, k, len(batches)) for k, b in enumerate(batches)]

            classified_chunk = []
            if pool is None:
                for wa in worker_args:
                    classified_chunk.extend(_classify_batch(wa))
            else:
                for batch_result in pool.imap_unordered(_classify_batch, worker_args, chunksize=1):
                    classified_chunk.extend(batch_result)

            save_chunk(classified_chunk, chunk_index)
            classified_remaining.extend(classified_chunk)
            chunk_index += 1

    return already_done + classified_remaining


# -------------------------------------------------
# Main entry point
# -------------------------------------------------

def reclassify_snapshot(
    snapshot_path: Path,
    output_base_dir: Path,
    fresh: bool = False,
) -> Path:

    if fresh:
        clear_checkpoints()

    snapshot = load_snapshot(snapshot_path)
    raw_trials = snapshot.get("trials", [])
    old_metadata = snapshot.get("metadata", {})
    print(f"Loaded {len(raw_trials)} trials from snapshot.")

    # Reconstruct full trial list from snapshot
    trials = reconstruct_trials(raw_trials)

    # Load any existing checkpoint progress
    already_classified_dicts, next_chunk = load_chunks()

    if already_classified_dicts:
        n = len(already_classified_dicts)
        already_classified = reconstruct_trials(already_classified_dicts)
        trials = already_classified + trials[n:]
        print(f"  Skipping first {n} trials (already classified).")

    # Classify remaining in chunks with checkpoints
    start_time = time.time()
    trials = classify_in_chunks(trials, start_chunk=next_chunk)
    elapsed = time.time() - start_time
    print(f"\n✓ Classification completed in {elapsed:.1f}s ({len(trials)/elapsed:.1f} trials/sec)")

    # -------------------------------------------------
    # Summaries
    # -------------------------------------------------
    summary = {
        "ta_modality_counts_true_drugs":    ta_modality_counts_true_drugs(trials),
        "drug_trial_counts":                drug_trial_counts(trials),
        "info_flag_counts_true_drugs":      info_flag_counts_true_drugs(trials),
        "drug_info_overview":               drug_info_overview(trials),
        "intervention_type_summary":        intervention_type_summary_all_trials(trials),
        "study_type_summary":               study_type_summary_all_trials(trials),
        "drug_modality_provenance":         drug_modality_provenance_summary(trials),
        "drug_ta_provenance":               drug_ta_provenance_summary(trials),
        "drug_study_intent":                drug_study_intent_summary(trials),
        "non_disease_drug_subtypes":        non_disease_drug_subtype_summary(trials),
        "ta_by_phase":                      ta_by_phase(trials),
        "modality_by_phase":                modality_by_phase(trials),
        "ta_by_sponsor_class":              ta_by_sponsor_class(trials),
        "multi_ta_rate_by_phase":           multi_ta_rate_by_phase(trials),
        "drug_mesh_missing_condition":      drug_mesh_missing_condition_summary(trials),
        "non_disease_study_categories":     non_disease_study_category_summary(trials),
    }

    print("\nDrug trials by therapeutic area:")
    for k, v in sorted(drug_therapeutic_area_summary(trials).items()):
        print(f"  {k:40} | {v}")

    print("\nMulti-TA rate by phase:")
    for phase, rate in summary["multi_ta_rate_by_phase"].items():
        print(f"  {phase:10} | {rate:.2%}")

    print("\nDrug study intent:")
    for k, v in summary["drug_study_intent"].items():
        print(f"  {k:15} | {v}")

    print("\nNon-disease study categories:")
    for k, v in sorted(summary["non_disease_study_categories"].items()):
        print(f"  {k:40} | {v}")

    # -------------------------------------------------
    # Save
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

    # Clear checkpoints only after successful save
    clear_checkpoints()
    print(f"\n✓ Reclassified snapshot saved to: {out_path}")
    return out_path


# -------------------------------------------------
# CLI
# -------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Reclassify TA/modality for an existing V2 snapshot (chunked, resumable)"
    )
    parser.add_argument("--snapshot", required=True, help="Path to existing V2 snapshot JSON")
    parser.add_argument(
        "--out",
        default="storage/snapshots/clinical_trials_v2",
        help="Base output directory",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Clear existing checkpoints and start fresh (default: resume)",
    )

    args = parser.parse_args()

    out = reclassify_snapshot(
        snapshot_path=Path(args.snapshot),
        output_base_dir=Path(args.out),
        fresh=args.fresh,
    )
