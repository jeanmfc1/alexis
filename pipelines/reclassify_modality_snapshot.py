from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

from classifiers.modality import assign_modality


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def _as_trial_obj(trial_dict: Dict[str, Any]):
    """
    Build a minimal attribute-style object for assign_modality().
    Keeps the classifier decoupled from snapshot dict shape.
    """
    return SimpleNamespace(
        nct_id=trial_dict.get("nct_id"),
        study_type=trial_dict.get("study_type"),
        interventions=trial_dict.get("interventions") or [],
    )

def _count_modalities(trials: List[Dict[str, Any]]) -> Counter:
    c = Counter()
    for t in trials:
        c[t.get("modality", "MISSING")] += 1
    return c


def _diff_counts(before: Counter, after: Counter) -> List[Tuple[str, int]]:
    labels = sorted(set(before.keys()) | set(after.keys()))
    return [(lab, after.get(lab, 0) - before.get(lab, 0)) for lab in labels if after.get(lab, 0) - before.get(lab, 0) != 0]


def _default_out_path(in_path: Path) -> Path:
    # Example: 2025-12-23T10-53-43.json -> 2025-12-23T10-53-43.modality.reclassified.json
    return in_path.with_suffix("")\
                  .with_name(in_path.stem + ".modality.reclassified.json")

def _default_changes_path(in_path: Path) -> Path:
    # Example: 2025-12-23T10-53-43.json -> 2025-12-23T10-53-43.modality.changes.json
    return in_path.with_suffix("").with_name(in_path.stem + ".modality.changes.json")

def main() -> None:
    parser = argparse.ArgumentParser(description="Reclassify modality for a clinical trials snapshot (immutable).")
    parser.add_argument("--path", required=True, help="Path to snapshot JSON")
    parser.add_argument("--out", default=None, help="Optional explicit output path")
    parser.add_argument("--max_examples", type=int, default=20, help="Max changed examples to print")
    parser.add_argument("--changes_out", default=None, help="Optional explicit output path for full change log JSON")

    args = parser.parse_args()

    in_path = Path(args.path)
    if not in_path.exists():
        raise SystemExit(f"Snapshot not found: {in_path}")

    snapshot = _load_json(in_path)
    trials: List[Dict[str, Any]] = snapshot.get("trials", [])
    if not isinstance(trials, list):
        raise SystemExit("Snapshot JSON malformed: 'trials' must be a list.")

    before_counts = _count_modalities(trials)

    out_snapshot = deepcopy(snapshot)
    out_trials: List[Dict[str, Any]] = out_snapshot.get("trials", [])

    changed: List[Dict[str, Any]] = []

    for t in out_trials:
        old = t.get("modality")
        trial_obj = _as_trial_obj(t)
        new = assign_modality(trial_obj)
        if old != new:
            changed.append(
                {
                    "nct_id": t.get("nct_id"),
                    "title": t.get("title"),
                    "old": old,
                    "new": new,
                    "interventions": t.get("interventions", []),
                    "study_type": t.get("study_type"),
                }
            )
        t["modality"] = new

    after_counts = _count_modalities(out_trials)
    diffs = _diff_counts(before_counts, after_counts)

    # Update metadata (non-destructive, additive)
    meta = out_snapshot.setdefault("metadata", {})
    meta["modality_reclassified_at"] = datetime.now().isoformat(timespec="seconds")
    meta["modality_reclassifier"] = "classifiers.modality.assign_modality"
    meta["modality_reclassifier_version"] = "v1.1"

    out_path = Path(args.out) if args.out else _default_out_path(in_path)
    if out_path.exists():
        raise SystemExit(f"Refusing to overwrite existing file: {out_path}")

    _write_json(out_path, out_snapshot)

        # Write full change log (ALL changes, not just printed examples)
    changes_path = Path(args.changes_out) if args.changes_out else _default_changes_path(in_path)
    if changes_path.exists():
        raise SystemExit(f"Refusing to overwrite existing file: {changes_path}")

    changes_payload = {
        "input": str(in_path),
        "output_snapshot": str(out_path),
        "changed_count": len(changed),
        "changed": changed,
    }
    _write_json(changes_path, changes_payload)

    # --- Print summary ---
    print(f"\nInput:  {in_path}")
    print(f"Output: {out_path}")
    print(f"\nTrials: {len(trials)}")
    print(f"Changed: {len(changed)} ({(len(changed)/max(len(trials),1))*100:.2f}%)")
    print(f"Changes: {changes_path}")

    print("\nModality count deltas (after - before):")
    if not diffs:
        print("  (no changes)")
    else:
        for lab, delta in diffs:
            sign = "+" if delta > 0 else ""
            print(f"  {lab}: {sign}{delta}")

    if changed:
        print(f"\nExamples of changed trials (up to {args.max_examples}):")
        for ex in changed[: args.max_examples]:
            nct = ex.get("nct_id") or "UNKNOWN"
            print(f"- {nct}: {ex.get('old')} -> {ex.get('new')}")
            title = ex.get("title")
            if title:
                print(f"  Title: {title}")
            ints = ex.get("interventions", [])
            if ints:
                print(f"  Interventions: {ints}")
            st = ex.get("study_type")
            if st:
                print(f"  StudyType: {st}")
            print()

    print("\nDone.")


if __name__ == "__main__":
    main()
