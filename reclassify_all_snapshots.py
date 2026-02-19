"""
reclassify_all_snapshots.py

Loops every V2 snapshot in the source directory and reclassifies each one
using reclassify_modality_snapshot_v2.reclassify_snapshot().

Features:
    - tqdm progress bar with per-snapshot ETA and trials/sec throughput.
    - Resume-safe: skips any run_id that already has an output in the
      reclassified/ folder.
    - Validates format field before processing — skips non-V2 files.
    - Processes in chronological order (by window_end from metadata).
    - Per-snapshot errors are captured, not fatal; failures are listed in the
      final summary and the full traceback is shown inline.
    - reclassify_snapshot prints ~40 lines of detail per snapshot.  By default
      that output is suppressed and the progress bar stays clean.  Pass
      --verbose to see it.

MUST BE RUN FROM THE PROJECT ROOT — the directory that contains storage/,
classifiers/, policy/, analytics/, utils/.  All paths (source, output, and
the package imports in the reclassifier) are relative to that root.

Usage:
    cd /path/to/ALEXIS                          # project root

    python reclassify_all_snapshots.py          # run with defaults + progress bar
    python reclassify_all_snapshots.py --verbose                # show per-snapshot detail
    python reclassify_all_snapshots.py --dry-run                # preview without running
    python reclassify_all_snapshots.py --source path --out path # explicit directories
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import traceback
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from tqdm import tqdm

from pipelines.reclassify_modality_snapshot_v2 import reclassify_snapshot


# ---------------------------------------------------------------------------
# Constants — match conventions in backfill_weekly_snapshots_v2.py and
# reclassify_modality_snapshot_v2.py
# ---------------------------------------------------------------------------

DEFAULT_SOURCE_DIR  = Path("storage/snapshots/clinical_trials_v2/last_update")
DEFAULT_OUTPUT_DIR  = Path("storage/snapshots/clinical_trials_v2")
RECLASSIFIED_SUBFOLDER = "reclassified"
EXPECTED_FORMAT     = "ALEXIS_SNAPSHOT_V2"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class SnapshotMeta(NamedTuple):
    path:       Path
    run_id:     str
    window_end: str   # ISO date string; used for chronological sort
    format:     str


def read_snapshot_meta(path: Path) -> SnapshotMeta | None:
    """Extract lightweight metadata from a snapshot JSON.  Returns None on
    parse failure so the caller can skip gracefully."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        meta = data.get("metadata", {})
        return SnapshotMeta(
            path=path,
            run_id=meta.get("run_id", path.stem),
            window_end=meta.get("window_end", ""),
            format=meta.get("format", ""),
        )
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  [WARN] Could not read {path.name}: {exc}")
        return None


def discover_snapshots(source_dir: Path) -> list[SnapshotMeta]:
    """Find, parse, and chronologically sort all snapshot JSONs in source_dir."""
    if not source_dir.is_dir():
        print(f"[ERROR] Source directory does not exist: {source_dir}")
        sys.exit(1)

    jsons = sorted(source_dir.glob("*.json"))
    if not jsons:
        print(f"[WARN] No .json files found in {source_dir}")
        return []

    print(f"Scanning {len(jsons)} files in {source_dir} ...")
    metas = [m for p in jsons if (m := read_snapshot_meta(p)) is not None]
    metas.sort(key=lambda m: (m.window_end, m.run_id))
    return metas


def already_reclassified(run_id: str, output_base_dir: Path) -> bool:
    """True if a reclassified output for this run_id already exists.
    Globs rather than assuming exact filename — save_trial_snapshot_v2 may
    append timestamps or other suffixes."""
    reclass_dir = output_base_dir / RECLASSIFIED_SUBFOLDER
    if not reclass_dir.is_dir():
        return False
    return any(reclass_dir.glob(f"*{run_id}*.json"))


# ---------------------------------------------------------------------------
# Main batch loop
# ---------------------------------------------------------------------------


def run_batch(source_dir: Path, output_dir: Path, *, dry_run: bool, verbose: bool) -> None:
    snapshots = discover_snapshots(source_dir)
    if not snapshots:
        print("Nothing to do.")
        return

    # --- filter --------------------------------------------------------------
    to_process:     list[SnapshotMeta] = []
    skipped_format: list[SnapshotMeta] = []
    skipped_done:   list[SnapshotMeta] = []

    for snap in snapshots:
        if snap.format != EXPECTED_FORMAT:
            skipped_format.append(snap)
        elif already_reclassified(snap.run_id, output_dir):
            skipped_done.append(snap)
        else:
            to_process.append(snap)

    # --- plan ----------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"  RECLASSIFICATION BATCH")
    print(f"{'='*70}")
    print(f"  Source dir   : {source_dir}")
    print(f"  Output dir   : {output_dir}/{RECLASSIFIED_SUBFOLDER}/")
    print(f"  Total found  : {len(snapshots)}")
    print(f"  Already done : {len(skipped_done)}")
    if skipped_format:
        print(f"  Bad format   : {len(skipped_format)}  "
              f"({', '.join(s.run_id for s in skipped_format)})")
    print(f"  To process   : {len(to_process)}")
    print(f"{'='*70}\n")

    if dry_run:
        if not to_process:
            print("  (nothing pending)")
        else:
            print("[DRY RUN] Would process:\n")
            for i, snap in enumerate(to_process, 1):
                print(f"  {i:>3}. {snap.run_id}  "
                      f"(window_end={snap.window_end}, file={snap.path.name})")
        return

    if not to_process:
        print("All snapshots already reclassified. Nothing to do.")
        return

    # --- process -------------------------------------------------------------
    succeeded: list[tuple[SnapshotMeta, Path]] = []
    failed:    list[tuple[SnapshotMeta, str]]  = []
    captured:  dict[str, str] = {}              # run_id → stdout captured during run

    batch_start = datetime.now()

    # tqdm renders on stderr so it doesn't collide with any stdout we let
    # through in verbose mode.  desc updates to the current run_id each tick.
    progress = tqdm(
        total=len(to_process),
        desc=to_process[0].run_id if to_process else "",
        unit="snapshot",
        file=sys.stderr,
        leave=True,                 # keep the finished bar visible
    )

    for snap in to_process:
        progress.set_description(snap.run_id)

        try:
            if verbose:
                # Let reclassify_snapshot print normally; progress bar is on
                # stderr so the two don't collide.
                out_path = reclassify_snapshot(
                    snapshot_path=snap.path,
                    output_base_dir=output_dir,
                )
            else:
                # Capture stdout so the progress bar stays clean.  We keep the
                # captured text around — it gets printed for any snapshot that
                # later fails, so the user can debug without re-running.
                buf = io.StringIO()
                with redirect_stdout(buf):
                    out_path = reclassify_snapshot(
                        snapshot_path=snap.path,
                        output_base_dir=output_dir,
                    )
                captured[snap.run_id] = buf.getvalue()

            succeeded.append((snap, out_path))

        except Exception as exc:
            tb = traceback.format_exc()
            failed.append((snap, f"{exc}\n{tb}"))
            # Print failure immediately above the progress bar via tqdm.write
            # so it's visible without waiting for the summary.
            tqdm.write(f"  ✗ {snap.run_id}: {exc}", file=sys.stderr)

        progress.update(1)

    progress.close()

    # --- summary -------------------------------------------------------------
    batch_elapsed = (datetime.now() - batch_start).total_seconds()
    rate = f"  ({len(succeeded) / batch_elapsed:.1f} snapshots/sec)" if batch_elapsed else ""

    print(f"\n{'='*70}")
    print(f"  BATCH COMPLETE")
    print(f"{'='*70}")
    print(f"  Elapsed          : {batch_elapsed:.1f}s{rate}")
    print(f"  Succeeded        : {len(succeeded)}")
    print(f"  Failed           : {len(failed)}")
    print(f"  Already skipped  : {len(skipped_done)}")
    if skipped_format:
        print(f"  Format skipped   : {len(skipped_format)}")

    if failed:
        print(f"\n  Failures:")
        for snap, err in failed:
            first_line = err.split("\n")[0]
            print(f"    {snap.run_id}: {first_line}")

        # Surface any captured stdout from failed snapshots so the user can
        # see what the reclassifier was doing right before it blew up.
        print(f"\n  Captured output from failed snapshots:")
        for snap, _ in failed:
            if snap.run_id in captured:
                print(f"\n  --- {snap.run_id} ---")
                print(captured[snap.run_id])

    print(f"{'='*70}\n")

    if failed:
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Batch-reclassify all V2 snapshots (resume-safe, progress bar). "
                    "Must be run from the ALEXIS project root.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help=f"Directory containing source snapshots  (default: {DEFAULT_SOURCE_DIR})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Base output directory; reclassified/ is created inside  (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be processed without running anything.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print the per-snapshot detail from the reclassifier "
             "(suppressed by default to keep the progress bar clean).",
    )

    args = parser.parse_args()

    run_batch(
        source_dir=args.source,
        output_dir=args.out,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
