#!/usr/bin/env python3
"""
pipelines/generate_weekly_viz.py
─────────────────────────────────
Interactive assembler that:
  1. Prompts for snapshot, changelog, enriched, master DB, and prior weeks
  2. Calls each analytics/[team]_wq[n].py compute function
  3. Concatenates viz/[team]_wq[n].jsx component files into the HTML template
  4. Writes viz/alexis_weekly_dashboard_live.html

Run from the ALEXIS project root:
    python pipelines/generate_weekly_viz.py

When migrating to an app:
    Expose build_viz_data() as a JSON API endpoint.
    The React components just need that same structure via fetch().

Question IDs and their analytics sources:
    bd_wq1  — sponsor action table          → enriched trials[]
    bd_wq2  — client alert cards            → enriched trials[] + client list (stub)
    bd_wq3  — TA deviation bars             → summary{} + prior snapshots (stub)
    mk_wq1  — social stat cards             → summary{}
    mk_wq2  — modality over/under index     → summary{} + master DB (stub)
    mk_wq3  — conference prep snapshot      → trials[] + prior snapshots (stub)
    sci_wq1 — TA × modality bubble matrix   → enriched trials[] + prior weeks
    sci_wq2 — classification gap report     → trials[] (stub)
    sci_wq3 — MeSH quality waterfall        → summary{} (stub)
    ops_wq1 — velocity dashboard            → enriched trials[] + prior weeks
    ops_wq2 — complexity waffle chart       → summary{} (stub)
    ops_wq3 — Phase 1 intake list           → trials[] (stub)
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── Path setup ─────────────────────────────────────────────────────────────
# Add ALEXIS project root to sys.path so analytics.* imports resolve.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Data locations come from core.paths so the generator honours the user's
# configured data folder (data_root) and works in a frozen build. Viz assets
# (template + jsx components) are bundled, read-only (app_root).
from core.paths import snapshots_dir, changelogs_dir, viz_dir as _viz_dir

SNAPSHOT_DIRS = [
    snapshots_dir() / "reclassified",
    snapshots_dir() / "last_update",
]
CHANGELOG_DIR  = changelogs_dir()
MASTER_DB_DIR  = snapshots_dir() / "active_universe"

VIZ_DIR   = _viz_dir()
TEMPLATE  = VIZ_DIR / "alexis_weekly_dashboard.html"
OUTPUT    = VIZ_DIR / "alexis_weekly_dashboard_live.html"

DATA_PLACEHOLDER      = "/* __ALEXIS_DATA_PLACEHOLDER__ */"
COMPONENT_PLACEHOLDER = "/* __COMPONENTS_PLACEHOLDER__ */"

# JSX component files injected into the template in this order.
# Add new question files here as they are implemented.
# Must include every weekly component the template's section renderers
# reference, or the whole React tree throws (e.g. WeeklyBD renders both
# WQ1 and WQ2 -> bd_wq2 must be present). Mirrors the wq-subset that
# generate_dashboard.py injects for the unified build.
COMPONENT_FILES = [
    VIZ_DIR / "bd_wq1.jsx",
    VIZ_DIR / "bd_wq2.jsx",
    VIZ_DIR / "mk_wq1.jsx",
    VIZ_DIR / "mk_wq2.jsx",
    VIZ_DIR / "sci_wq1.jsx",
    VIZ_DIR / "sci_wq2.jsx",
    VIZ_DIR / "ops_wq1.jsx",
]

# Rare-modality threshold — informational, passed through to master_db_meta
RARE_MODALITY_PCT = 0.5


# ── Filename / sort helpers ─────────────────────────────────────────────────

def _sort_key(fpath: Path):
    """
    Extract a sortable (year, month, day) tuple from a filename.
    Used to sort files chronologically; default (0,0,0) for unrecognised.
    """
    name = fpath.stem.replace("reclassified_", "")
    months = dict(jan=1,feb=2,mar=3,apr=4,may=5,jun=6,
                  jul=7,aug=8,sep=9,oct=10,nov=11,dec=12)
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})_(\d{4})-(\d{2})-(\d{2})', name)
    if m:
        return (int(m.group(4)), int(m.group(5)), int(m.group(6)))
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', name)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r'(\d{4})_([a-z]{3})_w(\d+)', name, re.I)
    if m:
        return (int(m.group(1)), months.get(m.group(2).lower(), 0), int(m.group(3)))
    return (0, 0, 0)


def _is_reclassified(fpath: Path) -> bool:
    return "reclassified" in str(fpath)


def _extract_window_dates(filename: str) -> tuple[str, str] | tuple[None, None]:
    """Extract (win_start, win_end) from dated filenames."""
    m = re.search(r'(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})', filename)
    if m:
        return m.group(1), m.group(2)
    return None, None


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


# ── Silent file loaders (no user prompt) ───────────────────────────────────

def _load_enriched_silent(win_start: str, win_end: str) -> dict | None:
    """
    Find and load the enriched file for a given window without prompting.
    Returns {ta_mod, mod_totals, drug_new_total, phase_counts, source, filename}
    or None if not found.
    """
    if not CHANGELOG_DIR.exists():
        return None

    for fpath in sorted(CHANGELOG_DIR.glob("enriched_*.json"), key=_sort_key, reverse=True):
        f_start, f_end = _extract_window_dates(fpath.name)
        if f_start == win_start or f_end == win_end:
            try:
                data   = json.load(fpath.open(encoding="utf-8", errors="replace"))
                trials = data.get("trials", [])

                from collections import defaultdict
                # Split counts two ways:
                #   ta_mod / drug_new_total -- strictly "new" (active-only)
                #   ta_mod_reg / drug_registrations_total -- new + new_inactive
                #       (retrospective completions), i.e. ALL trials appearing
                #       for the first time relative to the master DB used.
                #   The registrations view is what MK_WQ2 baselines must use
                #   so weeks diffed against a near-current master DB (mostly
                #   producing new_inactive) remain comparable.
                ta_mod: dict        = defaultdict(lambda: defaultdict(int))
                ta_mod_reg: dict    = defaultdict(lambda: defaultdict(int))
                phase_counts: dict  = defaultdict(int)

                for t in trials:
                    if not t.get("is_drug_trial", True):
                        continue
                    utype = t.get("update_type")
                    if utype not in ("new", "new_inactive"):
                        continue
                    ta  = t.get("therapeutic_area") or "Unknown"
                    mod = t.get("modality")         or "Unknown"
                    ta_mod_reg[ta][mod] += 1
                    if utype == "new":
                        ta_mod[ta][mod] += 1
                        phase_counts[(t.get("phase") or "NA").upper()] += 1

                drug_new_total = sum(sum(m.values()) for m in ta_mod.values())
                drug_registrations_total = sum(sum(m.values())
                                               for m in ta_mod_reg.values())
                drug_inactive_total = drug_registrations_total - drug_new_total

                mod_totals: dict = defaultdict(int)
                for mods in ta_mod.values():
                    for mod, n in mods.items():
                        mod_totals[mod] += n

                return {
                    "ta_mod":                  {ta: dict(mods) for ta, mods in ta_mod.items()},
                    "ta_mod_registrations":    {ta: dict(mods) for ta, mods in ta_mod_reg.items()},
                    "mod_totals":              dict(mod_totals),
                    "drug_new_total":          drug_new_total,
                    "drug_inactive_total":     drug_inactive_total,
                    "drug_registrations_total": drug_registrations_total,
                    "phase_counts":            dict(phase_counts),
                    "source":                  "enriched",
                    "filename":                fpath.name,
                }
            except Exception:
                return None

    return None


def _load_changelog_counts_silent(win_start: str, win_end: str) -> dict:
    """
    Silently find the changelog for a given window and return high-level counts.
    Returns {} if not found or on error.
    """
    if not CHANGELOG_DIR.exists():
        return {}

    for fpath in sorted(CHANGELOG_DIR.glob("*.json"), key=_sort_key, reverse=True):
        if "enriched" in fpath.name:
            continue
        f_start, f_end = _extract_window_dates(fpath.name)
        if f_start == win_start or f_end == win_end:
            try:
                data = json.load(fpath.open(encoding="utf-8", errors="replace"))
                s    = data.get("summary", {})
                return {
                    "new_active_all":    s.get("new_active_registrations",       0),
                    "new_inactive":      s.get("new_inactive_updates",           0),
                    "existing_business": s.get("existing_with_business_changes", 0),
                    "existing_metadata": s.get("existing_metadata_only",         0),
                }
            except Exception:
                return {}
    return {}


# ── Interactive file selection ──────────────────────────────────────────────

def pick_snapshot() -> tuple[Path, bool]:
    """Present all snapshot JSONs sorted newest-first; return (path, is_reclassified)."""
    print("\n  ┌─ SNAPSHOT SELECTION ────────────────────────────────────────")

    all_files = []
    for d in SNAPSHOT_DIRS:
        if d.exists():
            all_files += list(d.glob("*.json"))
        else:
            print(f"  │  (dir not found: {d})")

    if not all_files:
        print("  └─ ERROR: no snapshot files found in any of:")
        for d in SNAPSHOT_DIRS:
            print(f"       {d}")
        sys.exit(1)

    all_files.sort(key=_sort_key, reverse=True)
    print(f"  │  Found {len(all_files)} snapshot(s):\n")

    labels = []
    for f in all_files:
        tag   = "RECLASSIFIED" if _is_reclassified(f) else "RAW"
        try:
            short = str(f.relative_to(ROOT))
        except ValueError:
            short = str(f)
        labels.append(f"{f.name}  [{tag}]  ({short})")

    idx    = _prompt_choice("Pick a snapshot", labels, default=0)
    chosen = all_files[idx]
    is_rec = _is_reclassified(chosen)

    print(f"\n  │  Selected  : {chosen.name}")
    print(f"  │  Full path : {chosen}")
    print(f"  │  Type      : {'RECLASSIFIED' if is_rec else 'RAW (TA/modality charts will be hidden)'}")
    print("  └─────────────────────────────────────────────────────────────")
    return chosen, is_rec


def pick_changelog(snap_meta: dict) -> dict | None:
    """Auto-match changelog by window dates; let user confirm or override."""
    print("\n  ┌─ CHANGELOG SELECTION ───────────────────────────────────────")
    win_start = snap_meta.get("window_start", "")
    win_end   = snap_meta.get("window_end", snap_meta.get("as_of", ""))
    print(f"  │  Snapshot window: {win_start} → {win_end}")

    if not CHANGELOG_DIR.exists():
        print(f"  │  Changelog dir not found: {CHANGELOG_DIR}")
        print("  └─────────────────────────────────────────────────────────────")
        return None

    candidates = sorted(CHANGELOG_DIR.glob("changelog_*.json"), key=_sort_key, reverse=True)
    if not candidates:
        print(f"  │  No changelog files found in {CHANGELOG_DIR}")
        print("  └─────────────────────────────────────────────────────────────")
        return None

    print(f"  │  Found {len(candidates)} changelog(s):\n")

    auto_idx    = None
    auto_reason = None
    labels      = []
    for i, fpath in enumerate(candidates):
        m = re.search(r'changelog_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})', fpath.name)
        if m:
            cl_start, cl_end = m.group(1), m.group(2)
            hit_start = cl_start == win_start
            hit_end   = cl_end   == win_end
            match_tag = ""
            if hit_start or hit_end:
                match_tag = "  ✓ DATE MATCH"
                if auto_idx is None:
                    auto_idx    = i
                    auto_reason = (
                        f"start matched ({cl_start} == {win_start})" if hit_start
                        else f"end matched ({cl_end} == {win_end})"
                    )
            labels.append(f"{fpath.name}  cl={cl_start}→{cl_end}{match_tag}")
        else:
            labels.append(f"{fpath.name}  (no date range in filename)")
            if auto_idx is None:
                auto_idx    = i
                auto_reason = "fallback — no date range in filename"

    if auto_idx is None:
        auto_idx    = 0
        auto_reason = "fallback — no date match found"

    labels.append("(none — skip changelog)")

    print(f"  │  Auto-match: {candidates[auto_idx].name}")
    print(f"  │  Reason    : {auto_reason}\n")

    idx = _prompt_choice("Pick a changelog (or skip)", labels, default=auto_idx)
    print("  └─────────────────────────────────────────────────────────────")

    if idx == len(candidates):
        print("  │  Changelog skipped.")
        return None

    chosen = candidates[idx]
    print(f"\n  │  Selected  : {chosen.name}")
    print(f"  │  Full path : {chosen}")

    try:
        return json.load(chosen.open())
    except Exception as e:
        print(f"  │  WARNING: could not load changelog: {e}")
        return None


def pick_enriched(snap_meta: dict) -> list:
    """Find and load the enriched changelog for this snapshot window."""
    print("\n  ┌─ ENRICHED FILE SELECTION ───────────────────────────────────")
    win_start = snap_meta.get("window_start", "")
    win_end   = snap_meta.get("window_end", snap_meta.get("as_of", ""))
    print(f"  │  Snapshot window : {win_start} → {win_end}")
    print(f"  │  Looking in      : {CHANGELOG_DIR}")

    if not CHANGELOG_DIR.exists():
        print("  │  Dir not found — skipping enriched file")
        print("  └─────────────────────────────────────────────────────────────")
        return []

    candidates = sorted(CHANGELOG_DIR.glob("enriched_*.json"), key=_sort_key, reverse=True)
    if not candidates:
        print("  │  No enriched_*.json files found")
        print("  └─────────────────────────────────────────────────────────────")
        return []

    print(f"  │  Found {len(candidates)} enriched file(s):\n")

    auto_idx    = None
    auto_reason = None
    labels      = []
    for i, fpath in enumerate(candidates):
        m = re.search(r'enriched_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})', fpath.name)
        if m:
            cl_start, cl_end = m.group(1), m.group(2)
            hit_start = cl_start == win_start
            hit_end   = cl_end   == win_end
            match_tag = ""
            if hit_start or hit_end:
                match_tag = "  ✓ DATE MATCH"
                if auto_idx is None:
                    auto_idx    = i
                    auto_reason = (
                        f"start matched ({cl_start} == {win_start})" if hit_start
                        else f"end matched ({cl_end} == {win_end})"
                    )
            labels.append(f"{fpath.name}  [{cl_start}→{cl_end}]{match_tag}")
        else:
            labels.append(f"{fpath.name}  (no date range in filename)")
            if auto_idx is None:
                auto_idx    = i
                auto_reason = "fallback — no date range in filename"

    if auto_idx is None:
        auto_idx    = 0
        auto_reason = "fallback — no date match found"

    labels.append("(none — skip enriched file)")

    print(f"  │  Auto-match : {candidates[auto_idx].name}")
    print(f"  │  Reason     : {auto_reason}\n")

    idx = _prompt_choice("Pick an enriched file (or skip)", labels, default=auto_idx)
    print("  └─────────────────────────────────────────────────────────────")

    if idx == len(candidates):
        print("  │  Enriched file skipped.")
        return []

    chosen = candidates[idx]
    print(f"\n  │  Selected  : {chosen.name}")
    print(f"  │  Full path : {chosen}")

    try:
        data   = json.load(chosen.open(encoding="utf-8", errors="replace"))
        trials = data.get("trials", [])
        em     = data.get("metadata", {})
        print(f"  │  Trials in enriched file : {len(trials):,}")
        print(f"  │  drug_only               : {em.get('drug_only')}")
        return trials
    except Exception as e:
        print(f"  │  WARNING: could not load enriched file: {e}")
        return []


def pick_master_db() -> tuple[dict, str]:
    """Find master_DB_*.json files and return (summary_dict, filename)."""
    print("\n  ┌─ MASTER DB SELECTION ───────────────────────────────────────")
    print(f"  │  Looking in : {MASTER_DB_DIR}")

    if not MASTER_DB_DIR.exists():
        print("  │  Dir not found — skipping master DB")
        print("  └─────────────────────────────────────────────────────────────")
        return {}, ""

    candidates = sorted(MASTER_DB_DIR.glob("master_DB*.json"), key=_sort_key, reverse=True)
    if not candidates:
        print(f"  │  No master_DB*.json files found in {MASTER_DB_DIR}")
        print("  └─────────────────────────────────────────────────────────────")
        return {}, ""

    print(f"  │  Found {len(candidates)} master DB file(s):\n")

    labels = [f.name for f in candidates]
    labels.append("(none — skip master DB)")

    idx = _prompt_choice("Pick a master DB", labels, default=0)
    print("  └─────────────────────────────────────────────────────────────")

    if idx == len(candidates):
        print("  │  Master DB skipped.")
        return {}, ""

    chosen = candidates[idx]
    print(f"\n  │  Selected  : {chosen.name}")
    print(f"  │  Full path : {chosen}")

    try:
        data        = json.load(chosen.open(encoding="utf-8", errors="replace"))
        summary     = data.get("summary", {})
        meta        = data.get("metadata", {})
        dtc         = summary.get("drug_trial_counts", {})
        drug_total  = dtc.get("drug_trials", 0)
        export_date = meta.get("export_date")
        print(f"  │  Drug trials in master DB : {drug_total:,}")
        print(f"  │  Export date              : {export_date}")
        return summary, chosen.name
    except Exception as e:
        print(f"  │  WARNING: could not load master DB: {e}")
        return {}, ""


def pick_prior_snapshots(current_path: Path, n: int = 3) -> list:
    """
    Find the N snapshots immediately preceding current_path, let the user
    confirm, and return a list of dicts (oldest first) with TA×mod counts.
    """
    print("\n  ┌─ PRIOR WEEKS SELECTION (rolling average) ───────────────────")

    all_files = []
    for d in SNAPSHOT_DIRS:
        if d.exists():
            all_files += list(d.glob("*.json"))

    all_files = [f for f in all_files if f.resolve() != current_path.resolve()]
    all_files.sort(key=_sort_key, reverse=True)

    if not all_files:
        print("  │  No prior snapshots found — heat will be disabled")
        print("  └─────────────────────────────────────────────────────────────")
        return []

    candidates = all_files[:max(n, 1)]
    print(f"  │  Found {len(all_files)} prior snapshot(s). Will use up to {n}:")
    print()
    print(f"  │  Enter to use all {len(candidates)}, or pick a number to use fewer:")
    print()

    labels = []
    for i, f in enumerate(candidates):
        ws, we = _extract_window_dates(f.name)
        enriched_avail = ""
        if ws or we:
            if _load_enriched_silent(ws, we):
                enriched_avail = "  [enriched ✓]"
            else:
                enriched_avail = "  [enriched ✗ — summary fallback]"
        tag = "RECLASSIFIED" if _is_reclassified(f) else "RAW"
        if i == 0:
            use_desc = f"use all {len(candidates)} weeks"
        else:
            use_desc = f"use only the {i+1} most recent week{'s' if i > 0 else ''}"
        labels.append(f"{f.name}  [{tag}]{enriched_avail}  → {use_desc}")

    labels.append("(none — skip prior weeks, disable heat comparison)")

    idx_skip = len(candidates)
    idx = _prompt_choice("Prior weeks to load", labels, default=0)
    print("  └─────────────────────────────────────────────────────────────")

    if idx == idx_skip:
        print("  Prior weeks: disabled.")
        return []

    chosen_files = candidates if idx == 0 else candidates[:idx + 1]
    print(f"\n  Loading {len(chosen_files)} prior week(s) ...")

    results = []
    for f in reversed(chosen_files):   # oldest first
        ws, we = _extract_window_dates(f.name)
        window_label = f"{ws} → {we}" if ws else f.stem

        enriched = _load_enriched_silent(ws, we) if (ws or we) else None

        if enriched:
            entry = enriched
            entry["window_label"] = window_label
            print(f"    {window_label}  "
                  f"({entry['drug_new_total']:,} active new + "
                  f"{entry.get('drug_inactive_total', 0):,} retrospective = "
                  f"{entry.get('drug_registrations_total', entry['drug_new_total']):,} "
                  f"registered) [enriched]")
        else:
            try:
                from collections import defaultdict as _dd
                raw     = json.load(f.open(encoding="utf-8", errors="replace"))
                summary = raw.get("summary", {})
                ta_mod  = summary.get("ta_modality_counts_true_drugs", {})
                dtc     = summary.get("drug_trial_counts", {})
                total   = dtc.get("drug_trials", 0)
                _mod_totals: dict = _dd(int)
                for _mods in ta_mod.values():
                    for _mod, _n in _mods.items():
                        _mod_totals[_mod] += _n
                entry = {
                    "ta_mod":         ta_mod,
                    "mod_totals":     dict(_mod_totals),
                    "drug_new_total": total,
                    "phase_counts":   {},
                    "source":         "snapshot_summary",
                    "filename":       f.name,
                    "window_label":   window_label,
                }
                print(f"    {window_label}  ({total:,} drug trials) [snapshot summary fallback]")
            except Exception as e:
                print(f"    WARNING: could not load {f.name}: {e}")
                continue

        # Derive ta_totals for convenience
        entry["ta_totals"] = {
            ta: sum(mods.values())
            for ta, mods in (entry.get("ta_mod") or {}).items()
        }

        # Merge changelog counts (new_active_all etc.) — silent, best-effort
        if ws or we:
            cl_counts = _load_changelog_counts_silent(ws, we)
            entry.update(cl_counts)

        results.append(entry)

    return results


# ── Changelog reshaper ──────────────────────────────────────────────────────

def extract_changelog(cl: dict | None) -> dict:
    """Reshape changelog JSON into the structure the dashboard needs."""
    if not cl:
        return {"available": False}
    cl_summary = cl.get("summary", {})
    return {
        "available":                      True,
        "generated_at":                   cl.get("generated_at"),
        "window":                         cl.get("window"),
        "total_trials":                   cl_summary.get("total_trials", 0),
        "new_active_registrations":       cl_summary.get("new_active_registrations", 0),
        "new_inactive_updates":           cl_summary.get("new_inactive_updates", 0),
        "existing_with_business_changes": cl_summary.get("existing_with_business_changes", 0),
        "existing_metadata_only":         cl_summary.get("existing_metadata_only", 0),
        "category_counts":                cl_summary.get("category_counts", {}),
    }



# ── Reusable payload builder (called by main() and generate_dashboard.py) ──

def build_weekly_payload(snap_path, is_rec, meta, trials, raw,
                         cl_data, enriched_trials, master_summary,
                         master_db_filename, prior_weeks) -> dict:
    """
    Import all analytics modules, compute wq1-wq12, and return the
    ALEXIS_DATA payload dict.  Extracted so generate_dashboard.py can
    call it without duplicating the logic.
    """
    print("\n  Building per-question data ...")

    snap_summary = raw.get("summary", {})

    enriched_counts = {
        "available": bool(enriched_trials),
        "total":     len(enriched_trials),
        "new":       sum(1 for t in enriched_trials if t.get("update_type") == "new"),
        "existing":  sum(1 for t in enriched_trials if t.get("update_type") == "existing"),
    }

    from analytics.bd_wq1  import wq1_sponsor_action_table
    from analytics.bd_wq2  import wq2_client_alert_cards
    from analytics.bd_wq3  import wq3_ta_deviation_bars
    from analytics.mk_wq1  import wq4_social_stat_cards
    from analytics.mk_wq2  import wq5_modality_index_chart
    from analytics.mk_wq3  import wq6_conference_snapshot
    from analytics.sci_wq1 import wq7_ta_modality_matrix
    from analytics.sci_wq2 import wq8_classification_gap_report
    from analytics.sci_wq3 import wq9_mesh_quality_waterfall
    from analytics.ops_wq1 import wq10_velocity_dashboard
    from analytics.ops_wq2 import wq11_complexity_waffle
    from analytics.ops_wq3 import wq12_phase1_intake_list

    bd_wq1_data = wq1_sponsor_action_table(enriched_trials)
    print(f"  bd_wq1  : {len(bd_wq1_data)} INDUSTRY sponsors with new trials this week")

    bd_wq2_data  = wq2_client_alert_cards(enriched_trials)
    bd_wq3_data  = wq3_ta_deviation_bars(snap_summary, prior_summaries=[])

    mk_wq1_data  = wq4_social_stat_cards(snap_summary, enriched_counts)
    print(f"  mk_wq1  : {len(mk_wq1_data)} stat cards")

    mk_wq2_data  = wq5_modality_index_chart(snap_summary,
                                            master_db_summary=master_summary,
                                            enriched_trials=enriched_trials,
                                            prior_weeks=prior_weeks)
    mk_wq3_data  = wq6_conference_snapshot(trials, ta_filter="", prior_summaries=[])

    sci_wq1_data = wq7_ta_modality_matrix(enriched_trials, master_summary, prior_weeks)
    if sci_wq1_data.get("available"):
        heat_info = (
            f"rolling avg ({sci_wq1_data['prior_weeks_used']} weeks)"
            if sci_wq1_data["heat_mode"] == "rolling_avg"
            else sci_wq1_data["heat_mode"]
        )
        print(f"  sci_wq1 : {len(sci_wq1_data['rows'])} TAs x "
              f"{len(sci_wq1_data['columns'])} modalities "
              f"({sci_wq1_data['grand_total']} new registrations) "
              f"[heat: {heat_info}]")
    else:
        print("  sci_wq1 : no data - enriched file empty or not loaded")

    sci_wq2_data = wq8_classification_gap_report(enriched_trials, snap_summary)
    sci_wq3_data = wq9_mesh_quality_waterfall(snap_summary)

    ops_wq1_data = wq10_velocity_dashboard(
        enriched_trials, meta, snap_summary, cl_data, prior_weeks)
    if ops_wq1_data.get("available"):
        pace = ops_wq1_data.get("pace_delta_pct")
        if pace is not None:
            print(f"  ops_wq1 : sparkline {len(ops_wq1_data['sparkline'])} pts, "
                  f"cur={ops_wq1_data['cur_drug_new']} drug new, "
                  f"pace {pace:+.1f}%")
        else:
            print(f"  ops_wq1 : {ops_wq1_data['cur_drug_new']} new drug trials (no prior avg)")
    else:
        print("  ops_wq1 : no data")

    ops_wq2_data = wq11_complexity_waffle(snap_summary)
    ops_wq3_data = wq12_phase1_intake_list(trials)

    return {
        "generated_at":    datetime.now().isoformat(),
        "snapshot_file":   snap_path.name,
        "is_reclassified": is_rec,
        "metadata":        meta,
        "snap_summary":    snap_summary,
        "changelog":       cl_data,
        "enriched_counts": enriched_counts,
        "master_db_meta":  {
            "available":   bool(master_summary),
            "drug_trials": (master_summary.get("drug_trial_counts") or {}).get("drug_trials", 0),
            "rare_pct":    RARE_MODALITY_PCT,
            "filename":    master_db_filename,
        },
        "prior_weeks_meta": [
            {
                "window_label":  pw["window_label"],
                "source":        pw["source"],
                "drug_new_total": pw["drug_new_total"],
            }
            for pw in prior_weeks
        ],
        "wq1":  bd_wq1_data,  "wq2":  bd_wq2_data,  "wq3":  bd_wq3_data,
        "wq4":  mk_wq1_data,  "wq5":  mk_wq2_data,  "wq6":  mk_wq3_data,
        "wq7":  sci_wq1_data, "wq8":  sci_wq2_data,  "wq9":  sci_wq3_data,
        "wq10": ops_wq1_data, "wq11": ops_wq2_data,  "wq12": ops_wq3_data,
    }

# ── Non-interactive auto-selection (for the desktop app / background jobs) ──
# Mirrors the pick_* helpers but never calls input(); always takes the newest
# matching file. ASCII-only prints so it is safe under a Windows subprocess
# pipe (no console). Used by `--auto` and by app/jobs.

def _latest_snapshot() -> tuple[Path | None, bool]:
    all_files: list[Path] = []
    for d in SNAPSHOT_DIRS:
        if d.exists():
            all_files += list(d.glob("*.json"))
    if not all_files:
        return None, False
    all_files.sort(key=_sort_key, reverse=True)
    chosen = all_files[0]
    return chosen, _is_reclassified(chosen)


def _auto_match_changelog(win_start: str, win_end: str) -> dict | None:
    if not CHANGELOG_DIR.exists():
        return None
    for fpath in sorted(CHANGELOG_DIR.glob("changelog_*.json"), key=_sort_key, reverse=True):
        m = re.search(r'changelog_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})', fpath.name)
        if m and (m.group(1) == win_start or m.group(2) == win_end):
            try:
                return json.load(fpath.open(encoding="utf-8", errors="replace"))
            except Exception:
                return None
    return None


def _auto_match_enriched(win_start: str, win_end: str) -> list:
    if not CHANGELOG_DIR.exists():
        return []
    for fpath in sorted(CHANGELOG_DIR.glob("enriched_*.json"), key=_sort_key, reverse=True):
        f_start, f_end = _extract_window_dates(fpath.name)
        if f_start == win_start or f_end == win_end:
            try:
                data = json.load(fpath.open(encoding="utf-8", errors="replace"))
                return data.get("trials", [])
            except Exception:
                return []
    return []


def _latest_master_db() -> tuple[dict, str]:
    if not MASTER_DB_DIR.exists():
        return {}, ""
    candidates = sorted(MASTER_DB_DIR.glob("master_DB*.json"), key=_sort_key, reverse=True)
    if not candidates:
        return {}, ""
    chosen = candidates[0]
    try:
        data = json.load(chosen.open(encoding="utf-8", errors="replace"))
        return data.get("summary", {}), chosen.name
    except Exception:
        return {}, chosen.name


def _auto_prior_snapshots(current_path: Path, n: int = 3) -> list:
    all_files: list[Path] = []
    for d in SNAPSHOT_DIRS:
        if d.exists():
            all_files += list(d.glob("*.json"))
    all_files = [f for f in all_files if f.resolve() != current_path.resolve()]
    all_files.sort(key=_sort_key, reverse=True)
    chosen_files = all_files[:max(n, 0)]

    results = []
    for f in reversed(chosen_files):  # oldest first
        ws, we = _extract_window_dates(f.name)
        window_label = f"{ws} -> {we}" if ws else f.stem
        enriched = _load_enriched_silent(ws, we) if (ws or we) else None

        if enriched:
            entry = enriched
            entry["window_label"] = window_label
        else:
            try:
                from collections import defaultdict as _dd
                raw     = json.load(f.open(encoding="utf-8", errors="replace"))
                summary = raw.get("summary", {})
                ta_mod  = summary.get("ta_modality_counts_true_drugs", {})
                dtc     = summary.get("drug_trial_counts", {})
                total   = dtc.get("drug_trials", 0)
                _mt: dict = _dd(int)
                for _mods in ta_mod.values():
                    for _mod, _n in _mods.items():
                        _mt[_mod] += _n
                entry = {
                    "ta_mod":         ta_mod,
                    "mod_totals":     dict(_mt),
                    "drug_new_total": total,
                    "phase_counts":   {},
                    "source":         "snapshot_summary",
                    "filename":       f.name,
                    "window_label":   window_label,
                }
            except Exception:
                continue

        entry["ta_totals"] = {
            ta: sum(mods.values())
            for ta, mods in (entry.get("ta_mod") or {}).items()
        }
        if ws or we:
            entry.update(_load_changelog_counts_silent(ws, we))
        results.append(entry)

    return results


def build_viz_data_auto() -> tuple[dict, Path]:
    """Non-interactive payload build: auto-select the newest inputs.

    Returns ``(payload, snapshot_path)``. Raises ``FileNotFoundError`` if no
    snapshot is available.
    """
    snap_path, is_rec = _latest_snapshot()
    if snap_path is None:
        raise FileNotFoundError(
            "No snapshot files found under: "
            + ", ".join(str(d) for d in SNAPSHOT_DIRS)
        )

    print(f"  [info] snapshot   : {snap_path.name}")
    with snap_path.open("r", encoding="utf-8", errors="replace") as f:
        raw = json.load(f)
    meta   = raw.get("metadata", {})
    trials = raw.get("trials", [])
    win_start = meta.get("window_start", "")
    win_end   = meta.get("window_end", meta.get("as_of", ""))

    cl_raw  = _auto_match_changelog(win_start, win_end)
    cl_data = extract_changelog(cl_raw)
    enriched_trials = _auto_match_enriched(win_start, win_end)
    master_summary, master_db_fn = _latest_master_db()
    prior_weeks = _auto_prior_snapshots(snap_path, n=3)

    print(f"  [info] changelog  : {'matched' if cl_raw else 'none'}")
    print(f"  [info] enriched   : {len(enriched_trials):,} trials")
    print(f"  [info] master DB  : {master_db_fn or 'none'}")
    print(f"  [info] prior weeks: {len(prior_weeks)}")

    payload = build_weekly_payload(
        snap_path, is_rec, meta, trials, raw,
        cl_data, enriched_trials, master_summary, master_db_fn,
        prior_weeks,
    )
    return payload, snap_path


def assemble_html(payload: dict,
                  output_path: Path | None = None,
                  component_files: list | None = None,
                  template_path: Path | None = None) -> Path:
    """Inject ``payload`` + JSX components into the template; write live HTML.

    Returns the output path. Shared by interactive ``main()`` and ``--auto``.
    """
    template_path   = Path(template_path) if template_path else TEMPLATE
    component_files = component_files if component_files is not None else COMPONENT_FILES
    output_path     = Path(output_path) if output_path else OUTPUT

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    missing = [f for f in component_files if not Path(f).exists()]
    for f in missing:
        print(f"  [warn] missing JSX component: {f}")

    components_js = "\n\n".join(
        Path(f).read_text(encoding="utf-8")
        for f in component_files
        if Path(f).exists()
    )
    template  = template_path.read_text(encoding="utf-8")
    data_json = json.dumps(payload, separators=(",", ":"), default=str)

    html = template.replace(COMPONENT_PLACEHOLDER, components_js, 1)
    html = html.replace(DATA_PLACEHOLDER, data_json, 1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def run_auto(no_open: bool = True) -> int:
    """Entry point for `--auto` and background jobs. Returns a process code."""
    print("[info] ALEXIS weekly viz - auto mode")
    if not TEMPLATE.exists():
        print(f"[err] Template not found at: {TEMPLATE}")
        return 1
    try:
        payload, _snap = build_viz_data_auto()
    except FileNotFoundError as e:
        print(f"[err] {e}")
        return 1
    out = assemble_html(payload)
    print(f"[ok] wrote {out}")
    if not no_open:
        _try_open(out)
    return 0


def _try_open(output_path: Path) -> None:
    """Best-effort open in the default browser (cross-platform)."""
    try:
        import platform
        system = platform.system()
        if system == "Linux" and "microsoft" in platform.uname().release.lower():
            win_path = subprocess.check_output(
                ["wslpath", "-w", str(output_path)], text=True
            ).strip()
            subprocess.Popen(["cmd.exe", "/c", "start", "", win_path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system == "Darwin":
            subprocess.Popen(["open", str(output_path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system == "Windows":
            import os
            os.startfile(str(output_path))  # type: ignore[attr-defined]
        elif system == "Linux":
            subprocess.Popen(["xdg-open", str(output_path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        print(f"  [info] open manually: {output_path}")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="ALEXIS weekly viz generator (interactive by default)."
    )
    ap.add_argument("--auto", action="store_true",
                    help="Non-interactive: auto-pick the newest inputs.")
    ap.add_argument("--no-open", action="store_true",
                    help="Do not auto-open the generated HTML in a browser.")
    args = ap.parse_args()

    if args.auto:
        raise SystemExit(run_auto(no_open=args.no_open))

    _interactive_main()


def _interactive_main():
    print("═" * 60)
    print("  ALEXIS Weekly Viz Generator — Interactive Mode")
    print("═" * 60)

    if not TEMPLATE.exists():
        print(f"\nERROR: Template not found at:\n  {TEMPLATE}")
        sys.exit(1)

    # ── 1. Interactive file selection ──────────────────────────────────────
    snap_path, is_rec = pick_snapshot()

    print(f"\n  Loading {snap_path.name} ...")
    with snap_path.open("r", encoding="utf-8", errors="replace") as f:
        raw = json.load(f)
    meta   = raw.get("metadata", {})
    trials = raw.get("trials",   [])
    print(f"  Trials loaded : {len(trials):,}")
    print(f"  run_id        : {meta.get('run_id')}")
    print(f"  as_of         : {meta.get('as_of')}")
    print(f"  window        : {meta.get('window_start')} → {meta.get('window_end')}")

    cl_raw          = pick_changelog(meta)
    cl_data         = extract_changelog(cl_raw)
    enriched_trials = pick_enriched(meta)
    master_summary, master_db_filename = pick_master_db()
    prior_weeks     = pick_prior_snapshots(snap_path, n=3)

    if enriched_trials:
        new_count      = sum(1 for t in enriched_trials if t.get("update_type") == "new")
        existing_count = sum(1 for t in enriched_trials if t.get("update_type") == "existing")
        print(f"  Enriched trials : {len(enriched_trials):,} total")
        print(f"    update_type=new      : {new_count:,}")
        print(f"    update_type=existing : {existing_count:,}")
    else:
        print("  Enriched file not loaded — bd_wq1 / sci_wq1 / ops_wq1 will return empty results")

    # ── 2. Build payload via extracted function ──────────────────────────
    payload = build_weekly_payload(
        snap_path, is_rec, meta, trials, raw,
        cl_data, enriched_trials, master_summary, master_db_filename,
        prior_weeks,
    )

    # ── 3-4. Assemble + write live HTML (shared with --auto) ───────────────
    out = assemble_html(payload)

    print("\n" + "=" * 60)
    print(f"  Output : {out}")
    print("=" * 60)

    _try_open(out)


if __name__ == "__main__":
    main()
