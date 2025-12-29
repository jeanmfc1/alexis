from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

from analytics.modality_audit import audit_trials


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _as_trial_obj(trial_dict: Dict[str, Any]):
    """
    Build a minimal attribute-style object for audit_trials().
    The audit expects: nct_id (optional), study_type, interventions, modality.
    """
    return SimpleNamespace(
        nct_id=trial_dict.get("nct_id"),
        study_type=trial_dict.get("study_type"),
        interventions=trial_dict.get("interventions") or [],
        modality=trial_dict.get("modality"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit modality assignments for a clinical trials snapshot.")
    parser.add_argument("--path", required=True, help="Path to snapshot JSON (original or reclassified)")
    parser.add_argument("--max_examples", type=int, default=2000, help="Max examples to print per section")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"Snapshot not found: {path}")

    snapshot = _load_json(path)
    trials: List[Dict[str, Any]] = snapshot.get("trials", [])
    if not isinstance(trials, list):
        raise SystemExit("Snapshot JSON malformed: 'trials' must be a list.")

    trial_objs = [_as_trial_obj(t) for t in trials]

    flags, infos, counts = audit_trials(trial_objs)

    print(f"\nSnapshot: {path}")
    print(f"Trials: {len(trials)}")

    # --- Summary counts ---
    print("\n=== Flag counts ===")
    flag_keys = sorted(k for k in counts.keys() if k.startswith("flags_"))
    if not flag_keys:
        print("  (no flag counters)")
    else:
        for k in flag_keys:
            print(f"  {k}: {counts[k]}")
    print(f"  flags_total: {len(flags)}")

    print("\n=== INFO counts ===")
    info_keys = sorted(k for k in counts.keys() if k.startswith("info_"))
    if not info_keys:
        print("  (no info counters)")
    else:
        for k in info_keys:
            print(f"  {k}: {counts[k]}")
    print(f"  infos_total: {len(infos)}")

    # --- Examples ---
    if flags:
        print(f"\n=== Flag examples (up to {args.max_examples}) ===")
        for ex in flags[: args.max_examples]:
            nct = ex.get("nct_id", "UNKNOWN")
            print(f"- {nct} | {ex.get('type')}: {ex.get('message')}")

    if infos:
        print(f"\n=== INFO examples (up to {args.max_examples}) ===")
        for ex in infos[: args.max_examples]:
            nct = ex.get("nct_id", "UNKNOWN")
            print(f"- {nct} | {ex.get('type')}: {ex.get('message')}")

    print("\nDone.")


if __name__ == "__main__":
    main()
