"""
run_diff_chictr.py -- Interactive launcher for the ChiCTR snapshot diff.

Auto-discovers ChiCTR snapshots in
storage/snapshots/clinical_trials_v2/chictr/, presents numbered menus,
then invokes pipelines/diff_chictr_snapshots.py.

Usage:
    PYTHONPATH=. python pipelines/run_diff_chictr.py
"""

from __future__ import annotations
import sys
from datetime import datetime
from pathlib import Path

W = 60
SNAP_DIR = Path("storage/snapshots/clinical_trials_v2/chictr")
OUT_DIR  = Path("storage/chictr_changelogs")


def _discover():
    if not SNAP_DIR.exists():
        return []
    files = list(SNAP_DIR.glob("*_chictr_v1.json"))
    files.sort(key=lambda p: p.name, reverse=True)
    return files


def _file_summary(p):
    sz = p.stat().st_size / 1e6
    mt = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return f"{p.name}  ({sz:.1f} MB, {mt})"


def _pick(files, label, default_idx):
    print(f"\n  Available {label}:")
    print(f"  {'-'*55}")
    for i, f in enumerate(files, 1):
        marker = " (default)" if i == default_idx else ""
        print(f"    {i:2d}) {_file_summary(f)}{marker}")
        if i >= 15:
            if len(files) > 15:
                print(f"        ... and {len(files)-15} more")
            break
    print()
    while True:
        raw = input(f"  Select {label} [1-{len(files)}, default {default_idx}]: ").strip()
        if raw == "":
            return files[default_idx-1]
        try:
            n = int(raw)
            if 1 <= n <= len(files):
                return files[n-1]
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(files)}.")


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print()
    print("=" * W)
    print("  ChiCTR Snapshot Diff -- Interactive")
    print("=" * W)
    print(f"  Today: {today}")
    print(f"  Snapshot dir: {SNAP_DIR}")

    files = _discover()
    if len(files) < 2:
        print(f"\n  ERROR: Need at least 2 ChiCTR snapshots.")
        print(f"  Found: {len(files)}")
        for f in files:
            print(f"    {f}")
        sys.exit(1)

    print(f"  Found: {len(files)} snapshot(s)")

    current = _pick(files, "CURRENT snapshot (most recent)", default_idx=1)
    remaining = [f for f in files if f != current]
    prior = _pick(remaining, "PRIOR snapshot (baseline)", default_idx=1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prior_stem = prior.stem.split("_chictr_v1")[0]
    curr_stem  = current.stem.split("_chictr_v1")[0]
    enr_path  = OUT_DIR / f"chictr_enriched_{curr_stem}_vs_{prior_stem}.json"
    clog_path = OUT_DIR / f"chictr_changelog_{curr_stem}_vs_{prior_stem}.json"

    print()
    print(f"  {'-'*55}")
    print(f"  Prior:     {prior}")
    print(f"  Current:   {current}")
    print(f"  {'-'*55}")
    print(f"  Outputs:")
    print(f"    Enriched:  {enr_path}")
    print(f"    Changelog: {clog_path}")
    print(f"  {'-'*55}")
    print()
    while True:
        raw = input("  Proceed? [Y/n]: ").strip().lower()
        if raw in ("", "y", "yes"):
            break
        if raw in ("n", "no"):
            print("  Cancelled.")
            sys.exit(0)

    from pipelines.diff_chictr_snapshots import main as diff_main
    diff_main([
        "--prior", str(prior),
        "--current", str(current),
        "--output-enriched", str(enr_path),
        "--output-changelog", str(clog_path),
    ])


if __name__ == "__main__":
    main()
