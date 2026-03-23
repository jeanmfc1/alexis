#!/usr/bin/env python3
"""
generate_weekly_viz.py
──────────────────────
Interactively prompts you to pick a snapshot and changelog, then
extracts exactly the data each dashboard question needs and injects
everything into alexis_weekly_dashboard.html → standalone HTML.

Run from the ALEXIS project root:
    python analytics/generate_weekly_viz.py

When migrating to an app:
    Expose build_viz_data() as a JSON API endpoint.
    The React components just need that same structure via fetch().

Data functions are named by question ID (wq1, wq2, ...) so you can
trace exactly which function feeds which card in the dashboard spec.

Weekly questions and their data sources:
    wq1  — sponsor action table          → trials[]  (individual records)
    wq2  — client alert cards            → trials[]  + manual client list
    wq3  — TA deviation bars             → summary{} + prior snapshots (rolling avg)
    wq4  — social stat cards             → summary{}
    wq5  — modality over/under index     → summary{} + master DB
    wq6  — conference prep snapshot      → trials[]  + prior snapshots
    wq7  — new signal feed               → trials[]  (individual records)
    wq8  — classification gap report     → trials[]  (individual records)
    wq9  — MeSH quality waterfall        → summary{}
    wq10 — velocity dashboard            → metadata  + prior snapshots
    wq11 — complexity waffle chart       → summary{} + manual weights
    wq12 — Phase 1 intake list           → trials[]  (individual records)
"""

import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT          = Path(__file__).parent.parent
SNAPSHOT_DIRS = [
    ROOT / "storage" / "snapshots" / "clinical_trials_v2" / "reclassified",
    ROOT / "storage" / "snapshots" / "clinical_trials_v2" / "last_update",
]
CHANGELOG_DIR  = ROOT / "storage" / "changelogs"
MASTER_DB_DIR  = ROOT / "storage" / "snapshots" / "clinical_trials_v2" / "active_universe"
TEMPLATE       = Path(__file__).parent / "alexis_weekly_dashboard.html"
OUTPUT         = Path(__file__).parent / "alexis_weekly_dashboard_live.html"
PLACEHOLDER    = "/* __ALEXIS_DATA_PLACEHOLDER__ */"

# Rare-modality threshold for wq7: modalities below this % of master DB
# total drug trials are flagged as novel signals
RARE_MODALITY_PCT = 0.5


# ── Helpers ───────────────────────────────────────────────────────────────

def _sort_key(fpath: Path):
    """
    Extract a sortable (year, month, day-or-week) tuple from a filename.
    Used to sort files chronologically in the selection list.

    Handles:
      reclassified_2026-02-20_2026-02-27_v1.json  → (2026, 02, 27)  uses end date
      2026-02-20_2026-02-27_v1.json               → (2026, 02, 27)  uses end date
      2026-02-20.json                              → (2026, 02, 20)
      2026_feb_w4.json                             → (2026,  2,  4)
    Unrecognised → (0, 0, 0)
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


def humanMod(s: str | None) -> str:
    """'small_molecule' → 'Small Molecule'  (mirrors the JS helper)"""
    return (s or "Unknown").replace("_", " ").title()


def _prompt_choice(prompt: str, options: list, default: int = 0) -> int:
    """
    Print a numbered list and return the chosen index.
    Pressing Enter selects the default (shown in brackets).
    """
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


# ── Interactive file selection ────────────────────────────────────────────

def pick_snapshot() -> tuple[Path, bool]:
    """
    Collect all snapshot JSONs across all known dirs, present them to the
    user sorted newest-first, and return (chosen_path, is_reclassified).
    """
    print("\n  ┌─ SNAPSHOT SELECTION ────────────────────────────────────────")

    all_files = []
    for d in SNAPSHOT_DIRS:
        if d.exists():
            for f in d.glob("*.json"):
                all_files.append(f)
        else:
            print(f"  │  (dir not found: {d})")

    if not all_files:
        print("  └─ ERROR: no snapshot files found in any of:")
        for d in SNAPSHOT_DIRS:
            print(f"       {d}")
        sys.exit(1)

    # Sort newest first so default=0 picks the most recent
    all_files.sort(key=_sort_key, reverse=True)

    print(f"  │  Found {len(all_files)} snapshot(s):\n")
    labels = []
    for f in all_files:
        tag   = "RECLASSIFIED" if _is_reclassified(f) else "RAW"
        short = str(f.relative_to(ROOT))
        labels.append(f"{f.name}  [{tag}]  ({short})")

    idx = _prompt_choice("Pick a snapshot", labels, default=0)
    chosen = all_files[idx]
    is_rec = _is_reclassified(chosen)

    print(f"\n  │  Selected  : {chosen.name}")
    print(f"  │  Full path : {chosen}")
    print(f"  │  Type      : {'RECLASSIFIED' if is_rec else 'RAW (TA/modality charts will be hidden)'}")
    print("  └─────────────────────────────────────────────────────────────")
    return chosen, is_rec


def pick_changelog(snap_meta: dict) -> dict | None:
    """
    Collect all changelog JSONs, highlight which one matches the snapshot
    window by date, and let the user confirm or choose a different one.
    Returns the loaded changelog dict, or None if skipped.
    """
    print("\n  ┌─ CHANGELOG SELECTION ───────────────────────────────────────")
    print(f"  │  Snapshot window: {snap_meta.get('window_start')} → {snap_meta.get('window_end') or snap_meta.get('as_of')}")
    print(f"  │  Matching rule  : filename dates vs snapshot window_start / window_end")
    print(f"  │  No database    : pure JSON file matching")

    win_start = snap_meta.get("window_start", "")
    win_end   = snap_meta.get("window_end", snap_meta.get("as_of", ""))

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

    # Work out the auto-match so we can set it as default and explain it
    auto_idx   = None
    auto_reason = None
    labels     = []
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
                    auto_idx = i
                    auto_reason = (
                        f"start matched ({cl_start} == {win_start})" if hit_start
                        else f"end matched ({cl_end} == {win_end})"
                    )
            labels.append(f"{fpath.name}  cl={cl_start}→{cl_end}{match_tag}")
        else:
            labels.append(f"{fpath.name}  (no date range in filename)")
            if auto_idx is None:
                auto_idx = i
                auto_reason = "fallback — no date range in filename"

    if auto_idx is None:
        auto_idx = 0
        auto_reason = "fallback — no date match found"

    labels.append("(none — skip changelog)")

    print(f"  │  Auto-match: {candidates[auto_idx].name}")
    print(f"  │  Reason    : {auto_reason}\n")

    idx = _prompt_choice("Pick a changelog (or skip)", labels, default=auto_idx)

    print("  └─────────────────────────────────────────────────────────────")

    # User picked "none"
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


# ─────────────────────────────────────────────────────────────────────────
# Weekly question data functions
#
# Each function is named after the question ID it serves.
# Each function receives either:
#   - trials   : list of trial dicts loaded from snapshot["trials"]
#   - summary  : dict loaded directly from snapshot["summary"]
#   - changelog: dict loaded from the changelog JSON
# and returns a dict that maps 1-to-1 to what the dashboard card renders.
# ─────────────────────────────────────────────────────────────────────────


# Complexity weights used by wq1 (priority score) and wq11 (waffle chart).
# Keys are lowercased substrings — matched with `in modality.lower()`.
# Order matters: more specific strings must come before broader ones.
# These are the manual weights described in the spec:
#   cell/gene therapy = 3×, radiopharmaceutical/oligonucleotide = 2.5×,
#   mAb/biologic = 2×, vaccine = 1.5×, small molecule = 1×
MODALITY_COMPLEXITY = [
    ("gene",   3.0),
    ("cell",   3.0),
    ("radio",  2.5),
    ("oligo",  2.5),
    ("mab",    2.0),
    ("biolog", 2.0),
    ("vaccin", 1.5),
]
MODALITY_COMPLEXITY_DEFAULT = 1.0   # small molecule and anything unrecognised

# Phase weights for priority scoring: earlier phase = higher urgency
# (Phase 1 sponsor is actively placing bioanalytical contracts right now)
PHASE_PRIORITY = {
    "PHASE1": 4,
    "PHASE2": 3,
    "PHASE3": 2,
    "PHASE4": 1,
}
PHASE_PRIORITY_DEFAULT = 0   # unknown / N/A


def _modality_weight(modality: str | None) -> float:
    """
    Return the complexity weight for a modality string.
    Matched case-insensitively against MODALITY_COMPLEXITY substrings.
    Returns MODALITY_COMPLEXITY_DEFAULT (1.0) if nothing matches.
    """
    if not modality:
        return MODALITY_COMPLEXITY_DEFAULT
    m = modality.lower()
    for substring, weight in MODALITY_COMPLEXITY:
        if substring in m:
            return weight
    return MODALITY_COMPLEXITY_DEFAULT


def _phase_weight(phase: str | None) -> int:
    """
    Return the urgency weight for a phase string.
    Normalises common variants ("Phase 1", "PHASE1", "phase_1") to the
    canonical key used in PHASE_PRIORITY.
    Returns PHASE_PRIORITY_DEFAULT (0) if nothing matches.
    """
    if not phase:
        return PHASE_PRIORITY_DEFAULT
    # Normalise: keep only digits and letters, uppercase
    key = re.sub(r"[^A-Z0-9]", "", phase.upper())
    # "PHASE1" → matches directly; "1" → prefix with PHASE
    if key.startswith("PHASE"):
        return PHASE_PRIORITY.get(key, PHASE_PRIORITY_DEFAULT)
    return PHASE_PRIORITY.get("PHASE" + key, PHASE_PRIORITY_DEFAULT)


def wq1_sponsor_action_table(enriched_trials: list) -> list:
    """
    BD / wq1 — "Which sponsors filed new trials this week that we should contact?"

    Source: enriched file trials[]
    Why enriched, not snapshot: the snapshot contains ALL trials updated that
    week (new registrations + existing trial updates). Only the enriched file
    has the update_type field ("new" | "existing") that lets us isolate actual
    new registrations.

    Filter:
        update_type   == "new"      — new registration only, not an update
        sponsor_class == "INDUSTRY" — BD cares about industry-sponsored trials
        is_drug_trial == True       — enriched file is drug_only but kept as guard

    Returns a list of sponsor dicts, sorted by priority_score descending.
    Each entry is one row in the Action Table.

    Fields returned per sponsor:
        sponsor_name    str   — display name
        new_trial_count int   — how many new drug trials they filed this week
        modalities      list  — unique modality labels, ordered by frequency
        top_phase       str   — the phase that appears most in their trials
        priority_score  float — sum of (modality_weight × phase_weight) across
                                all their new trials; higher = call today
        priority_label  str   — "HIGH" / "MED" / "LOW" derived from score
        trials          list  — individual trial records for the expandable row:
                                [{nct_id, title, modality, phase}]

    Priority label thresholds (score is sum across all the sponsor's new trials;
    a sponsor with 3 gene-therapy Phase-1 trials scores 3 × 3.0 × 4 = 36):
        HIGH  score >= 12
        MED   score >= 4
        LOW   score <  4
    """
    # 1. Filter: new registrations, INDUSTRY, drug trials only
    industry_drug = [
        t for t in enriched_trials
        if t.get("update_type") == "new"
        and (t.get("sponsor_class") or "").upper() == "INDUSTRY"
        and t.get("is_drug_trial", True)   # enriched is drug_only, guard only
    ]

    # 2. Group by sponsor_name
    by_sponsor: dict[str, list] = defaultdict(list)
    for t in industry_drug:
        name = t.get("sponsor_name") or "Unknown Sponsor"
        by_sponsor[name].append(t)

    # 3. Build one row per sponsor
    rows = []
    for sponsor_name, sponsor_trials in by_sponsor.items():

        # Modality frequency — most common first, nulls last
        mod_counts: dict[str, int] = defaultdict(int)
        for t in sponsor_trials:
            mod_counts[t.get("modality") or "Unknown"] += 1
        modalities = [m for m, _ in sorted(mod_counts.items(),
                                           key=lambda x: x[1], reverse=True)]

        # Top phase — most common phase across their trials
        phase_counts: dict[str, int] = defaultdict(int)
        for t in sponsor_trials:
            phase_counts[t.get("phase") or "Unknown"] += 1
        top_phase = max(phase_counts, key=phase_counts.__getitem__)

        # Priority score — sum of modality_weight × phase_weight per trial
        score = sum(
            _modality_weight(t.get("modality")) * _phase_weight(t.get("phase"))
            for t in sponsor_trials
        )

        # Priority label
        if score >= 12:
            priority_label = "HIGH"
        elif score >= 4:
            priority_label = "MED"
        else:
            priority_label = "LOW"

        # Individual trial records for the expandable row
        trial_rows = [
            {
                "nct_id":   t.get("nct_id"),
                "title":    t.get("title"),
                "modality": t.get("modality"),
                "phase":    t.get("phase"),
            }
            for t in sponsor_trials
        ]

        rows.append({
            "sponsor_name":    sponsor_name,
            "new_trial_count": len(sponsor_trials),
            "modalities":      modalities,
            "top_phase":       top_phase,
            "priority_score":  round(score, 1),
            "priority_label":  priority_label,
            "trials":          trial_rows,
        })

    # 4. Sort by priority_score descending (highest urgency first)
    rows.sort(key=lambda r: r["priority_score"], reverse=True)
    return rows


# ─────────────────────────────────────────────────────────────────────────
# Remaining question functions — stubs to be filled question by question
# ─────────────────────────────────────────────────────────────────────────

def pick_enriched(snap_meta: dict) -> list:
    """
    Find and load the enriched changelog for this snapshot window.

    Enriched files live in the same dir as changelogs:
        storage/changelogs/enriched_2026-02-20_2026-02-27_v1.json

    Schema:
        metadata.drug_only  : True  (pre-filtered to drug trials only)
        trials[]            : full trial records plus:
            update_type         : "new" | "existing"
            update_categories   : [{category, tier, direction, old_value, new_value, field, note}]
            field_diffs         : [{field, tier, old, new}]

    Returns the trials list, or [] if not found / skipped.
    """
    print("\n  ┌─ ENRICHED FILE SELECTION ───────────────────────────────────")
    print(f"  │  Snapshot window : {snap_meta.get('window_start')} → {snap_meta.get('window_end')}")
    print(f"  │  Looking in      : {CHANGELOG_DIR}")

    win_start = snap_meta.get("window_start", "")
    win_end   = snap_meta.get("window_end", snap_meta.get("as_of", ""))

    if not CHANGELOG_DIR.exists():
        print(f"  │  Dir not found — skipping enriched file")
        print("  └─────────────────────────────────────────────────────────────")
        return []

    candidates = sorted(CHANGELOG_DIR.glob("enriched_*.json"), key=_sort_key, reverse=True)

    if not candidates:
        print(f"  │  No enriched_*.json files found")
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
                    auto_idx = i
                    auto_reason = (
                        f"start matched ({cl_start} == {win_start})" if hit_start
                        else f"end matched ({cl_end} == {win_end})"
                    )
            labels.append(f"{fpath.name}  [{cl_start}→{cl_end}]{match_tag}")
        else:
            labels.append(f"{fpath.name}  (no date range in filename)")
            if auto_idx is None:
                auto_idx = i
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
        data = json.load(chosen.open(encoding="utf-8", errors="replace"))
        trials = data.get("trials", [])
        em = data.get("metadata", {})
        print(f"  │  Trials in enriched file : {len(trials):,}")
        print(f"  │  drug_only               : {em.get('drug_only')}")
        return trials
    except Exception as e:
        print(f"  │  WARNING: could not load enriched file: {e}")
        return []



def _extract_window_dates(filename: str) -> tuple[str, str] | tuple[None, None]:
    """
    Extract (win_start, win_end) from filenames like:
        reclassified_2026-02-20_2026-02-27_v1.json
        enriched_2026-02-20_2026-02-27_v1.json
        2026-02-20_2026-02-27_v1.json
    Returns (None, None) if no date range found.
    """
    m = re.search(r'(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})', filename)
    if m:
        return m.group(1), m.group(2)
    return None, None


def _load_enriched_silent(win_start: str, win_end: str) -> dict | None:
    """
    Silently find and load the enriched file for a given window.
    Returns {ta_mod, drug_new_total, source: "enriched"} or None.
    No user prompt — used for prior-week auto-loading.
    """
    if not CHANGELOG_DIR.exists():
        return None

    for fpath in sorted(CHANGELOG_DIR.glob("enriched_*.json"), key=_sort_key, reverse=True):
        f_start, f_end = _extract_window_dates(fpath.name)
        if f_start == win_start or f_end == win_end:
            try:
                data   = json.load(fpath.open(encoding="utf-8", errors="replace"))
                trials = data.get("trials", [])

                # Compute TA x modality counts for new drug registrations only
                from collections import defaultdict
                ta_mod: dict = defaultdict(lambda: defaultdict(int))
                for t in trials:
                    if t.get("update_type") != "new":
                        continue
                    if not t.get("is_drug_trial", True):
                        continue
                    ta  = t.get("therapeutic_area") or "Unknown"
                    mod = t.get("modality")         or "Unknown"
                    ta_mod[ta][mod] += 1

                drug_new_total = sum(sum(m.values()) for m in ta_mod.values())

                # Phase counts for wq10
                phase_counts: dict = defaultdict(int)
                for t in trials:
                    if t.get("update_type") != "new":
                        continue
                    if not t.get("is_drug_trial", True):
                        continue
                    ph = t.get("phase") or "NA"
                    phase_counts[ph] += 1

                # Modality totals (flat, across all TAs)
                mod_totals: dict = defaultdict(int)
                for mods in ta_mod.values():
                    for mod, n in mods.items():
                        mod_totals[mod] += n

                return {
                    "ta_mod":         {ta: dict(mods) for ta, mods in ta_mod.items()},
                    "mod_totals":     dict(mod_totals),
                    "drug_new_total": drug_new_total,
                    "phase_counts":   dict(phase_counts),
                    "source":         "enriched",
                    "filename":       fpath.name,
                }
            except Exception:
                return None

    return None



def _load_changelog_counts_silent(win_start: str, win_end: str) -> dict:
    """
    Silently find the changelog for a given window and return high-level counts.
    Returns {} if not found or on error — no user prompt.
    Keys: new_active_all, new_inactive, existing_business, existing_metadata
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
                    "new_active_all":    s.get("new_active_registrations", 0),
                    "new_inactive":      s.get("new_inactive_updates",     0),
                    "existing_business": s.get("existing_with_business_changes", 0),
                    "existing_metadata": s.get("existing_metadata_only",   0),
                }
            except Exception:
                return {}
    return {}


def pick_prior_snapshots(current_path: Path, n: int = 3) -> list:
    """
    Find the N snapshots immediately preceding current_path (by date),
    present them to the user for confirmation, and for each load
    its TA×modality counts from the matching enriched file (preferred)
    or from the snapshot summary (fallback).

    Returns a list of dicts (oldest first):
        window_label   str   — e.g. "2026-02-13 → 2026-02-20"
        ta_mod         dict  — {ta: {mod: count}}
        drug_new_total int   — total new drug registrations that week
        source         str   — "enriched" | "snapshot_summary"
        filename       str   — source filename
    """
    print("\n  ┌─ PRIOR WEEKS SELECTION (wq7 rolling average) ──────────────")

    all_files = []
    for d in SNAPSHOT_DIRS:
        if d.exists():
            all_files += list(d.glob("*.json"))

    # Exclude the current snapshot; sort newest-first
    all_files = [f for f in all_files if f.resolve() != current_path.resolve()]
    all_files.sort(key=_sort_key, reverse=True)

    if not all_files:
        print("  │  No prior snapshots found — wq7 heat will be disabled")
        print("  └─────────────────────────────────────────────────────────────")
        return []

    # Take at most N most recent prior snapshots
    candidates = all_files[:max(n, 1)]

    print(f"  │  Found {len(all_files)} prior snapshot(s). Will use up to {n}:")
    print()

    # Check enriched availability for each candidate
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
        # Label describes what that choice does
        if i == 0:
            use_desc = f"use all {len(candidates)} weeks"
        else:
            use_desc = f"use only the {i+1} most recent week{'s' if i > 0 else ''}"
        labels.append(f"{f.name}  [{tag}]{enriched_avail}  → {use_desc}")

    labels.append("(none — skip prior weeks, disable heat comparison)")

    idx_skip = len(candidates)
    idx = _prompt_choice(
        f"Prior weeks to load",
        labels, default=0          # always default to "use all"
    )
    print("  └─────────────────────────────────────────────────────────────")

    if idx == idx_skip:
        print("  Prior weeks: disabled.")
        return []

    # idx == 0 → use all N; idx == 1 → top 2; idx == 2 → top 1; etc.
    # (option N means "up to and including candidate N" because the label
    #  says "use only the N+1 most recent weeks")
    if idx == 0:
        chosen_files = candidates           # all
    else:
        chosen_files = candidates[:idx + 1] # top idx+1

    print(f"\n  Loading {len(chosen_files)} prior week(s) ...")

    results = []
    for f in reversed(chosen_files):   # oldest first
        ws, we = _extract_window_dates(f.name)
        window_label = f"{ws} → {we}" if ws else f.stem

        # Try enriched file first
        enriched = _load_enriched_silent(ws, we) if (ws or we) else None

        if enriched:
            entry = enriched
            entry["window_label"] = window_label
            print(f"    {window_label}  ({entry['drug_new_total']:,} new drug trials) [enriched]")
        else:
            # Fallback: load snapshot summary
            try:
                raw     = json.load(f.open(encoding="utf-8", errors="replace"))
                summary = raw.get("summary", {})
                ta_mod  = summary.get("ta_modality_counts_true_drugs", {})
                dtc     = summary.get("drug_trial_counts", {})
                total   = dtc.get("drug_trials", 0)
                # Derive mod_totals from ta_mod
                from collections import defaultdict as _dd
                _mod_totals: dict = _dd(int)
                for _mods in ta_mod.values():
                    for _mod, _n in _mods.items():
                        _mod_totals[_mod] += _n
                entry = {
                    "ta_mod":         ta_mod,
                    "mod_totals":     dict(_mod_totals),
                    "drug_new_total": total,
                    "phase_counts":   {},   # not available from snapshot summary
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
            entry.update(cl_counts)   # keys: new_active_all, new_inactive, etc.

        results.append(entry)

    return results


def pick_master_db() -> dict:
    """
    Find the latest master_DB_*.json in MASTER_DB_DIR, present it to the
    user, and return only its summary{} block.

    We load summary{} only — trials[] (38k+ records) is not needed for
    any current weekly question. If a quarterly question needs trial-level
    data in the future, load it there on demand.

    Returns the summary dict, or {} if not found / skipped.
    """
    print("\n  \u250c\u2500 MASTER DB SELECTION \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    print(f"  \u2502  Looking in : {MASTER_DB_DIR}")

    if not MASTER_DB_DIR.exists():
        print(f"  \u2502  Dir not found \u2014 skipping master DB")
        print("  \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
        return {}, ""

    candidates = sorted(MASTER_DB_DIR.glob("master_DB*.json"), key=_sort_key, reverse=True)

    if not candidates:
        print(f"  \u2502  No master_DB*.json files found in {MASTER_DB_DIR}")
        print("  \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
        return {}, ""

    print(f"  \u2502  Found {len(candidates)} master DB file(s):\n")

    labels = [f.name for f in candidates]
    labels.append("(none \u2014 skip master DB)")

    idx = _prompt_choice("Pick a master DB", labels, default=0)
    print("  \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")

    if idx == len(candidates):
        print("  \u2502  Master DB skipped.")
        return {}, ""

    chosen = candidates[idx]
    print(f"\n  \u2502  Selected  : {chosen.name}")
    print(f"  \u2502  Full path : {chosen}")

    try:
        data = json.load(chosen.open(encoding="utf-8", errors="replace"))
        summary = data.get("summary", {})
        meta    = data.get("metadata", {})
        dtc     = summary.get("drug_trial_counts", {})
        drug_total = dtc.get("drug_trials", 0)
        export_date = meta.get("export_date")
        print(f"  │  Drug trials in master DB : {drug_total:,}")
        print(f"  │  Export date              : {export_date}")
        return summary, chosen.name
    except Exception as e:
        print(f"  \u2502  WARNING: could not load master DB: {e}")
        return {}, ""


def wq2_client_alert_cards(trials: list, client_list: list) -> list:
    """BD / wq2 — stub. Needs manual client_list input."""
    return []

def wq3_ta_deviation_bars(summary: dict, prior_summaries: list) -> list:
    """BD / wq3 — stub. Needs prior snapshots for 4-week rolling average."""
    return []

def wq4_social_stat_cards(summary: dict, enriched_counts: dict) -> list:
    """
    Marketing / wq4 — "What's the headline stat for this week's
    social/newsletter content?"

    Source: snapshot summary{} (pre-computed by summary_v2.py)
    Also uses enriched_counts for the new vs updated split on card 1.

    Returns a list of exactly 4 card dicts — one per social stat.
    Each card has:
        id          str  — "wq4_c1" … "wq4_c4"
        title       str  — headline label
        value       str  — big display number or name
        sub         str  — supporting line
        detail      list — [{label, value, pct?}] for the breakdown rows
        note        str  — small footnote (source / caveat)

    Cards:
        1. Drug Trials This Window  → drug_info_overview.drug_trials_total
                                      + new vs existing from enriched_counts
        2. Top Therapeutic Area     → #1 TA by total drug trial count
                                      + its top 3 modalities
        3. Modality Spotlight       → top 4 modalities, count + % of drug trials
        4. Beyond Disease           → top non-disease categories
    """
    dio       = summary.get("drug_info_overview", {})
    ta_mod    = summary.get("ta_modality_counts_true_drugs", {})
    intent    = summary.get("drug_study_intent", {})
    non_dis   = summary.get("non_disease_study_categories", {})

    drug_total = dio.get("drug_trials_total", 0)

    # ── Card 1 : Drug Trials This Window ────────────────────────────────
    ec = enriched_counts or {}
    detail_c1 = []
    if ec.get("available"):
        detail_c1 = [
            {"label": "New registrations", "value": ec.get("new", 0)},
            {"label": "Existing updated",  "value": ec.get("existing", 0)},
        ]
    else:
        disease_n    = intent.get("disease",     0)
        non_disease_n = intent.get("non_disease", 0)
        if disease_n or non_disease_n:
            detail_c1 = [
                {"label": "Disease studies",     "value": disease_n},
                {"label": "Non-disease studies", "value": non_disease_n},
            ]

    card1 = {
        "id":     "wq4_c1",
        "title":  "Drug Trials This Window",
        "value":  f"{drug_total:,}",
        "sub":    "drug trials in the weekly pulse",
        "detail": detail_c1,
        "note":   "Source: snapshot summary — drug_info_overview",
    }

    # ── Card 2 : Top Therapeutic Area ───────────────────────────────────
    # Sum across all modalities per TA to find #1
    ta_totals = {
        ta: sum(mods.values())
        for ta, mods in ta_mod.items()
        if ta and ta != "Unknown"
    }
    top_ta      = max(ta_totals, key=ta_totals.__getitem__) if ta_totals else "—"
    top_ta_n    = ta_totals.get(top_ta, 0)
    top_ta_pct  = round(top_ta_n / drug_total * 100, 1) if drug_total else 0.0

    # Top 3 modalities within that TA
    ta_mod_breakdown = sorted(
        (ta_mod.get(top_ta) or {}).items(),
        key=lambda x: x[1], reverse=True
    )[:3]
    detail_c2 = [
        {
            "label": mod,
            "value": count,
            "pct":   round(count / top_ta_n * 100, 1) if top_ta_n else 0.0,
        }
        for mod, count in ta_mod_breakdown
    ]

    card2 = {
        "id":     "wq4_c2",
        "title":  "Top Therapeutic Area",
        "value":  top_ta,
        "sub":    f"{top_ta_n:,} trials · {top_ta_pct}% of drug trials",
        "detail": detail_c2,
        "note":   "Source: ta_modality_counts_true_drugs",
    }

    # ── Card 3 : Modality Spotlight ──────────────────────────────────────
    # Flatten ta_modality_counts_true_drugs → modality totals
    mod_totals: dict = defaultdict(int)
    for mods in ta_mod.values():
        for mod, n in mods.items():
            mod_totals[mod] += n

    top_mods = sorted(mod_totals.items(), key=lambda x: x[1], reverse=True)[:4]
    detail_c3 = [
        {
            "label": mod.replace("_", " ").title(),
            "value": count,
            "pct":   round(count / drug_total * 100, 1) if drug_total else 0.0,
        }
        for mod, count in top_mods
    ]

    card3 = {
        "id":     "wq4_c3",
        "title":  "Modality Spotlight",
        "value":  top_mods[0][0].replace("_", " ").title() if top_mods else "—",
        "sub":    f"leads with {top_mods[0][1]:,} trials" if top_mods else "",
        "detail": detail_c3,
        "note":   "% of drug trials in this window",
    }

    # ── Card 4 : Beyond Disease ──────────────────────────────────────────
    top_non_dis = sorted(non_dis.items(), key=lambda x: x[1], reverse=True)[:4]
    non_dis_total = sum(non_dis.values())
    detail_c4 = [
        {
            "label": cat.replace("_", " ").title(),
            "value": count,
            "pct":   round(count / non_dis_total * 100, 1) if non_dis_total else 0.0,
        }
        for cat, count in top_non_dis
    ]

    card4 = {
        "id":     "wq4_c4",
        "title":  "Beyond Disease",
        "value":  f"{non_dis_total:,}",
        "sub":    "non-disease drug trials",
        "detail": detail_c4,
        "note":   "Source: non_disease_study_categories",
    }

    return [card1, card2, card3, card4]

def wq5_modality_index_chart(summary: dict, master_db_summary: dict) -> list:
    """Marketing / wq5 — stub. Needs master DB for baseline proportions."""
    return []

def wq6_conference_snapshot(trials: list, ta_filter: str, prior_summaries: list) -> dict:
    """Marketing / wq6 — stub. Needs prior snapshots and a TA filter."""
    return {}





def wq7_ta_modality_matrix(
    enriched_trials:  list,
    master_db_summary: dict,
    prior_weeks:      list,
) -> dict:
    """
    Scientific / wq7 — TA x Modality Bubble Matrix

    Source  : enriched file, update_type == "new", is_drug_trial == True
    Baseline: prior_weeks list from pick_prior_snapshots()

    Heat formula (week-over-week rate change):
        prior_avg_pct[ta][mod] = mean(
            prior[ta_mod][ta][mod] / prior[drug_new_total]
            for each prior week that has data for this cell
        )
        current_pct  = count / week_total
        heat = (current_pct - prior_avg_pct) / max(prior_avg_pct, 0.001)
        clamped to [-1, +1]

    Falls back to master DB comparison when no prior weeks are available.
    Heat is None when neither prior weeks nor master DB are loaded.
    """
    from collections import defaultdict
    MAX_TA  = 12
    MAX_MOD = 10

    # ── 1. Count current week new drug registrations ──────────────────────
    ta_mod_week:  dict = defaultdict(lambda: defaultdict(int))
    cell_trials:  dict = defaultdict(list)

    for t in enriched_trials:
        if t.get("update_type") != "new":
            continue
        if not t.get("is_drug_trial", True):
            continue
        ta  = t.get("therapeutic_area") or "Unknown"
        mod = t.get("modality")         or "Unknown"
        ta_mod_week[ta][mod] += 1
        cell_key = f"{ta}||{mod}"
        cell_trials[cell_key].append({
            "nct_id": t.get("nct_id"),
            "title":  t.get("title"),
            "phase":  t.get("phase") or "—",
        })

    if not ta_mod_week:
        return {"available": False, "rows": [], "columns": [], "cells": {},
                "row_totals": {}, "col_totals": {}, "grand_total": 0,
                "has_heat": False, "heat_mode": "none", "prior_weeks_used": 0}

    # ── 2. Select top TAs and modalities ──────────────────────────────────
    ta_totals  = {ta: sum(m.values()) for ta, m in ta_mod_week.items()}
    mod_totals: dict = defaultdict(int)
    for mods in ta_mod_week.values():
        for mod, n in mods.items():
            mod_totals[mod] += n

    top_tas  = sorted(ta_totals,  key=ta_totals.__getitem__,  reverse=True)[:MAX_TA]
    top_mods = sorted(mod_totals, key=mod_totals.__getitem__,  reverse=True)[:MAX_MOD]

    week_total  = sum(mod_totals.values()) or 1
    grand_total = sum(ta_totals[ta] for ta in top_tas)

    # ── 3. Decide heat mode and compute baseline ──────────────────────────
    has_prior   = bool(prior_weeks)
    db_ta_mod   = (master_db_summary or {}).get("ta_modality_counts_true_drugs", {})
    db_dtc      = (master_db_summary or {}).get("drug_trial_counts", {})
    db_total    = db_dtc.get("drug_trials", 0)
    has_master  = bool(db_ta_mod and db_total)

    if has_prior:
        heat_mode        = "rolling_avg"
        prior_weeks_used = len(prior_weeks)

        # Build per-cell prior average proportion
        # Each week contributes a proportion only if it has any drug trials
        prior_avg_pct: dict = {}   # (ta, mod) → float
        for ta in top_tas:
            for mod in top_mods:
                contributions = []
                for pw in prior_weeks:
                    pw_total = pw.get("drug_new_total") or 0
                    if pw_total > 0:
                        pw_count = (pw.get("ta_mod") or {}).get(ta, {}).get(mod, 0)
                        contributions.append(pw_count / pw_total)
                prior_avg_pct[(ta, mod)] = (
                    sum(contributions) / len(contributions) if contributions else 0.0
                )

    elif has_master:
        heat_mode        = "master_db"
        prior_weeks_used = 0
    else:
        heat_mode        = "none"
        prior_weeks_used = 0

    # ── 4. Build cells ────────────────────────────────────────────────────
    cells = {}
    for ta in top_tas:
        for mod in top_mods:
            count = ta_mod_week[ta].get(mod, 0)

            # Prior-week average count for tooltip display
            prior_avg_count = None
            if has_prior and prior_weeks:
                totals = [pw.get("drug_new_total") or 0 for pw in prior_weeks]
                counts = [(pw.get("ta_mod") or {}).get(ta, {}).get(mod, 0)
                          for pw in prior_weeks]
                prior_avg_count = round(
                    sum(counts) / len(counts), 1
                ) if counts else None

            # Compute heat
            heat       = None
            heat_label = None
            if count > 0:
                if heat_mode == "rolling_avg":
                    avg_pct  = prior_avg_pct.get((ta, mod), 0.0)
                    curr_pct = count / week_total
                    raw      = (curr_pct - avg_pct) / max(avg_pct, 0.001)
                    heat     = max(-1.0, min(1.0, raw))

                    # Human-readable label for tooltip
                    if avg_pct == 0:
                        heat_label = "new this week — not seen in prior weeks"
                    else:
                        delta_pct = round((heat * 100), 0)
                        if heat >= 0.15:
                            heat_label = f"▲ {abs(delta_pct):.0f}% above {prior_weeks_used}-week avg"
                        elif heat <= -0.15:
                            heat_label = f"▼ {abs(delta_pct):.0f}% below {prior_weeks_used}-week avg"
                        else:
                            heat_label = f"≈ in line with {prior_weeks_used}-week avg"

                elif heat_mode == "master_db":
                    expected_pct = db_ta_mod.get(ta, {}).get(mod, 0) / db_total
                    curr_pct     = count / week_total
                    raw          = (curr_pct - expected_pct) / max(expected_pct, 0.001)
                    heat         = max(-1.0, min(1.0, raw))
                    delta_pct    = round(heat * 100, 0)
                    if heat >= 0.15:
                        heat_label = f"▲ {abs(delta_pct):.0f}% above master DB baseline"
                    elif heat <= -0.15:
                        heat_label = f"▼ {abs(delta_pct):.0f}% below master DB baseline"
                    else:
                        heat_label = "≈ at master DB baseline"

            # Baseline_n for tooltip: master DB count for this cell (informational always)
            baseline_n = db_ta_mod.get(ta, {}).get(mod, 0) if has_master else None

            key = f"{ta}||{mod}"
            cells[key] = {
                "ta":              ta,
                "mod":             mod,
                "count":           count,
                "baseline_n":      baseline_n,
                "prior_avg_count": prior_avg_count,
                "heat":            round(heat, 3) if heat is not None else None,
                "heat_label":      heat_label,
                "trials":          cell_trials.get(key, []),
            }

    row_totals = {ta:  sum(ta_mod_week[ta].get(m, 0) for m in top_mods) for ta in top_tas}
    col_totals = {mod: sum(ta_mod_week[ta].get(mod, 0) for ta in top_tas) for mod in top_mods}

    # Prior week window labels for the tooltip sub-header
    prior_window_labels = [pw.get("window_label", "") for pw in prior_weeks]

    return {
        "available":           True,
        "has_heat":            heat_mode != "none",
        "heat_mode":           heat_mode,     # "rolling_avg" | "master_db" | "none"
        "prior_weeks_used":    prior_weeks_used,
        "prior_window_labels": prior_window_labels,
        "rows":                top_tas,
        "columns":             top_mods,
        "cells":               cells,
        "row_totals":          row_totals,
        "col_totals":          col_totals,
        "grand_total":         grand_total,
        "db_total":            db_total,
        "week_total":          week_total,
    }
def wq8_classification_gap_report(trials: list, summary: dict) -> dict:
    """Scientific / wq8 — stub."""
    return {}

def wq9_mesh_quality_waterfall(summary: dict) -> dict:
    """Scientific / wq9 — stub."""
    return {}

def wq10_velocity_dashboard(
    enriched_trials: list,
    snap_meta:       dict,
    snap_summary:    dict,
    changelog:       dict,
    prior_weeks:     list,
) -> dict:
    """
    Operations / wq10 — Velocity Dashboard

    4 tiles in a 2×2 grid:
      1. New drug registrations sparkline (4 weeks)
      2. TA % change vs prior average  (diverging bar, top 3 + bottom 3)
      3. Modality % change vs prior average  (diverging bar, top 3 + bottom 3)
      4. Phase 1 intake rate — Phase 1 as % of new drug, vs prior average

    Source (current week):
      enriched_trials — new drug registrations, TA/mod/phase breakdown
      changelog — new_active_all (all trial types)
      snap_meta — window dates
    Source (prior weeks):
      prior_weeks list from pick_prior_snapshots (already loaded)
    """
    from collections import defaultdict

    # ── Current week counts from enriched_trials ──────────────────────────
    cur_ta:    dict = defaultdict(int)
    cur_mod:   dict = defaultdict(int)
    cur_phase: dict = defaultdict(int)
    cur_drug_new = 0

    for t in enriched_trials:
        if t.get("update_type") != "new":
            continue
        if not t.get("is_drug_trial", True):
            continue
        cur_drug_new += 1
        cur_ta[t.get("therapeutic_area") or "Unknown"] += 1
        cur_mod[t.get("modality") or "Unknown"] += 1
        cur_phase[(t.get("phase") or "NA").upper()] += 1

    cur_ta    = dict(cur_ta)
    cur_mod   = dict(cur_mod)
    cur_phase = dict(cur_phase)

    # Window label for current week
    ws = snap_meta.get("window_start", "")
    we = snap_meta.get("window_end", snap_meta.get("as_of", ""))
    cur_window_label = f"{ws} → {we}" if ws else "current"

    # Changelog counts for current week (all trial types)
    cur_cl_new_active = changelog.get("new_active_registrations", 0)

    available = cur_drug_new > 0
    has_prior = bool(prior_weeks) and len(prior_weeks) >= 1

    if not available:
        return {"available": False}

    # ── Helper: short label "Feb 27" from "YYYY-MM-DD → YYYY-MM-DD" ───────
    def short_label(window_label: str) -> str:
        import re as _re
        dates = _re.findall(r'\d{4}-(\d{2})-(\d{2})', window_label)
        if len(dates) >= 2:
            mo_map = {"01":"Jan","02":"Feb","03":"Mar","04":"Apr","05":"May",
                      "06":"Jun","07":"Jul","08":"Aug","09":"Sep",
                      "10":"Oct","11":"Nov","12":"Dec"}
            return f"{mo_map.get(dates[1][0], dates[1][0])} {int(dates[1][1])}"
        return window_label[:10]

    # ── Tile 1: Sparkline data (oldest → current) ─────────────────────────
    sparkline_pts = []
    for pw in prior_weeks:   # already oldest-first from pick_prior_snapshots
        sparkline_pts.append({
            "window_label": pw.get("window_label", ""),
            "short_label":  short_label(pw.get("window_label", "")),
            "drug_new":     pw.get("drug_new_total", 0),
        })
    sparkline_pts.append({
        "window_label": cur_window_label,
        "short_label":  short_label(cur_window_label),
        "drug_new":     cur_drug_new,
        "is_current":   True,
    })

    # 3-week average (or however many prior weeks we have)
    prior_drug_totals = [pw.get("drug_new_total", 0) for pw in prior_weeks]
    prior_avg_drug    = sum(prior_drug_totals) / len(prior_drug_totals) if prior_drug_totals else None
    pace_delta_pct    = None
    if prior_avg_drug and prior_avg_drug > 0:
        pace_delta_pct = round((cur_drug_new - prior_avg_drug) / prior_avg_drug * 100, 1)

    # ── Tile 2: TA % change diverging bars ────────────────────────────────
    def _pct_change_bars(cur_counts: dict, cur_total: int,
                         prior_key: str, max_bars: int = 3) -> list:
        """
        For each dimension (TA or mod), compute:
            current_pct   = cur_counts[key] / cur_total
            prior_avg_pct = mean( prior_week[prior_key].get(key,0)
                                  / prior_week['drug_new_total']
                                  for each prior week with drug_new_total > 0 )
            delta = (current_pct - prior_avg_pct) / max(prior_avg_pct, 0.001) * 100
        Returns top max_bars gainers and top max_bars decliners, sorted by |delta|.
        """
        if cur_total == 0:
            return []
        all_keys = set(cur_counts.keys())
        for pw in prior_weeks:
            all_keys |= set((pw.get(prior_key) or {}).keys())

        bars = []
        for key in all_keys:
            # Skip unassigned / non-disease TAs — not meaningful for ops comparison
            if key.lower() in {
                "unassigned drug study", "unassigned", "unknown",
                "non-disease", "non_disease", "other",
            }:
                continue
            c_pct = cur_counts.get(key, 0) / cur_total
            pw_pcts = []
            for pw in prior_weeks:
                pw_total = pw.get("drug_new_total") or 0
                if pw_total > 0:
                    pw_pcts.append((pw.get(prior_key) or {}).get(key, 0) / pw_total)
            avg_pct = sum(pw_pcts) / len(pw_pcts) if pw_pcts else 0.0

            # Skip negligible entries (< 1% current AND < 1% average)
            if c_pct < 0.005 and avg_pct < 0.005:
                continue

            raw_delta = (c_pct - avg_pct) / max(avg_pct, 0.001) * 100
            bars.append({
                "label":        key,
                "current_pct":  round(c_pct * 100, 1),
                "avg_pct":      round(avg_pct * 100, 1),
                "delta_pct":    round(raw_delta, 1),
                "current_n":    cur_counts.get(key, 0),
            })

        bars.sort(key=lambda b: b["delta_pct"], reverse=True)
        gainers  = bars[:max_bars]
        decliners = sorted(bars, key=lambda b: b["delta_pct"])[:max_bars]
        # Combine: gainers descending, then decliners ascending (most negative last)
        combined = gainers + [b for b in decliners if b not in gainers]
        return combined

    ta_bars  = _pct_change_bars(cur_ta,  cur_drug_new, "ta_totals",  max_bars=3) if has_prior else []
    mod_bars = _pct_change_bars(cur_mod, cur_drug_new, "mod_totals", max_bars=3) if has_prior else []

    # ── Tile 4: Phase 1 intake ────────────────────────────────────────────
    PHASE1_KEYS = {"PHASE1", "EARLY_PHASE1", "PHASE1/PHASE2"}

    cur_p1_count = sum(v for k, v in cur_phase.items() if k in PHASE1_KEYS)
    cur_p1_pct   = round(cur_p1_count / cur_drug_new * 100, 1) if cur_drug_new else 0

    # Prior weeks phase 1 — only from enriched (phase_counts is {} for summary fallback)
    prior_p1_pcts = []
    for pw in prior_weeks:
        pc    = pw.get("phase_counts") or {}
        total = pw.get("drug_new_total") or 0
        if pc and total > 0:
            p1 = sum(v for k, v in pc.items() if k in PHASE1_KEYS)
            prior_p1_pcts.append(round(p1 / total * 100, 1))

    avg_p1_pct     = round(sum(prior_p1_pcts) / len(prior_p1_pcts), 1) if prior_p1_pcts else None
    p1_delta_pct   = round(cur_p1_pct - avg_p1_pct, 1) if avg_p1_pct is not None else None

    # Sparkline of Phase 1 % across weeks
    p1_sparkline = []
    for pw in prior_weeks:
        pc    = pw.get("phase_counts") or {}
        total = pw.get("drug_new_total") or 0
        pct   = None
        if pc and total > 0:
            p1 = sum(v for k, v in pc.items() if k in PHASE1_KEYS)
            pct = round(p1 / total * 100, 1)
        p1_sparkline.append({
            "short_label": short_label(pw.get("window_label", "")),
            "pct":         pct,
        })
    p1_sparkline.append({
        "short_label": short_label(cur_window_label),
        "pct":         cur_p1_pct,
        "is_current":  True,
    })

    return {
        "available":         True,
        "has_prior":         has_prior,
        "n_prior_weeks":     len(prior_weeks),
        "cur_window_label":  cur_window_label,
        # Tile 1
        "sparkline":         sparkline_pts,
        "cur_drug_new":      cur_drug_new,
        "prior_avg_drug":    round(prior_avg_drug, 1) if prior_avg_drug else None,
        "pace_delta_pct":    pace_delta_pct,
        # Tile 2
        "ta_bars":           ta_bars,
        # Tile 3
        "mod_bars":          mod_bars,
        # Tile 4
        "phase1": {
            "cur_count":   cur_p1_count,
            "cur_pct":     cur_p1_pct,
            "avg_pct":     avg_p1_pct,
            "delta_pct":   p1_delta_pct,
            "sparkline":   p1_sparkline,
            "has_prior":   bool(prior_p1_pcts),
        },
    }

def wq11_complexity_waffle(summary: dict) -> dict:
    """Operations / wq11 — stub."""
    return {}

def wq12_phase1_intake_list(trials: list) -> list:
    """Operations / wq12 — stub."""
    return []


def extract_changelog(cl: dict | None) -> dict:
    """
    Reshape the changelog JSON into the structure the dashboard needs.

    Actual changelog structure (from your file):
        {
          "generated_at": "...",
          "window":       "2026-02-20_2026-02-27",
          "summary": {
            "total_trials":                  2525,
            "new_active_registrations":       528,
            "new_inactive_updates":           204,
            "existing_with_business_changes": 1250,
            "existing_metadata_only":         543,
            "category_counts": {
              "sites_changed":      684,
              "metadata_only":      543,
              "new_registration":   528,
              "enrollment_change":  272,
              "phase_format_change":262,
              ...
            }
          }
        }
    """
    if not cl:
        return {"available": False}

    cl_summary = cl.get("summary", {})
    return {
        "available":                    True,
        "generated_at":                 cl.get("generated_at"),
        "window":                       cl.get("window"),
        "total_trials":                 cl_summary.get("total_trials", 0),
        "new_active_registrations":     cl_summary.get("new_active_registrations", 0),
        "new_inactive_updates":         cl_summary.get("new_inactive_updates", 0),
        "existing_with_business_changes": cl_summary.get("existing_with_business_changes", 0),
        "existing_metadata_only":       cl_summary.get("existing_metadata_only", 0),
        "category_counts":              cl_summary.get("category_counts", {}),
    }


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    print("═" * 60)
    print("  ALEXIS Weekly Viz Generator — Interactive Mode")
    print("═" * 60)

    if not TEMPLATE.exists():
        print(f"\nERROR: Template not found at:\n  {TEMPLATE}")
        sys.exit(1)

    # 1. Pick snapshot
    snap_path, is_rec = pick_snapshot()

    # 2. Load trials
    print(f"\n  Loading {snap_path.name} ...")
    with snap_path.open("r", encoding="utf-8", errors="replace") as f:
        raw = json.load(f)
    meta   = raw.get("metadata", {})
    trials = raw.get("trials", [])
    print(f"  Trials loaded : {len(trials):,}")
    print(f"  run_id        : {meta.get('run_id')}")
    print(f"  as_of         : {meta.get('as_of')}")
    print(f"  window        : {meta.get('window_start')} → {meta.get('window_end')}")

    # 3. Pick changelog and enriched file
    cl_raw          = pick_changelog(meta)
    cl_data         = extract_changelog(cl_raw)
    enriched_trials = pick_enriched(meta)
    master_summary, master_db_filename = pick_master_db()
    prior_weeks = pick_prior_snapshots(snap_path, n=3)

    if enriched_trials:
        new_count = sum(1 for t in enriched_trials if t.get("update_type") == "new")
        existing_count = sum(1 for t in enriched_trials if t.get("update_type") == "existing")
        print(f"  Enriched trials : {len(enriched_trials):,} total")
        print(f"    update_type=new      : {new_count:,}")
        print(f"    update_type=existing : {existing_count:,}")
    else:
        print("  Enriched file not loaded — wq1 will return empty results")

    # 4. Build per-question data
    print("\n  Building per-question data ...")

    snap_summary = raw.get("summary", {})   # pre-computed by weekly_pulse_clinical_v2.py

    # enriched_counts used by wq4 and injected into the HTML payload
    enriched_counts = {
        "available": bool(enriched_trials),
        "total":     len(enriched_trials),
        "new":       sum(1 for t in enriched_trials if t.get("update_type") == "new"),
        "existing":  sum(1 for t in enriched_trials if t.get("update_type") == "existing"),
    }

    wq1_data = wq1_sponsor_action_table(enriched_trials)
    print(f"  wq1 : {len(wq1_data)} INDUSTRY sponsors with new trials this week")

    # Stubs — will be replaced question by question
    wq2_data  = wq2_client_alert_cards(trials, client_list=[])
    wq3_data  = wq3_ta_deviation_bars(snap_summary, prior_summaries=[])
    wq4_data  = wq4_social_stat_cards(snap_summary, enriched_counts)
    print(f"  wq4 : {len(wq4_data)} stat cards")
    wq5_data  = wq5_modality_index_chart(snap_summary, master_db_summary=master_summary)
    wq6_data  = wq6_conference_snapshot(trials, ta_filter="", prior_summaries=[])
    wq7_data  = wq7_ta_modality_matrix(enriched_trials, master_summary, prior_weeks)
    if wq7_data.get("available"):
        heat_info = (
            f"rolling avg ({wq7_data['prior_weeks_used']} weeks)"
            if wq7_data["heat_mode"] == "rolling_avg"
            else wq7_data["heat_mode"]
        )
        print(f"  wq7 : {len(wq7_data['rows'])} TAs × "
              f"{len(wq7_data['columns'])} modalities "
              f"({wq7_data['grand_total']} new registrations) "
              f"[heat: {heat_info}]")
    else:
        print("  wq7 : no data — enriched file empty or not loaded")
    wq8_data  = wq8_classification_gap_report(trials, snap_summary)
    wq9_data  = wq9_mesh_quality_waterfall(snap_summary)
    wq10_data = wq10_velocity_dashboard(
        enriched_trials, meta, snap_summary, cl_data, prior_weeks)
    if wq10_data.get("available"):
        print(f"  wq10: sparkline {len(wq10_data['sparkline'])} pts, "
              f"cur={wq10_data['cur_drug_new']} drug new, "
              f"pace {wq10_data['pace_delta_pct']:+.1f}%"
              if wq10_data['pace_delta_pct'] is not None else
              f"  wq10: {wq10_data['cur_drug_new']} new drug trials (no prior avg)")
    else:
        print("  wq10: no data")
    wq11_data = wq11_complexity_waffle(snap_summary)
    wq12_data = wq12_phase1_intake_list(trials)

    # 5. Inject into HTML
    data = {
        "generated_at":    datetime.now().isoformat(),
        "snapshot_file":   snap_path.name,
        "is_reclassified": is_rec,
        "metadata":        meta,
        "snap_summary":    snap_summary,
        "changelog":       cl_data,
        "enriched_counts":  enriched_counts,
        "master_db_meta":   {
            "available":   bool(master_summary),
            "drug_trials": (master_summary.get("drug_trial_counts") or {}).get("drug_trials", 0),
            "rare_pct":    RARE_MODALITY_PCT,
            "filename":    master_db_filename,
        },
        "prior_weeks_meta": [
            {"window_label": pw["window_label"], "source": pw["source"],
             "drug_new_total": pw["drug_new_total"]}
            for pw in prior_weeks
        ],
        "wq1":  wq1_data,
        "wq2":  wq2_data,
        "wq3":  wq3_data,
        "wq4":  wq4_data,
        "wq5":  wq5_data,
        "wq6":  wq6_data,
        "wq7":  wq7_data,
        "wq8":  wq8_data,
        "wq9":  wq9_data,
        "wq10": wq10_data,
        "wq11": wq11_data,
        "wq12": wq12_data,
    }

    template  = TEMPLATE.read_text(encoding="utf-8")
    data_json = json.dumps(data, separators=(",", ":"), default=str)
    OUTPUT.write_text(template.replace(PLACEHOLDER, data_json, 1), encoding="utf-8")

    print("\n" + "═" * 60)
    print(f"  Output : {OUTPUT}")
    print("═" * 60)

    # ── Auto-open ──────────────────────────────────────────────────
    opened = False
    try:
        import platform
        system = platform.system()

        if system == "Linux" and "microsoft" in platform.uname().release.lower():
            # WSL: convert to Windows UNC path and hand off to cmd.exe
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
