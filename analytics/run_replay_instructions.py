"""
run_replay_instructions.py — Interactive launcher to build a new master DB
by replaying instruction files against a base master.

Auto-discovers master DBs and instruction files, lets the user pick a base
and a contiguous range of instructions, then calls
analytics.update_categorizer.replay_all_instructions.

Usage:
    PYTHONPATH=. python analytics/run_replay_instructions.py
"""

from __future__ import annotations
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# ── File discovery ──────────────────────────────────────────────

MASTER_DIRS = [
    Path("storage/snapshots/clinical_trials_v2/active_universe"),
    Path("storage/snapshots/clinical_trials_v2/reclassified"),
]

INSTRUCTIONS_BASE = Path("storage/instructions")
OUTPUT_BASE = Path("storage/snapshots/clinical_trials_v2/active_universe")

_SEQ_RE = re.compile(r"instructions_(\d+)\.json$")


def _discover_files(dirs: list[Path], pattern: str) -> list[Path]:
    files = []
    for d in dirs:
        if d.exists():
            files.extend(d.glob(pattern))
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _file_summary(path: Path) -> str:
    size_mb = path.stat().st_size / 1e6
    mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return f"{path.name}  ({size_mb:.1f} MB, {mtime})"


def _pick_file(files: list[Path], label: str) -> Path:
    print(f"\n  Available {label}:")
    print(f"  {'─' * 55}")
    for i, f in enumerate(files, 1):
        print(f"    {i:2d}) {_file_summary(f)}")
        if i >= 15:
            remaining = len(files) - 15
            if remaining > 0:
                print(f"        ... and {remaining} more")
            break
    print()

    while True:
        raw = input(f"  Select {label} [1-{len(files)}]: ").strip()
        try:
            idx = int(raw)
            if 1 <= idx <= len(files):
                selected = files[idx - 1]
                print(f"  → {selected}")
                return selected
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(files)}.")


def _seq_of(path: Path) -> int:
    m = _SEQ_RE.search(path.name)
    return int(m.group(1)) if m else -1


def _pick_instruction_range(all_inst: list[Path]) -> list[Path]:
    """Show instructions in chronological order; user picks a range."""
    ordered = sorted(all_inst, key=_seq_of)
    print(f"\n  Available instruction files ({len(ordered)} total):")
    print(f"  {'─' * 55}")
    for f in ordered:
        seq = _seq_of(f)
        print(f"    {seq:>3}) {_file_summary(f)}")
    print()
    print("  Enter a sequence range to apply (e.g. '1-12' or '5-5').")
    print("  Press Enter to apply ALL listed files in order.")
    while True:
        raw = input("  Range: ").strip()
        if not raw:
            return ordered
        try:
            if "-" in raw:
                lo_s, hi_s = raw.split("-", 1)
                lo, hi = int(lo_s), int(hi_s)
            else:
                lo = hi = int(raw)
            if lo > hi:
                print("  Low must be ≤ high.")
                continue
            picked = [f for f in ordered if lo <= _seq_of(f) <= hi]
            if not picked:
                print("  No files in that range.")
                continue
            return picked
        except ValueError:
            print("  Could not parse range. Try '1-12'.")


# ── Main ────────────────────────────────────────────────────────

def main():
    today = datetime.now().strftime("%Y-%m-%d")

    print()
    print("=" * 60)
    print("  ALEXIS Master DB Replay")
    print("=" * 60)
    print(f"  Today: {today}")

    # ── Base master ──
    masters = _discover_files(MASTER_DIRS, "master_*.json")
    if not masters:
        print("\n  ERROR: No master DB files found.")
        print(f"  Searched: {[str(d) for d in MASTER_DIRS]}")
        sys.exit(1)
    base_master = _pick_file(masters, "base master DB")

    # ── Instruction files ──
    all_inst = list(INSTRUCTIONS_BASE.glob("instructions_*.json"))
    if not all_inst:
        print(f"\n  ERROR: No instruction files in {INSTRUCTIONS_BASE}")
        sys.exit(1)
    inst_paths = _pick_instruction_range(all_inst)

    # ── Output path ──
    default_out = OUTPUT_BASE / f"master_replay_{today}.json"
    print(f"\n  Output master path [default: {default_out}]: ", end="")
    raw = input().strip()
    out_path = Path(raw) if raw else default_out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Confirmation ──
    seqs = [_seq_of(p) for p in inst_paths]
    print()
    print(f"  {'─' * 55}")
    print(f"  Base master:   {base_master}")
    print(f"  Instructions:  {len(inst_paths)} files (seq {min(seqs)}–{max(seqs)})")
    print(f"  Output:        {out_path}")
    print(f"  {'─' * 55}")

    if out_path.exists():
        print(f"  ⚠ {out_path} already exists and will be OVERWRITTEN.")
    print()
    while True:
        raw = input("  Proceed? [Y/n]: ").strip().lower()
        if raw in ("", "y", "yes"):
            break
        if raw in ("n", "no"):
            print("  Cancelled.")
            sys.exit(0)

    # ── Run ──
    from analytics.update_categorizer import replay_all_instructions
    final_trials = replay_all_instructions(
        base_master_path=str(base_master),
        instruction_paths=[str(p) for p in inst_paths],
        output_path=str(out_path),
    )

    # ── Post-run sanity ──
    with open(base_master, "r", encoding="utf-8") as f:
        base_data = json.load(f)
    base_n = len(base_data.get("trials", []))
    delta = len(final_trials) - base_n

    W = 60
    print(f"\n{'=' * W}")
    print(f"  REPLAY SUMMARY")
    print(f"{'=' * W}")
    print(f"  Base trials:     {base_n:,}")
    print(f"  Final trials:    {len(final_trials):,}")
    print(f"  Net change:      {delta:+,}")
    print(f"  Output:          {out_path}")
    print()


if __name__ == "__main__":
    main()
