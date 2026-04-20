"""
pipelines/backfill_enriched_weekly.py
--------------------------------------
For every weekly pulse snapshot in storage/snapshots/.../last_update/,
work out which master DB actually predates that pulse's window_start,
and (re)run analytics/update_categorizer.py against that master so the
resulting enriched + changelog files carry meaningful 'new' counts.

Why this exists:
    update_categorizer.py diffs a pulse against whatever master DB the
    user pointed it at.  If the user picked a master DB whose aact_dir
    postdates the pulse window, trials in the pulse were already in
    master and got labelled update_type='existing' rather than 'new'.
    The weekly dashboard (mk_cw1, mk_wq2, etc.) then sees artificially
    low 'new' counts for those prior weeks.

    This script automates the pairing: for each pulse P, pick the
    master M with the largest aact_dir date that is still <=
    P.window_start.  That is the master as it stood *before* the pulse,
    which is semantically what we want for 'new-this-window'.

Assumes:
    - Pulse files live in MASTER_DIR parent/last_update/ and are named
      YYYY-MM-DD_YYYY-MM-DD_v1.json
    - Master DBs live in MASTER_DIR/master_DB_*.json with
      metadata.aact_dir = 'raw MM-DD-YY' or 'raw MM-DD-YYYY' format.
    - analytics/update_categorizer.py is importable.

Usage:
    PYTHONPATH=. python pipelines/backfill_enriched_weekly.py
    PYTHONPATH=. python pipelines/backfill_enriched_weekly.py --force
    PYTHONPATH=. python pipelines/backfill_enriched_weekly.py --dry-run
    PYTHONPATH=. python pipelines/backfill_enriched_weekly.py --since 2026-03-01
"""

from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT             = Path(__file__).parent.parent
PULSE_DIR        = ROOT / "storage" / "snapshots" / "clinical_trials_v2" / "last_update"
MASTER_DIR       = ROOT / "storage" / "snapshots" / "clinical_trials_v2" / "active_universe"
CHANGELOG_DIR    = ROOT / "storage" / "changelogs"

# Parse dates like 'raw 04-01-26' -> date(2026, 4, 1)
_AACT_DIR_RE = re.compile(r"raw\s+(\d{2})-(\d{2})-(\d{2,4})")


def _parse_aact_dir(s: str) -> date | None:
    if not s: return None
    m = _AACT_DIR_RE.search(s)
    if not m: return None
    mm, dd, yy = m.groups()
    yr = int(yy) + (2000 if len(yy) == 2 else 0)
    try:
        return date(yr, int(mm), int(dd))
    except ValueError:
        return None


def _read_master_metadata(path: Path) -> dict:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        text = f.read(4000)
    m = re.search(r'"metadata"\s*:\s*({.*?})\s*,?\s*(?:"summary"|"trials")', text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def _master_as_of(path: Path) -> date | None:
    """Effective date: aact_dir first, then export_date, then end-of-quarter
    heuristic from filename."""
    meta = _read_master_metadata(path)
    for key in ("aact_dir", "export_date"):
        val = meta.get(key)
        d = _parse_aact_dir(val) if val else None
        if d: return d
    m = re.match(r"master_DB_(\d{4})_Q(\d)", path.name)
    if m:
        y, q = int(m.group(1)), int(m.group(2))
        # Day AFTER end of quarter (masters typically built right after quarter close)
        mm_dd = {1: (4, 1), 2: (7, 1), 3: (10, 1), 4: (1, 1)}[q]
        year  = y + 1 if q == 4 else y
        try:
            return date(year, *mm_dd)
        except ValueError:
            return None
    return None


_PULSE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})_v\d+\.json$")


def _parse_pulse_window(pulse_path: Path) -> tuple[date, date] | None:
    m = _PULSE_RE.match(pulse_path.name)
    if not m: return None
    try:
        return (date.fromisoformat(m.group(1)),
                date.fromisoformat(m.group(2)))
    except ValueError:
        return None


def _pick_master(window_start: date, masters: list[tuple[Path, date]]) -> Path | None:
    """Largest as_of <= window_start."""
    best: tuple[Path, date] | None = None
    for path, d in masters:
        if d <= window_start and (best is None or d > best[1]):
            best = (path, d)
    return best[0] if best else None


def _enriched_current_master(enriched_path: Path) -> str | None:
    """Read the master_source from an existing enriched file's metadata."""
    if not enriched_path.exists():
        return None
    try:
        with enriched_path.open("r", encoding="utf-8", errors="replace") as f:
            # Metadata is near the top -- read first ~2KB only
            text = f.read(3000)
        m = re.search(r'"master_source"\s*:\s*"([^"]+)"', text)
        return m.group(1) if m else None
    except Exception:
        return None


def _run_categorizer(master: Path, pulse: Path, enriched_out: Path,
                     changelog_out: Path, drug_only: bool) -> bool:
    """Run analytics/update_categorizer.py as a subprocess (fresh RAM)."""
    cmd = [
        sys.executable, "-u", "-m", "analytics.update_categorizer",
        "--master",            str(master),
        "--snapshot",          str(pulse),
        "--output-enriched",   str(enriched_out),
        "--output-changelog",  str(changelog_out),
        "--quiet",
    ]
    if drug_only:
        cmd.append("--drug-only")
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    result = subprocess.run(cmd, cwd=str(ROOT), env=env)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description="Regenerate weekly enriched+changelog files against the "
                    "master DB that actually predated each pulse."
    )
    parser.add_argument("--pulse-dir",     type=Path, default=PULSE_DIR)
    parser.add_argument("--master-dir",    type=Path, default=MASTER_DIR)
    parser.add_argument("--changelog-dir", type=Path, default=CHANGELOG_DIR)
    parser.add_argument("--drug-only",     action="store_true", default=True)
    parser.add_argument("--all-trials",    dest="drug_only", action="store_false",
                        help="Do not pass --drug-only to update_categorizer.")
    parser.add_argument("--force",         action="store_true",
                        help="Always regenerate, even if the existing enriched "
                             "file already matches the expected master.")
    parser.add_argument("--dry-run",       action="store_true",
                        help="Show which pulses would be rebuilt, don't run.")
    parser.add_argument("--since",         type=str, default=None,
                        help="YYYY-MM-DD -- skip pulses whose window_start "
                             "is earlier than this date.")
    args = parser.parse_args()

    pulses = sorted(args.pulse_dir.glob("*.json"))
    masters_raw = sorted(args.master_dir.glob("master_DB_*.json"))
    masters: list[tuple[Path, date]] = []
    for m in masters_raw:
        d = _master_as_of(m)
        if d:
            masters.append((m, d))

    print("=" * 70)
    print("  Backfill Enriched Weekly Files")
    print("=" * 70)
    print(f"  Pulse dir:     {args.pulse_dir}")
    print(f"  Master dir:    {args.master_dir}")
    print(f"  Changelog dir: {args.changelog_dir}")
    print(f"  Force:         {args.force}  |  Dry-run: {args.dry_run}  |  "
          f"Drug-only: {args.drug_only}")
    print()
    print(f"  Available masters ({len(masters)}):")
    for path, d in sorted(masters, key=lambda x: x[1]):
        print(f"    {d}  {path.name}")
    print()
    print(f"  Pulses to process: {len(pulses)}")

    since_dt = date.fromisoformat(args.since) if args.since else None

    args.changelog_dir.mkdir(parents=True, exist_ok=True)

    ok = skipped = rebuilt = failed = 0
    for pulse in pulses:
        window = _parse_pulse_window(pulse)
        if not window:
            print(f"  WARN: cannot parse window from {pulse.name}, skipping")
            continue
        ws, we = window
        if since_dt and ws < since_dt:
            continue

        master = _pick_master(ws, masters)
        if not master:
            print(f"  [{ws} -> {we}]  NO MASTER predates this window, skipping")
            skipped += 1
            continue

        stem = pulse.stem
        enriched_path  = args.changelog_dir / f"enriched_{stem}.json"
        changelog_path = args.changelog_dir / f"changelog_{stem}.json"

        # Decide whether to rebuild
        existing_master_src = _enriched_current_master(enriched_path)
        existing_name = Path(existing_master_src).name if existing_master_src else None
        reason = ""
        if args.force:
            rebuild = True
            reason = "--force"
        elif not enriched_path.exists():
            rebuild = True
            reason = "missing"
        elif existing_name != master.name:
            rebuild = True
            reason = f"wrong master ({existing_name or '?'} -> {master.name})"
        else:
            rebuild = False
            reason = f"already built against {master.name}"

        print(f"  [{ws} -> {we}]  master={master.name}  {reason}")
        if not rebuild:
            ok += 1
            continue
        if args.dry_run:
            rebuilt += 1
            continue

        success = _run_categorizer(master, pulse,
                                   enriched_path, changelog_path,
                                   drug_only=args.drug_only)
        if success:
            rebuilt += 1
            print(f"              wrote {enriched_path.name}")
        else:
            failed += 1
            print(f"              FAILED")

    print()
    print("=" * 70)
    print(f"  Already-correct:  {ok}")
    print(f"  Rebuilt:          {rebuilt}{' (dry-run)' if args.dry_run else ''}")
    print(f"  Failed:           {failed}")
    print(f"  Skipped:          {skipped}")
    print("=" * 70)


if __name__ == "__main__":
    main()
