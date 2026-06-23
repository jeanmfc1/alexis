#!/usr/bin/env python3
"""
pipelines/generate_dashboard.py

Unified dashboard generator -- runs weekly + quarterly pipelines and
produces a single HTML with both tabs fully populated.

Usage:
    python pipelines/generate_dashboard.py               # both (default)
    python pipelines/generate_dashboard.py --weekly-only
    python pipelines/generate_dashboard.py --quarterly-only
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import snapshots_dir, viz_dir as _viz_dir

VIZ_DIR   = _viz_dir()
TEMPLATE  = VIZ_DIR / "alexis_weekly_dashboard.html"
OUTPUT    = VIZ_DIR / "alexis_dashboard_live.html"

DATA_PLACEHOLDER      = "/* __ALEXIS_DATA_PLACEHOLDER__ */"
COMPONENT_PLACEHOLDER = "/* __COMPONENTS_PLACEHOLDER__ */"

MASTER_DB_DIR = snapshots_dir() / "active_universe"

COMPONENT_FILES = [
    VIZ_DIR / "bd_wq1.jsx",
    VIZ_DIR / "bd_wq2.jsx",
    VIZ_DIR / "mk_wq1.jsx",
    VIZ_DIR / "mk_wq2.jsx",
    VIZ_DIR / "sci_wq1.jsx",
    VIZ_DIR / "sci_wq2.jsx",
    VIZ_DIR / "ops_wq1.jsx",
    VIZ_DIR / "bd_sq2.jsx",
    VIZ_DIR / "bd_sq3.jsx",
    VIZ_DIR / "mk_sq1_sq.jsx",
    VIZ_DIR / "ops_sq1_sq.jsx",
    VIZ_DIR / "ops_sq12.jsx",
    VIZ_DIR / "sci_sq3.jsx",
    VIZ_DIR / "sci_sq8.jsx",
    # ChiCTR (weekly cadence, cw prefix)
    VIZ_DIR / "bd_cw1.jsx",
    VIZ_DIR / "mk_cw1.jsx",
    VIZ_DIR / "sci_cw1.jsx",
    VIZ_DIR / "ops_cw1.jsx",
    # ANZCTR (monthly cadence, aw prefix)
    VIZ_DIR / "bd_aw1.jsx",
    VIZ_DIR / "mk_aw1.jsx",
    VIZ_DIR / "sci_aw1.jsx",
    VIZ_DIR / "ops_aw1.jsx",
]


def _pick_shared_master_db():
    """Pick master DB once, return (path, metadata, summary)."""
    from pipelines.generate_quarterly_viz import pick_master_db as _pick_q
    db_path, meta = _pick_q()
    try:
        with db_path.open("r", encoding="utf-8", errors="replace") as f:
            raw = json.load(f)
        summary = raw.get("summary", {})
    except Exception:
        summary = {}
    return db_path, meta, summary


def _auto_open(output_path):
    """Try to open the output HTML in the default browser."""
    opened = False
    try:
        import platform
        system = platform.system()
        if system == "Linux" and "microsoft" in platform.uname().release.lower():
            win_path = subprocess.check_output(
                ["wslpath", "-w", str(output_path)], text=True
            ).strip()
            subprocess.Popen(
                ["cmd.exe", "/c", "start", "", win_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            opened = True
        elif system == "Darwin":
            subprocess.Popen(["open", str(output_path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            opened = True
        elif system == "Linux":
            subprocess.Popen(["xdg-open", str(output_path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            opened = True
    except Exception:
        pass
    if not opened:
        print(f"  Browser: could not auto-open. Open manually:\n           {output_path}")


def _run_auto(run_weekly=True, run_quarterly=True, run_chictr=True,
              run_anzctr=True, no_open=True) -> int:
    """Non-interactive full-dashboard build: auto-pick newest inputs per tab.

    Each source is best-effort -- a missing/failed source degrades to an
    'unavailable' stub so the rest of the dashboard still renders.
    """
    print("[info] ALEXIS unified dashboard - auto mode")
    if not TEMPLATE.exists():
        print(f"[err] template not found: {TEMPLATE}")
        return 1

    payload: dict = {
        "generated_at": datetime.now().isoformat(),
        "is_reclassified": True,
    }

    # -- Weekly --
    if run_weekly:
        try:
            from pipelines.generate_weekly_viz import build_viz_data_auto
            wk, _snap = build_viz_data_auto()
            payload.update(wk)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] weekly payload failed: {e}")
            run_weekly = False
    if not run_weekly:
        payload.update({
            "snap_summary": {}, "changelog": {"available": False},
            "enriched_counts": {"available": False},
            "master_db_meta": {"available": False}, "prior_weeks_meta": [],
            "wq1": [], "wq2": None, "wq3": None, "wq4": [], "wq5": None, "wq6": None,
            "wq7": {"available": False}, "wq8": None, "wq9": None,
            "wq10": {"available": False}, "wq11": None, "wq12": None,
        })

    # -- Quarterly --
    if run_quarterly:
        try:
            from pipelines.generate_quarterly_viz import build_quarterly_payload, _newest_master
            db_path, meta = _newest_master()
            payload.update(build_quarterly_payload(db_path, meta))
        except Exception as e:  # noqa: BLE001
            print(f"[warn] quarterly payload failed: {e}")
            run_quarterly = False
    if not run_quarterly:
        payload.update({"quarterly": False, "sq2": {"available": False},
                        "sq4": {"available": False}, "sq9": {"available": False},
                        "sq8": {"available": False}, "sq10": {"available": False}})

    # -- ChiCTR --
    if run_chictr:
        try:
            from pipelines.generate_chictr_viz import build_chictr_payload
            payload.update(build_chictr_payload())
        except Exception as e:  # noqa: BLE001
            print(f"[warn] ChiCTR payload failed: {e}")
            run_chictr = False
    if not run_chictr:
        payload.update({"cw1": {"available": False}, "cw2": {"available": False},
                        "cw3": {"available": False}, "cw4": {"available": False},
                        "chictr_metadata": {"available": False}})

    # -- ANZCTR --
    if run_anzctr:
        try:
            from pipelines.generate_anzctr_viz import build_anzctr_payload
            payload.update(build_anzctr_payload())
        except Exception as e:  # noqa: BLE001
            print(f"[warn] ANZCTR payload failed: {e}")
            run_anzctr = False
    if not run_anzctr:
        payload.update({"aw1": {"available": False}, "aw2": {"available": False},
                        "aw3": {"available": False}, "aw4": {"available": False},
                        "anzctr_metadata": {"available": False}})

    # -- Assemble (reuse the weekly generator's assembler) --
    from pipelines.generate_weekly_viz import assemble_html
    out = assemble_html(payload, output_path=OUTPUT,
                        component_files=COMPONENT_FILES, template_path=TEMPLATE)
    print(f"[ok] wrote {out}")
    if not no_open:
        _auto_open(out)
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Unified ALEXIS dashboard generator (weekly + quarterly)."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--weekly-only", action="store_true",
                       help="Generate only the weekly (tactical) data")
    group.add_argument("--quarterly-only", action="store_true",
                       help="Generate only the quarterly (strategic) data")
    group.add_argument("--chictr-only", action="store_true",
                       help="Generate only the ChiCTR data")
    group.add_argument("--anzctr-only", action="store_true",
                       help="Generate only the ANZCTR data")
    parser.add_argument("--no-chictr", action="store_true",
                        help="Skip the ChiCTR pipeline (AACT only)")
    parser.add_argument("--no-anzctr", action="store_true",
                        help="Skip the ANZCTR pipeline")
    parser.add_argument("--auto", action="store_true",
                        help="Non-interactive: auto-pick newest inputs for every tab.")
    parser.add_argument("--no-open", action="store_true",
                        help="Do not open the result in a browser.")
    args = parser.parse_args()

    if args.auto:
        raise SystemExit(_run_auto(
            run_weekly=not args.quarterly_only and not args.chictr_only and not args.anzctr_only,
            run_quarterly=not args.weekly_only and not args.chictr_only and not args.anzctr_only,
            run_chictr=not args.no_chictr and not args.weekly_only and not args.quarterly_only and not args.anzctr_only,
            run_anzctr=not args.no_anzctr and not args.weekly_only and not args.quarterly_only and not args.chictr_only,
            no_open=args.no_open,
        ))

    run_weekly    = not args.quarterly_only and not args.chictr_only and not args.anzctr_only
    run_quarterly = not args.weekly_only    and not args.chictr_only and not args.anzctr_only
    run_chictr    = not args.no_chictr and not args.weekly_only and not args.quarterly_only and not args.anzctr_only
    run_anzctr    = not args.no_anzctr and not args.weekly_only and not args.quarterly_only and not args.chictr_only

    print("=" * 60)
    parts = []
    if run_weekly:    parts.append("Weekly")
    if run_quarterly: parts.append("Quarterly")
    if run_chictr:    parts.append("ChiCTR")
    if run_anzctr:    parts.append("ANZCTR")
    mode = " + ".join(parts) if parts else "(nothing selected)"
    print(f"  ALEXIS Dashboard Generator -- {mode}")
    print("=" * 60)

    if not TEMPLATE.exists():
        print(f"\nERROR: Template not found at:\n  {TEMPLATE}")
        sys.exit(1)

    payload = {}

    # -- Shared master DB selection (when running both) -----------------------
    db_path = None
    db_meta = None
    master_summary = {}
    master_db_fn = ""

    if run_weekly and run_quarterly:
        print("\n  Selecting master DB (shared by weekly + quarterly) ...")
        db_path, db_meta, master_summary = _pick_shared_master_db()
        master_db_fn = db_path.name
    elif run_quarterly:
        from pipelines.generate_quarterly_viz import pick_master_db as _pick_q
        db_path, db_meta = _pick_q()

    # -- Weekly pipeline ------------------------------------------------------
    if run_weekly:
        from pipelines.generate_weekly_viz import (
            pick_snapshot, pick_changelog, extract_changelog,
            pick_enriched, pick_master_db, pick_prior_snapshots,
            build_weekly_payload,
        )

        snap_path, is_rec = pick_snapshot()

        print(f"\n  Loading {snap_path.name} ...")
        with snap_path.open("r", encoding="utf-8", errors="replace") as f:
            raw = json.load(f)
        meta   = raw.get("metadata", {})
        trials = raw.get("trials",   [])
        print(f"  Trials loaded : {len(trials):,}")
        print(f"  run_id        : {meta.get('run_id')}")
        print(f"  window        : {meta.get('window_start')} -> {meta.get('window_end')}")

        cl_raw          = pick_changelog(meta)
        cl_data         = extract_changelog(cl_raw)
        enriched_trials = pick_enriched(meta)

        if not master_summary:
            master_summary, master_db_fn = pick_master_db()

        prior_weeks = pick_prior_snapshots(snap_path, n=3)

        if enriched_trials:
            new_count      = sum(1 for t in enriched_trials if t.get("update_type") == "new")
            existing_count = sum(1 for t in enriched_trials if t.get("update_type") == "existing")
            print(f"  Enriched trials : {len(enriched_trials):,} total")
            print(f"    update_type=new      : {new_count:,}")
            print(f"    update_type=existing : {existing_count:,}")
        else:
            print("  Enriched file not loaded")

        weekly_payload = build_weekly_payload(
            snap_path, is_rec, meta, trials, raw,
            cl_data, enriched_trials, master_summary, master_db_fn,
            prior_weeks,
        )
        payload.update(weekly_payload)
    else:
        payload.update({
            "generated_at":    datetime.now().isoformat(),
            "is_reclassified": True,
            "metadata":        {},
            "snap_summary":    {},
            "changelog":       {"available": False},
            "enriched_counts": {"available": False},
            "master_db_meta":  {"available": False},
            "prior_weeks_meta": [],
            "wq1": [], "wq2": None, "wq3": None,
            "wq4": [], "wq5": None, "wq6": None,
            "wq7": {"available": False}, "wq8": None, "wq9": None,
            "wq10": {"available": False}, "wq11": None, "wq12": None,
        })

    # -- Quarterly pipeline ---------------------------------------------------
    if run_quarterly:
        from pipelines.generate_quarterly_viz import build_quarterly_payload

        quarterly_data = build_quarterly_payload(db_path, db_meta)
        payload.update(quarterly_data)
    else:
        payload.update({
            "quarterly": False,
            "sq2":  {"available": False},
            "sq4":  {"available": False},
            "sq9":  {"available": False},
            "sq8":  {"available": False},
            "sq10": {"available": False},
        })

    # -- ChiCTR pipeline ------------------------------------------------------
    if run_chictr:
        print()
        print("  Building ChiCTR payload ...")
        from pipelines.generate_chictr_viz import build_chictr_payload
        try:
            chictr_payload = build_chictr_payload()
            payload.update(chictr_payload)
        except Exception as e:
            print(f"  WARNING: ChiCTR payload failed: {e}")
            payload.update({
                "cw1": {"available": False, "reason": str(e)},
                "cw2": {"available": False, "reason": str(e)},
                "cw3": {"available": False, "reason": str(e)},
                "cw4": {"available": False, "reason": str(e)},
                "chictr_metadata": {"available": False, "error": str(e)},
            })
    else:
        payload.update({
            "cw1": {"available": False},
            "cw2": {"available": False},
            "cw3": {"available": False},
            "cw4": {"available": False},
            "chictr_metadata": {"available": False},
        })

    # -- ANZCTR pipeline ------------------------------------------------------
    if run_anzctr:
        print()
        print("  Building ANZCTR payload ...")
        from pipelines.generate_anzctr_viz import build_anzctr_payload
        try:
            anzctr_payload = build_anzctr_payload()
            payload.update(anzctr_payload)
        except Exception as e:
            print(f"  WARNING: ANZCTR payload failed: {e}")
            payload.update({
                "aw1": {"available": False, "reason": str(e)},
                "aw2": {"available": False, "reason": str(e)},
                "aw3": {"available": False, "reason": str(e)},
                "aw4": {"available": False, "reason": str(e)},
                "anzctr_metadata": {"available": False, "error": str(e)},
            })
    else:
        payload.update({
            "aw1": {"available": False},
            "aw2": {"available": False},
            "aw3": {"available": False},
            "aw4": {"available": False},
            "anzctr_metadata": {"available": False},
        })

    # -- Load and concatenate JSX component files -----------------------------
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

    # -- Inject into template and write live HTML -----------------------------
    template  = TEMPLATE.read_text(encoding="utf-8")
    data_json = json.dumps(payload, separators=(",", ":"), default=str)

    html = template.replace(COMPONENT_PLACEHOLDER, components_js, 1)
    html = html.replace(DATA_PLACEHOLDER, data_json, 1)
    OUTPUT.write_text(html, encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"  Output : {OUTPUT}")
    print("=" * 60)

    _auto_open(OUTPUT)


if __name__ == "__main__":
    main()
