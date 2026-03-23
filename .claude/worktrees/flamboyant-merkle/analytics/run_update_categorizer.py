"""
run_update_categorizer.py — Interactive launcher for the ALEXIS Update Categorizer.

Auto-discovers master DBs and pulse snapshots, presents numbered menus,
creates output directories, and runs the categorizer.

Usage:
    PYTHONPATH=. python analytics/run_update_categorizer.py
"""

from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime

# ── File discovery ──────────────────────────────────────────────

MASTER_DIRS = [
    Path("storage/snapshots/clinical_trials_v2/active_universe"),
    Path("storage/snapshots/clinical_trials_v2/reclassified"),
]

PULSE_DIRS = [
    Path("storage/snapshots/clinical_trials_v2/last_update"),
]

OUTPUT_BASE = Path("storage/changelogs")
INSTRUCTIONS_BASE = Path("storage/instructions")


def _discover_files(dirs: list[Path], pattern: str = "*.json") -> list[Path]:
    """Find JSON files across multiple directories, sorted newest first."""
    files = []
    for d in dirs:
        if d.exists():
            files.extend(d.glob(pattern))
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _file_summary(path: Path) -> str:
    """One-line summary: filename, size, modified date."""
    size_mb = path.stat().st_size / 1e6
    mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return f"{path.name}  ({size_mb:.1f} MB, {mtime})"


def _pick_file(files: list[Path], label: str) -> Path:
    """Present numbered menu, return selected path."""
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


# ── Interactive prompts ─────────────────────────────────────────

def prompt_config() -> dict:
    """Interactive configuration for the update categorizer."""
    today = datetime.now().strftime("%Y-%m-%d")

    print()
    print("=" * 60)
    print("  ALEXIS Update Categorizer")
    print("=" * 60)
    print(f"  Today: {today}")

    # ── Master DB ──
    masters = _discover_files(MASTER_DIRS, "master_*.json")
    if not masters:
        print("\n  ERROR: No master DB files found.")
        print(f"  Searched: {[str(d) for d in MASTER_DIRS]}")
        sys.exit(1)

    master_path = _pick_file(masters, "master DB")

    # ── Pulse snapshot ──
    pulses = _discover_files(PULSE_DIRS)
    if not pulses:
        print("\n  ERROR: No pulse snapshot files found.")
        print(f"  Searched: {[str(d) for d in PULSE_DIRS]}")
        sys.exit(1)

    pulse_path = _pick_file(pulses, "pulse snapshot")

    # ── Drug-only filter ──
    print()
    while True:
        raw = input("  Drug trials only? [Y/n]: ").strip().lower()
        if raw in ("", "y", "yes"):
            drug_only = True
            break
        elif raw in ("n", "no"):
            drug_only = False
            break
        print("  Please enter Y or N.")

    # ── Sequence number ──
    # Auto-detect from existing instruction files
    existing_instructions = sorted(INSTRUCTIONS_BASE.glob("instructions_*.json"))
    next_seq = len(existing_instructions) + 1

    print(f"\n  Instruction sequence number [default: {next_seq}]: ", end="")
    raw = input().strip()
    if raw:
        try:
            next_seq = int(raw)
        except ValueError:
            pass

    # ── Derive output paths ──
    pulse_stem = pulse_path.stem  # e.g. "2026-02-20_2026-02-27_v1"

    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)
    INSTRUCTIONS_BASE.mkdir(parents=True, exist_ok=True)

    enriched_path = OUTPUT_BASE / f"enriched_{pulse_stem}.json"
    changelog_path = OUTPUT_BASE / f"changelog_{pulse_stem}.json"
    instructions_path = INSTRUCTIONS_BASE / f"instructions_{next_seq:03d}.json"

    # ── Confirmation ──
    print()
    print(f"  {'─' * 55}")
    print(f"  Master:       {master_path}")
    print(f"  Snapshot:     {pulse_path}")
    print(f"  Drug only:    {drug_only}")
    print(f"  Sequence:     {next_seq}")
    print(f"  {'─' * 55}")
    print(f"  Outputs:")
    print(f"    Enriched:     {enriched_path}")
    print(f"    Changelog:    {changelog_path}")
    print(f"    Instructions: {instructions_path}")
    print(f"  {'─' * 55}")
    print()

    while True:
        raw = input("  Proceed? [Y/n]: ").strip().lower()
        if raw in ("", "y", "yes"):
            break
        elif raw in ("n", "no"):
            print("  Cancelled.")
            sys.exit(0)

    return {
        "master": str(master_path),
        "snapshot": str(pulse_path),
        "drug_only": drug_only,
        "sequence": next_seq,
        "enriched": str(enriched_path),
        "changelog": str(changelog_path),
        "instructions": str(instructions_path),
    }


# ── Main ────────────────────────────────────────────────────────

def main():
    config = prompt_config()

    # Build argv for the existing update_categorizer
    argv = [
        "--master", config["master"],
        "--snapshot", config["snapshot"],
        "--output-enriched", config["enriched"],
        "--output-changelog", config["changelog"],
        "--output-instructions", config["instructions"],
        "--sequence", str(config["sequence"]),
    ]
    if config["drug_only"]:
        argv.append("--drug-only")

    # Patch sys.argv and run
    sys.argv = ["update_categorizer.py"] + argv

    from analytics.update_categorizer import main as categorizer_main
    categorizer_main()

    # ── Post-run validation ─────────────────────────────────────
    import json
    from collections import Counter

    snap_data = json.load(open(config["snapshot"]))
    enriched_data = json.load(open(config["enriched"]))
    instructions_data = json.load(open(config["instructions"]))

    snap_drug = [t for t in snap_data["trials"] if t.get("is_drug_trial")]
    snap_ncts = set(t["nct_id"] for t in snap_drug)
    enriched_ncts = set(t["nct_id"] for t in enriched_data["trials"])

    missing = snap_ncts - enriched_ncts
    extra = enriched_ncts - snap_ncts

    no_cat = [t["nct_id"] for t in enriched_data["trials"]
              if not t.get("update_categories")]

    add_ncts = set(t["nct_id"] for t in instructions_data["add"])
    patch_ncts = set(instructions_data["patch"].keys())
    remove_ncts = set(instructions_data["remove"])
    inactive = set(
        t["nct_id"] for t in enriched_data["trials"]
        if any(c["category"] == "inactive_update"
               for c in t.get("update_categories", []))
    )
    accounted = add_ncts | patch_ncts | remove_ncts | inactive
    unaccounted = enriched_ncts - accounted

    W = 60
    print(f"\n{'=' * W}")
    print(f"  COMPLETENESS CHECK")
    print(f"{'=' * W}")
    print(f"  Pulse drug trials:     {len(snap_ncts):,}")
    print(f"  Enriched trials:       {len(enriched_ncts):,}")
    print(f"  Missing from enriched: {len(missing)}")
    print(f"  Extra in enriched:     {len(extra)}")
    print(f"  Trials with no category: {len(no_cat)}")
    print()
    print(f"  Instruction coverage:")
    print(f"    ADD:         {len(add_ncts):>5,}")
    print(f"    PATCH:       {len(patch_ncts):>5,}")
    print(f"    REMOVE:      {len(remove_ncts):>5,}")
    print(f"    SKIP:        {len(inactive):>5,}")
    print(f"    Total:       {len(accounted):>5,}")
    print(f"    Unaccounted: {len(unaccounted):>5}")

    if missing:
        print(f"\n  ⚠ Missing: {list(missing)[:5]}")
    if unaccounted:
        print(f"\n  ⚠ Unaccounted: {list(unaccounted)[:5]}")

    # ── Histogram: categories per trial ─────────────────────────
    cat_counts = [len(t.get("update_categories", []))
                  for t in enriched_data["trials"]]
    hist = Counter(cat_counts)
    max_cats = max(hist.keys())
    max_bar = max(hist.values())
    bar_width = 40

    print(f"\n{'=' * W}")
    print(f"  CATEGORIES PER TRIAL")
    print(f"{'=' * W}")
    print(f"  {'Updates':>8}  {'Trials':>6}  {'':>5}  Distribution")
    print(f"  {'─' * 55}")

    for n in range(1, max_cats + 1):
        count = hist.get(n, 0)
        bar_len = int(bar_width * count / max_bar) if max_bar > 0 else 0
        pct = 100 * count / len(cat_counts) if cat_counts else 0
        bar = "█" * bar_len
        print(f"  {n:>8d}  {count:>6,}  {pct:4.1f}%  {bar}")

    # Multi-category breakdown
    multi = [(t["nct_id"], [c["category"] for c in t["update_categories"]])
             for t in enriched_data["trials"]
             if len(t.get("update_categories", [])) > 1]

    print(f"\n  Single category: {len(cat_counts) - len(multi):,}")
    print(f"  Multi-category:  {len(multi):,} ({100 * len(multi) / len(cat_counts):.1f}%)")

    # Most common category combos
    combo_counter = Counter()
    for _, cats in multi:
        combo_counter[tuple(sorted(cats))] += 1

    print(f"\n  Top category combinations:")
    for combo, n in combo_counter.most_common(10):
        print(f"    {n:>4}  {' + '.join(combo)}")

    print()


if __name__ == "__main__":
    main()
