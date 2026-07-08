"""
pipelines/patch_adc_modality.py
Relabel ADC (Antibody-Drug Conjugate) trials with a new `adc` modality.

Scans trial text (title, interventions) for strong ADC signals
(payload-linker INN suffixes, known ADC drug names, explicit phrases)
and relabels matching trials in-place across all master DBs and snapshots.

Does NOT run the full reclassification pipeline.

Usage:
    python pipelines/patch_adc_modality.py --dry-run
    python pipelines/patch_adc_modality.py
    python pipelines/patch_adc_modality.py --export-ncts out.csv
"""

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Data dirs via core.paths so they resolve to the user's data folder in a frozen
# build (deriving from __file__ would point inside the read-only bundle).
from core.paths import snapshots_dir, changelogs_dir

SNAPSHOT_BASE = snapshots_dir()

# -- Strong ADC signals -------------------------------------------------------

_PAYLOAD_SUFFIXES = [
    "vedotin", "emtansine", "deruxtecan", "govitecan", "ozogamicin",
    "mertansine", "soravtansine", "tesirine", "ravtansine",
    "maytansinoid", "auristatin",
]

_PAYLOAD_ABBREVS = [r"\bmmae\b", r"\bmmaf\b", r"\bdxd\b"]

_EXPLICIT_PHRASES = [
    r"antibody[- ]?drug conjugate",
    r"immunoconjugate",
]

_ADC_NAMES = [
    "t-dm1", "tdm1", "kadcyla",
    "t-dxd", "enhertu",
    "adcetris", "polivy", "padcev", "trodelvy",
    "zynlonta", "elahere", "tivdak",
    "dato-dxd", "her3-dxd",
    "disitamab vedotin",
    "tusamitamab ravtansine",
    "telisotuzumab vedotin",
    "trastuzumab emtansine", "ado-trastuzumab",
    "trastuzumab deruxtecan",
    "brentuximab vedotin",
    "polatuzumab vedotin",
    "enfortumab vedotin",
    "sacituzumab govitecan",
    "loncastuximab tesirine",
    "mirvetuximab soravtansine",
    "tisotumab vedotin",
    "datopotamab deruxtecan",
    "patritumab deruxtecan",
]

_strong_parts = (
    [re.escape(s) for s in _PAYLOAD_SUFFIXES]
    + _PAYLOAD_ABBREVS
    + _EXPLICIT_PHRASES
    + [re.escape(n) for n in _ADC_NAMES]
)
STRONG_ADC_RE = re.compile("|".join(_strong_parts), re.IGNORECASE)

WEAK_ADC_RE = re.compile(r"\badc\b", re.IGNORECASE)
ADENOCARCINOMA_RE = re.compile(r"adenocarcinoma", re.IGNORECASE)
ANTIBODY_CONTEXT_RE = re.compile(
    r"\bantibody\b|\bmonoclonal\b|\w{3,}mab\b", re.IGNORECASE
)


def _build_text_blob(trial: dict) -> str:
    """Assemble searchable text from a trial dict."""
    parts = [trial.get("title") or ""]
    for iv_text in trial.get("interventions_text") or []:
        parts.append(iv_text)
    for iv in trial.get("interventions_all") or []:
        parts.append(iv.get("name") or "")
        parts.append(iv.get("description") or "")
    return " ".join(parts).lower()


def is_adc_trial(trial: dict) -> tuple[bool, str]:
    """
    Return (True, matched_signal) if the trial is a high-confidence ADC,
    or (False, "") otherwise.
    """
    if not trial.get("is_drug_trial"):
        return False, ""
    if trial.get("modality") == "adc":
        return False, ""  # already labeled, skip for idempotency

    blob = _build_text_blob(trial)

    # Strong signals
    m = STRONG_ADC_RE.search(blob)
    if m:
        return True, m.group()

    # Weak signal: bare "adc" with guards
    if WEAK_ADC_RE.search(blob):
        if not ADENOCARCINOMA_RE.search(blob) and ANTIBODY_CONTEXT_RE.search(blob):
            return True, "adc (weak)"

    return False, ""


def _find_snapshot_files() -> list[Path]:
    """Discover all trial-containing JSON files to patch."""
    files = []

    # Master DBs
    au_dir = SNAPSHOT_BASE / "active_universe"
    if au_dir.is_dir():
        files.extend(sorted(au_dir.glob("master_DB_*.json")))

    # Weekly snapshots in last_update
    lu_dir = SNAPSHOT_BASE / "last_update"
    if lu_dir.is_dir():
        files.extend(sorted(lu_dir.glob("*.json")))

    # Reclassified snapshots
    rc_dir = SNAPSHOT_BASE / "reclassified"
    if rc_dir.is_dir():
        files.extend(sorted(rc_dir.glob("reclassified_*.json")))

    # Enriched changelogs (used by weekly sci_wq1 / bd_wq1)
    cl_dir = changelogs_dir()
    if cl_dir.is_dir():
        files.extend(sorted(cl_dir.glob("enriched_*.json")))

    return files


def patch_file(path: Path, dry_run: bool, audit_rows: list | None) -> dict:
    """Patch a single snapshot file. Returns stats dict."""
    size_mb = path.stat().st_size / 1e6
    print("")
    print(f"  FILE: {path.name}  ({size_mb:.0f} MB)")
    t0 = time.time()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    trials = data.get("trials", [])
    relabeled = 0
    from_modality: Counter = Counter()

    for trial in trials:
        is_adc, signal = is_adc_trial(trial)
        if not is_adc:
            continue

        old_mod = trial.get("modality", "?")
        from_modality[old_mod] += 1
        relabeled += 1

        if audit_rows is not None:
            audit_rows.append({
                "nct_id": trial.get("nct_id", "?"),
                "old_modality": old_mod,
                "matched_signal": signal,
                "file": path.name,
            })

        if not dry_run:
            trial["modality"] = "adc"
            trial["modality_source"] = "patch_adc"
            flags = trial.get("info_flags") or []
            if "adc_reclassified" not in flags:
                flags.append("adc_reclassified")
            trial["info_flags"] = flags

    load_s = time.time() - t0

    if relabeled == 0:
        print(f"    No ADC trials found ({len(trials)} trials scanned in {load_s:.1f}s)")
        return {"relabeled": 0, "from_modality": {}}

    print(f"    Relabeled: {relabeled} trials (scanned {len(trials)} in {load_s:.1f}s)")
    for mod, cnt in from_modality.most_common():
        print(f"      {mod} -> adc:  {cnt}")

    if not dry_run:
        t1 = time.time()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        print(f"    Written in {time.time() - t1:.1f}s")

    return {"relabeled": relabeled, "from_modality": dict(from_modality)}


def main():
    parser = argparse.ArgumentParser(
        description="Relabel ADC trials with new adc modality"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print counts without writing changes"
    )
    parser.add_argument(
        "--export-ncts", type=str, default=None,
        help="Path to export CSV audit log (nct_id, old_modality, signal, file)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  ADC Modality Patch")
    print("  Mode:", "DRY RUN" if args.dry_run else "LIVE (will modify files)")
    print("=" * 60)

    files = _find_snapshot_files()
    if not files:
        print("")
        print("  No snapshot files found. Check SNAPSHOT_BASE:", SNAPSHOT_BASE)
        sys.exit(1)

    print("")
    print(f"  Found {len(files)} snapshot file(s) to scan")

    audit_rows: list = [] if args.export_ncts else None
    grand_total = 0
    grand_from: Counter = Counter()

    for path in files:
        stats = patch_file(path, args.dry_run, audit_rows)
        grand_total += stats["relabeled"]
        grand_from.update(stats["from_modality"])

    # -- Grand summary ---------------------------------------------------------
    print("")
    print("=" * 60)
    print(f"  TOTAL: {grand_total} trials relabeled across {len(files)} files")
    if grand_from:
        print("  By previous modality:")
        for mod, cnt in grand_from.most_common():
            print(f"    {mod:25s} -> adc:  {cnt}")
    if args.dry_run:
        print("")
        print("  (DRY RUN -- no files were modified)")
    print("=" * 60)

    # -- Export audit CSV ------------------------------------------------------
    if args.export_ncts and audit_rows:
        with open(args.export_ncts, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=["nct_id", "old_modality", "matched_signal", "file"]
            )
            writer.writeheader()
            writer.writerows(audit_rows)
        print("")
        print(f"  Audit CSV written: {args.export_ncts} ({len(audit_rows)} rows)")


if __name__ == "__main__":
    main()
