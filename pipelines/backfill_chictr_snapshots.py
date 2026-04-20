"""
pipelines/backfill_chictr_snapshots.py
---------------------------------------
Synthesise historical ChiCTR snapshots by filtering the current corpus
by `first_posted_date` (which was mapped from ChiCTR's registration_date
in classify_chictr_to_snapshot.py).

Why this exists:
    ChiCTR scrapes accumulate slowly; you often have only one or two
    real captured snapshots, leaving mk_cw1 / sci_cw1 momentum analytics
    starved for a baseline. A single run of this script produces a
    cadence-spaced series of synthetic snapshots representing "the
    corpus state as of date X, classified with today's classifier."

Properties of synthetic snapshots:
    - Consistent corpus completeness across dates (no scrape-backfill
      artifacts).
    - Consistent classifier version across dates (no TA/modality drift).
    - Registration-date filter is stable -- a trial with reg_date
      2025-11-12 appears in every synthetic snapshot dated 2025-11-12
      or later.
    - metadata.synthetic = True so nobody confuses them with real
      scraped snapshots.

Usage:
    PYTHONPATH=. python pipelines/backfill_chictr_snapshots.py
    PYTHONPATH=. python pipelines/backfill_chictr_snapshots.py --weeks 10 --interval 7
    PYTHONPATH=. python pipelines/backfill_chictr_snapshots.py --source path/to/snap.json
    PYTHONPATH=. python pipelines/backfill_chictr_snapshots.py --force
"""

from __future__ import annotations
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

CHICTR_SNAP_DIR = Path("storage/snapshots/clinical_trials_v2/chictr")


def _parse_date(s):
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _latest_real_snapshot():
    if not CHICTR_SNAP_DIR.exists():
        return None
    files = sorted(
        [f for f in CHICTR_SNAP_DIR.glob("*_chictr_v1.json")
         if "_synth" not in f.name],
        key=lambda p: p.name,
        reverse=True,
    )
    return files[0] if files else None


def _write_synthetic(source_meta: dict, source_file: Path, cutoff: date,
                     filtered_trials: list, out_dir: Path) -> Path:
    """Write one synthetic snapshot for the given cutoff."""
    drug_count = sum(1 for t in filtered_trials if t.get("is_drug_trial"))

    metadata = {
        "source":              "ChiCTR",
        "registry":            "ChiCTR",
        "as_of":               cutoff.isoformat(),
        "window_start":        None,
        "window_end":          cutoff.isoformat(),
        "total_trials":        len(filtered_trials),
        "drug_trials":         drug_count,
        "generated_at":        datetime.now().isoformat(),
        "classifier":          source_meta.get("classifier", "intl_drug_classifier_v2"),
        "input_file":          source_meta.get("input_file"),
        # Flags that identify this as a derived snapshot
        "synthetic":           True,
        "backfilled_from":     source_file.name,
        "backfill_cutoff_date": cutoff.isoformat(),
    }

    out_name = f"{cutoff.isoformat()}_chictr_v1_synth.json"
    out_path = out_dir / out_name
    out_path.write_text(
        json.dumps({"metadata": metadata, "trials": filtered_trials},
                   ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return out_path


def backfill(source_path: Path, out_dir: Path,
             weeks: int, interval_days: int, anchor: date,
             force: bool = False, verbose: bool = True) -> list[Path]:
    """
    Produce `weeks` synthetic snapshots at `interval_days` spacing, anchored
    at (and working backwards from) `anchor` day.

    Returns list of written paths (may be shorter than `weeks` if some already
    exist and force=False).
    """
    if verbose:
        print(f"Loading source: {source_path}")

    t0 = datetime.now()
    with source_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    src_meta   = raw.get("metadata", {})
    src_trials = raw.get("trials", [])
    if verbose:
        print(f"  loaded {len(src_trials):,} trials "
              f"in {(datetime.now()-t0).total_seconds():.1f}s")

    # Pre-parse registration dates once
    parsed = []
    no_date = 0
    for t in src_trials:
        d = _parse_date(t.get("first_posted_date"))
        if d is None:
            no_date += 1
            continue
        parsed.append((d, t))
    parsed.sort(key=lambda x: x[0])
    if verbose:
        print(f"  {len(parsed):,} trials have parseable registration dates "
              f"({no_date:,} skipped with missing/invalid dates)")

    # Cutoffs (oldest first for stable write order)
    cutoffs = sorted(
        {anchor - timedelta(days=i * interval_days) for i in range(1, weeks + 1)}
    )
    if verbose:
        print(f"  generating {len(cutoffs)} cutoffs from "
              f"{cutoffs[0]} to {cutoffs[-1]}")

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    skipped_existing = 0

    for cutoff in cutoffs:
        out_name = f"{cutoff.isoformat()}_chictr_v1_synth.json"
        out_path = out_dir / out_name
        if out_path.exists() and not force:
            skipped_existing += 1
            if verbose:
                print(f"    {cutoff}  skip (exists) -- use --force to overwrite")
            continue

        # Binary-search-style filter since parsed is sorted by date
        filtered_trials = [t for (d, t) in parsed if d <= cutoff]
        drug_n = sum(1 for t in filtered_trials if t.get("is_drug_trial"))

        _write_synthetic(src_meta, source_path, cutoff, filtered_trials, out_dir)
        written.append(out_path)
        if verbose:
            print(f"    {cutoff}  total={len(filtered_trials):>6,}  "
                  f"drug={drug_n:>6,}  -> {out_name}")

    if verbose:
        print(f"\n  wrote {len(written)} synthetic snapshot(s), "
              f"skipped {skipped_existing} existing file(s)")
    return written


def main():
    parser = argparse.ArgumentParser(
        description="Backfill synthetic ChiCTR snapshots from the current corpus."
    )
    parser.add_argument("--source", type=Path, default=None,
                        help="Path to a ChiCTR _chictr_v1.json to use as the source corpus. "
                             "Defaults to the latest real snapshot.")
    parser.add_argument("--out-dir", type=Path, default=CHICTR_SNAP_DIR,
                        help="Directory to write synthetic snapshots into.")
    parser.add_argument("--weeks", type=int, default=10,
                        help="How many past weekly snapshots to synthesise (default: 10).")
    parser.add_argument("--interval", type=int, default=7,
                        help="Days between cutoffs (default: 7 = weekly).")
    parser.add_argument("--anchor", default=None,
                        help="Anchor date YYYY-MM-DD for the most recent cutoff "
                             "(default: today).")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing synthetic files instead of skipping.")
    args = parser.parse_args()

    src = args.source or _latest_real_snapshot()
    if not src or not src.exists():
        print("ERROR: could not find a source ChiCTR snapshot.", file=sys.stderr)
        print("       Provide one with --source or run the ChiCTR scrape + classify first.",
              file=sys.stderr)
        sys.exit(1)

    anchor = (datetime.strptime(args.anchor, "%Y-%m-%d").date()
              if args.anchor else date.today())

    print("=" * 64)
    print("  ChiCTR Synthetic Snapshot Backfill")
    print("=" * 64)
    print(f"  Source:   {src}")
    print(f"  Out dir:  {args.out_dir}")
    print(f"  Anchor:   {anchor}")
    print(f"  Weeks:    {args.weeks}  (interval {args.interval}d)")
    print(f"  Force:    {args.force}")
    print()

    written = backfill(
        source_path=src,
        out_dir=args.out_dir,
        weeks=args.weeks,
        interval_days=args.interval,
        anchor=anchor,
        force=args.force,
    )

    print()
    print("=" * 64)
    print(f"  Done. {len(written)} synthetic snapshot(s) written.")
    print("=" * 64)


if __name__ == "__main__":
    main()
