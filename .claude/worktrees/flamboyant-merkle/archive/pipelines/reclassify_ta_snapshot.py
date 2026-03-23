from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Tuple

from classifiers.therapeutic_area import assign_therapeutic_area


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _ta_counts(trials: List[dict]) -> Counter:
    return Counter((t.get("therapeutic_area") or "Unknown").strip() for t in trials)


def _reclassify_trials(trials: List[dict]) -> Tuple[List[dict], List[dict]]:
    """
    Returns:
      new_trials: trials with updated therapeutic_area
      changes: list of dicts describing changed trials
    """
    new_trials: List[dict] = []
    changes: List[dict] = []

    for t in trials:
        t2 = deepcopy(t)
        old_ta = (t2.get("therapeutic_area") or "Unknown").strip()

        # Build a minimal object with the attributes the classifier reads
        class TrialStub:
            def __init__(self, title, conditions):
                self.title = title
                self.conditions = conditions

        stub = TrialStub(
            title=t2.get("title") or "",
            conditions=t2.get("conditions") or [],
        )

        new_ta = assign_therapeutic_area(stub)

        t2["therapeutic_area"] = new_ta
        new_trials.append(t2)

        if new_ta != old_ta:
            changes.append(
                {
                    "nct_id": t2.get("nct_id", ""),
                    "old_ta": old_ta,
                    "new_ta": new_ta,
                    "title": (t2.get("title") or "")[:160],
                    "cond0": ((t2.get("conditions") or [""])[0] or "")[:160],
                }
            )

    return new_trials, changes


def main() -> None:
    parser = argparse.ArgumentParser(description="Reclassify therapeutic_area in a snapshot JSON.")
    parser.add_argument("--path", required=True, help="Path to snapshot JSON")
    parser.add_argument(
        "--out",
        default=None,
        help="Output path. Default: same folder with '.reclassified.json' suffix",
    )
    parser.add_argument("--limit", type=int, default=25, help="Max examples of changes to print")
    args = parser.parse_args()

    in_path = Path(args.path)
    if not in_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {in_path}")

    data = _load_json(in_path)
    trials = data.get("trials", []) or []

    before_counts = _ta_counts(trials)

    new_data = deepcopy(data)
    new_trials, changes = _reclassify_trials(trials)
    new_data["trials"] = new_trials

    # Add a small summary payload (non-destructive)
    new_data.setdefault("summary", {})
    new_data["summary"]["reclassify"] = {
        "input_path": str(in_path),
        "changed_trials": len(changes),
    }

    after_counts = _ta_counts(new_trials)

    # Resolve output path
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = in_path.with_suffix("")  # drop .json
        out_path = Path(str(out_path) + ".reclassified.json")

    _write_json(out_path, new_data)

    # Print summary
    print(f"Input:  {in_path}")
    print(f"Output: {out_path}")
    print(f"Trials: {len(trials)}")
    print(f"Changed therapeutic_area: {len(changes)}\n")

    # Print count deltas
    all_keys = sorted(set(before_counts) | set(after_counts))
    print("TA count changes (before -> after, delta):")
    for k in all_keys:
        b = before_counts.get(k, 0)
        a = after_counts.get(k, 0)
        d = a - b
        if d != 0:
            print(f"  {k}: {b} -> {a} ({d:+d})")

    # Print examples
    if changes:
        print("\nExamples of changed trials:")
        for c in changes[: args.limit]:
            print(f"- {c['nct_id']} | {c['old_ta']} -> {c['new_ta']}")
            print(f"  title: {c['title']}")
            print(f"  cond0:  {c['cond0']}\n")


if __name__ == "__main__":
    main()
