# pipelines/audit_ta_snapshot.py

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analytics.ta_audit import audit_trials


def main():
    parser = argparse.ArgumentParser(
        description="Audit therapeutic area (TA) assignments in a snapshot JSON"
    )
    parser.add_argument(
        "--path",
        required=True,
        help="Path to snapshot JSON (e.g., storage/snapshots/.../YYYY-MM-DD.json)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of flagged trials to print",
    )
    args = parser.parse_args()

    snapshot_path = Path(args.path)
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    trials = data.get("trials", []) or []

    flags, infos, counts = audit_trials(trials)

    flag_counts = {}
    for f in flags:
        flag_counts[f.reason] = flag_counts.get(f.reason, 0) + 1

    print(f"Loaded trials: {len(trials)}")
    print(f"Flags found: {len(flags)}\n")

    print("Flag counts (hard mismatches only):")
    for reason, count in sorted(flag_counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {reason}: {count}")

    print("\nAudit reason counts (includes INFO-only):")
    for reason, count in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {reason}: {count}")

    print("\nExamples (flagged trials):")
    for f in flags[: args.limit]:
        cond0 = f.conditions[0] if f.conditions else ""
        print(
            f"- {f.nct_id} | assigned={f.assigned_ta} | expected={f.expected_ta} | {f.reason}"
        )
        print(f"  title: {f.title[:120]}")
        print(f"  cond0: {cond0[:120]}\n")
    
    print("\nExamples (INFO-only):")
    info_mismatches = [i for i in infos if i.assigned_ta != i.suggested_ta]
    for info in info_mismatches[: args.limit]:
        cond0 = info.conditions[0] if info.conditions else ""
        print(f"- {info.nct_id} | assigned={info.assigned_ta} | suggested={info.suggested_ta} | {info.reason}")
        print(f"  title: {info.title[:120]}")
        print(f"  cond0: {cond0[:120]}\n")


if __name__ == "__main__":
    main()
