#!/usr/bin/env python3
"""
pipelines/generate_quarterly_viz.py
────────────────────────────────────
Interactive assembler for quarterly / strategic dashboard.

Separate from generate_weekly_viz.py (which handles weekly pulse data).
Reads the master DB and computes strategic questions that look at the
entire active universe rather than weekly deltas.

Run from the ALEXIS project root:
    python pipelines/generate_quarterly_viz.py

Question IDs and their analytics sources:
    bd_sq2  — top 25 sponsors          → master DB trials[]  (full scan + sidecar cache)
    mk_sq1  — modality landscape        → master DB dir  (full history + sidecar caches)
    sci_sq8 — biomarker × TA matrix    → master DB trials[]  (full scan + sidecar cache)
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── Path setup ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import snapshots_dir, viz_dir as _viz_dir

MASTER_DB_DIR = snapshots_dir() / "active_universe"

VIZ_DIR   = _viz_dir()
TEMPLATE  = VIZ_DIR / "alexis_weekly_dashboard.html"
OUTPUT    = VIZ_DIR / "alexis_quarterly_dashboard_live.html"

DATA_PLACEHOLDER      = "/* __ALEXIS_DATA_PLACEHOLDER__ */"
COMPONENT_PLACEHOLDER = "/* __COMPONENTS_PLACEHOLDER__ */"

# JSX component files — include ALL (weekly + quarterly) so both tabs work.
# The weekly set must be complete or WeeklyBD throws (it renders WQ2 too).
COMPONENT_FILES = [
    # Weekly components (so the weekly tab renders if user switches to it)
    VIZ_DIR / "bd_wq1.jsx",
    VIZ_DIR / "bd_wq2.jsx",
    VIZ_DIR / "mk_wq1.jsx",
    VIZ_DIR / "mk_wq2.jsx",
    VIZ_DIR / "sci_wq1.jsx",
    VIZ_DIR / "sci_wq2.jsx",
    VIZ_DIR / "ops_wq1.jsx",
    # Quarterly components
    VIZ_DIR / "bd_sq2.jsx",
    VIZ_DIR / "mk_sq1_sq.jsx",
    VIZ_DIR / "ops_sq1_sq.jsx",
    VIZ_DIR / "sci_sq3.jsx",
]


def _newest_master() -> tuple[Path, dict]:
    """Newest master_DB_*.json + light metadata (no full 1 GB load)."""
    cands = sorted(MASTER_DB_DIR.glob("master_DB*.json"), key=_sort_key, reverse=True)
    if not cands:
        raise FileNotFoundError(f"No master_DB*.json in {MASTER_DB_DIR}")
    return cands[0], {"filename": cands[0].name}


# ── Helpers ────────────────────────────────────────────────────────────────

def _sort_key(fpath: Path):
    """Extract sortable tuple from master DB filename."""
    m = re.search(r'(\d{4})_Q(\d)', fpath.name)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (0, 0)


def _prompt_choice(prompt: str, options: list, default: int = 0) -> int:
    """Print a numbered list and return the chosen index."""
    for i, label in enumerate(options):
        marker = " [default]" if i == default else ""
        print(f"    {i+1}. {label}{marker}")
    while True:
        raw = input(f"\n  {prompt} [1-{len(options)}, Enter={default+1}]: ").strip()
        if raw == "":
            return default
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return idx
        print(f"  Please enter a number between 1 and {len(options)}.")


# ── Interactive file selection ─────────────────────────────────────────────

def pick_master_db() -> tuple[Path, dict]:
    """
    Present master DB files, let user pick one.
    Returns (path, metadata_dict).

    Does NOT load the full trials array — that's deferred to each analytics
    function which manages its own sidecar cache.
    """
    print("\n  \u250c\u2500 MASTER DB SELECTION \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    print(f"  \u2502  Looking in : {MASTER_DB_DIR}")

    if not MASTER_DB_DIR.exists():
        print(f"  \u2502  Dir not found: {MASTER_DB_DIR}")
        print("  \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
        sys.exit(1)

    candidates = sorted(
        MASTER_DB_DIR.glob("master_DB*.json"),
        key=_sort_key, reverse=True,
    )
    if not candidates:
        print(f"  \u2502  No master_DB*.json files found")
        print("  \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
        sys.exit(1)

    print(f"  \u2502  Found {len(candidates)} master DB file(s):\n")

    labels = []
    for f in candidates:
        size_mb = f.stat().st_size / (1024 * 1024)
        labels.append(f"{f.name}  ({size_mb:.0f} MB)")

    idx = _prompt_choice("Pick a master DB", labels, default=0)
    chosen = candidates[idx]

    print(f"\n  \u2502  Selected  : {chosen.name}")
    print(f"  \u2502  Full path : {chosen}")

    # Load only metadata (fast — reads just the first few KB via streaming)
    try:
        with chosen.open("r", encoding="utf-8", errors="replace") as f:
            # Quick parse: load full JSON just for metadata + summary stats
            # The analytics functions handle their own full load + caching
            raw = json.load(f)
            meta = raw.get("metadata", {})
            summary = raw.get("summary", {})
            dtc = summary.get("drug_trial_counts", {})
            drug_total = dtc.get("drug_trials", 0)

        print(f"  \u2502  Drug trials : {drug_total:,}")
        print(f"  \u2502  Export date  : {meta.get('export_date')}")
    except Exception as e:
        print(f"  \u2502  WARNING: could not read metadata: {e}")
        meta = {}

    print("  \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    return chosen, meta


# ── Main ───────────────────────────────────────────────────────────────────


# ── Reusable payload builder (called by main() and generate_dashboard.py) ──

def build_quarterly_payload(db_path, meta) -> dict:
    """
    Import quarterly analytics modules, compute sq2/sq4/sq8/sq9/sq10, and return
    the quarterly portion of the ALEXIS_DATA payload.  Extracted so
    generate_dashboard.py can call it without duplicating the logic.
    """
    print("\n  Building per-question data ...")

    from analytics.bd_sq2 import sq2_top_sponsors
    sq2_data = sq2_top_sponsors(str(db_path))
    top_n = len(sq2_data.get("top_sponsors", []))
    total = sq2_data.get("meta", {}).get("total_industry_drug", 0)
    print(f"  bd_sq2  : {top_n} top sponsors, "
          f"{total:,} industry drug trials")

    from analytics.mk_sq1 import sq1_full_history
    sq4_data = sq1_full_history(str(MASTER_DB_DIR))
    sq4_mods = len(sq4_data.get("modalities", []))
    sq4_periods = len(sq4_data.get("periods", []))
    print(f"  mk_sq1  : {sq4_mods} modalities across {sq4_periods} periods")

    from analytics.ops_sq1 import sq10_workload_forecast
    sq10_data = sq10_workload_forecast(str(db_path))
    sq10_tiers = len([t for t in sq10_data.get("tiers", []) if t["volume"] > 0])
    sq10_total = sq10_data.get("grand_total_volume", 0)
    print(f"  ops_sq1 : {sq10_tiers} active tiers, "
          f"{sq10_total:,} drug trials scored")

    from analytics.sci_sq3 import sq9_confidence_dashboard
    sq9_data = sq9_confidence_dashboard(str(db_path))
    if sq9_data.get("available"):
        mc = sq9_data["modality_confidence"]
        tc = sq9_data["ta_confidence"]
        dc = sq9_data["data_coverage"]
        print(f"  sci_sq3 : mod {mc['score']}% ({mc['high_count']:,}H/{mc['medium_count']:,}M), "
              f"TA {tc['score']}% ({tc['high_count']:,}H/{tc['low_count']:,}L), "
              f"{dc['total_drug_trials']:,} drug trials, "
              f"MeSH coverage: mod {dc['modality_mesh_coverage_pct']}% / TA {dc['ta_mesh_coverage_pct']}%")
    else:
        print("  sci_sq3 : no data (no drug trials in master DB)")

    # sq8 (biomarker x TA) -- DISABLED: biomarker policy not fully implemented.
    # Re-enable once policy.biomarker_policy exports BIOMARKER_CATEGORIES and
    # classify_trial_biomarkers.
    # from analytics.sci_sq8 import sq8_biomarker_ta_matrix
    # sq8_data = sq8_biomarker_ta_matrix(str(db_path))
    # sq8_tagged = sq8_data.get("meta", {}).get("total_tagged", 0)
    # sq8_total = sq8_data.get("grand_total", 0)
    # print(f"  sci_sq8 : {sq8_tagged:,} biomarker-tagged trials, "
    #       f"{sq8_total:,} category x TA hits")
    sq8_data = {"available": False, "reason": "biomarker policy not fully implemented"}
    print("  sci_sq8 : disabled (biomarker policy not fully implemented)")

    # sq3 (BD / TA trajectory)
    from analytics.bd_sq3 import sq3_ta_trajectory
    sq3_data = sq3_ta_trajectory(str(MASTER_DB_DIR))
    if sq3_data.get("available"):
        print(f"  bd_sq3  : {len(sq3_data.get('tas', []))} top TAs over "
              f"{sq3_data.get('meta', {}).get('periods_loaded', 0)} periods")
    else:
        print(f"  bd_sq3  : no data ({sq3_data.get('reason')})")

    # sq12 (Ops / phase transition pipeline)
    from analytics.ops_sq12 import sq12_transition_pipeline
    sq12_data = sq12_transition_pipeline(str(db_path))
    if sq12_data.get("available"):
        n_flows = len(sq12_data.get("transitions", []))
        cov = sq12_data.get("meta", {}).get("completion_coverage_pct", 0)
        print(f"  ops_sq12: {n_flows} flows forecast, "
              f"{cov}% active trials have completion dates")

    return {
        "quarterly":       True,
        "metadata":        meta,
        "snapshot_file":   db_path.name,
        "sq2":             sq2_data,
        "sq3":             sq3_data,
        "sq4":             sq4_data,
        "sq8":             sq8_data,
        "sq9":             sq9_data,
        "sq10":            sq10_data,
        "sq12":            sq12_data,
    }

def main():
    print("\u2550" * 60)
    print("  ALEXIS Quarterly Viz Generator \u2014 Interactive Mode")
    print("\u2550" * 60)

    if not TEMPLATE.exists():
        print(f"\nERROR: Template not found at:\n  {TEMPLATE}")
        sys.exit(1)

    # ── 1. Pick master DB ──────────────────────────────────────────────────
    db_path, meta = pick_master_db()

    # ── 2. Build quarterly payload via extracted function ────────────────
    quarterly_data = build_quarterly_payload(db_path, meta)

    # Build full payload: quarterly data + weekly stubs
    payload = {
        "generated_at":    datetime.now().isoformat(),
        "is_reclassified": True,
        **quarterly_data,
        # Weekly keys -- set to empty so weekly tab renders gracefully
        "snap_summary":    {},
        "changelog":       {"available": False},
        "enriched_counts": {"available": False},
        "master_db_meta":  {"available": False},
        "prior_weeks_meta": [],
        "wq1": [], "wq2": None, "wq3": None,
        "wq4": [], "wq5": None, "wq6": None,
        "wq7": {"available": False}, "wq8": None, "wq9": None,
        "wq10": {"available": False}, "wq11": None, "wq12": None,
    }

    # ── 3. Load and concatenate JSX component files ────────────────────────
    missing = [f for f in COMPONENT_FILES if not f.exists()]
    if missing:
        print("\n  WARNING: missing JSX component files:")
        for f in missing:
            print(f"    {f}")

    components_js = "\n\n".join(
        f.read_text(encoding="utf-8")
        for f in COMPONENT_FILES
        if f.exists()
    )

    # ── 4. Inject into template and write live HTML ────────────────────────
    template  = TEMPLATE.read_text(encoding="utf-8")
    data_json = json.dumps(payload, separators=(",", ":"), default=str)

    html = template.replace(COMPONENT_PLACEHOLDER, components_js, 1)
    html = html.replace(DATA_PLACEHOLDER, data_json, 1)
    OUTPUT.write_text(html, encoding="utf-8")

    print("\n" + "\u2550" * 60)
    print(f"  Output : {OUTPUT}")
    print("\u2550" * 60)

    # ── Auto-open ──────────────────────────────────────────────────────────
    opened = False
    try:
        import platform
        system = platform.system()

        if system == "Linux" and "microsoft" in platform.uname().release.lower():
            win_path = subprocess.check_output(
                ["wslpath", "-w", str(OUTPUT)], text=True
            ).strip()
            subprocess.Popen(
                ["cmd.exe", "/c", "start", "", win_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print("  Browser: opening via cmd.exe (WSL)")
            opened = True

        elif system == "Darwin":
            subprocess.Popen(
                ["open", str(OUTPUT)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print("  Browser: opening via open (Mac)")
            opened = True

        elif system == "Linux":
            subprocess.Popen(
                ["xdg-open", str(OUTPUT)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print("  Browser: opening via xdg-open (Linux)")
            opened = True

    except Exception:
        pass

    if not opened:
        print(f"  Browser: could not auto-open. Open manually:")
        print(f"           {OUTPUT}")


if __name__ == "__main__":
    main()
