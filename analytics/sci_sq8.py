"""
analytics/sci_sq8.py
──────────────────────────
Scientific / sq8 — Biomarker × TA Heatmap

Business question:
    "Which TA × modality intersections drive the most bioanalytical complexity?"
    (Re-framed: which biomarker categories appear across which TAs?)

Source:
    Master DB trials[] (full active universe).
    Classifies outcome text into biomarker categories, then cross-tabs
    biomarker × therapeutic area.

Returns:
    dict matching the wq7 bubble matrix shape:
        rows          list  — biomarker category names
        columns       list  — top TAs by distinct biomarker-tagged trial count
        cells         dict  — keyed by "biomarker||ta", each with count,
                              total_count, and up to MAX_TRIALS_PER_CELL trials
        row_totals    dict  — total trials per biomarker category
        col_totals    dict  — total trials per TA
        grand_total   int   — total distinct biomarker-tagged trials

Sidecar cache:
    Writes sq8_cache_YYYY_QN.json next to the master DB file.
"""

import json
import os
from collections import defaultdict
from pathlib import Path

from policy.biomarker_policy import BIOMARKER_CATEGORIES, classify_trial_biomarkers


MAX_TA = 12
MAX_TRIALS_PER_CELL = 20


def sq8_biomarker_ta_matrix(master_db_path: str) -> dict:
    """
    Compute biomarker × TA bubble matrix from master DB.

    Args:
        master_db_path: absolute path to master_DB_YYYY_QN.json

    Returns:
        dict with keys: available, rows, columns, cells, row_totals,
        col_totals, grand_total, meta
    """
    db_path = Path(master_db_path)

    # ── Sidecar cache ─────────────────────────────────────────────
    cache_name = db_path.name.replace("master_DB_", "sq8_cache_")
    cache_path = db_path.parent / cache_name

    if cache_path.exists():
        if os.path.getmtime(str(cache_path)) >= os.path.getmtime(str(db_path)):
            return json.loads(cache_path.read_text(encoding="utf-8"))

    # ── Load master DB ────────────────────────────────────────────
    with db_path.open("r", encoding="utf-8", errors="replace") as f:
        raw = json.load(f)

    trials = raw.get("trials", [])
    meta = raw.get("metadata", {})

    # ── Filter: drug trials only ──────────────────────────────────
    drug_trials = [t for t in trials if t.get("is_drug_trial")]

    if not drug_trials:
        return {
            "available": False,
            "rows": [], "columns": [], "cells": {},
            "row_totals": {}, "col_totals": {}, "grand_total": 0,
        }

    # ── Classify each trial ───────────────────────────────────────
    bm_ta_count: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    cell_trials: dict[str, list] = defaultdict(list)
    ta_tagged: dict[str, int] = defaultdict(int)
    cell_total: dict[str, int] = defaultdict(int)
    total_tagged = 0

    for t in drug_trials:
        evidence_dict = classify_trial_biomarkers(t)
        if not evidence_dict:
            continue

        ta = t.get("therapeutic_area") or "Unknown"
        total_tagged += 1

        # Count distinct tagged trials per TA (once per trial, not per category)
        ta_tagged[ta] += 1

        for cat in evidence_dict:
            bm_ta_count[cat][ta] += 1
            cell_key = f"{cat}||{ta}"
            cell_total[cell_key] += 1
            if len(cell_trials[cell_key]) < MAX_TRIALS_PER_CELL:
                cell_trials[cell_key].append({
                    "nct_id":  t.get("nct_id"),
                    "title":   t.get("title"),
                    "phase":   t.get("phase") or "NA",
                    "trigger": evidence_dict[cat]["trigger"],
                    "source":  evidence_dict[cat]["source"],
                    "context": evidence_dict[cat]["context"],
                })

    if not bm_ta_count:
        return {
            "available": False,
            "rows": [], "columns": [], "cells": {},
            "row_totals": {}, "col_totals": {}, "grand_total": 0,
        }

    # ── Select top TAs ────────────────────────────────────────────
    # Rank by distinct tagged trial count; exclude "Unknown"
    ta_ranked = sorted(
        (ta for ta in ta_tagged if ta != "Unknown"),
        key=ta_tagged.__getitem__,
        reverse=True,
    )
    top_tas = ta_ranked[:MAX_TA]
    # Push "Unknown" to end if it exists and there is room
    if "Unknown" in ta_tagged and len(top_tas) < MAX_TA:
        top_tas.append("Unknown")

    # Rows: all biomarker categories (fixed order from policy)
    rows = list(BIOMARKER_CATEGORIES.keys())

    # ── Build cells ───────────────────────────────────────────────
    cells = {}
    row_totals = {}
    col_totals = {ta: ta_tagged.get(ta, 0) for ta in top_tas}

    for bm in rows:
        row_total = 0
        for ta in top_tas:
            count = bm_ta_count.get(bm, {}).get(ta, 0)
            cell_key = f"{bm}||{ta}"
            cells[cell_key] = {
                "bm":          bm,
                "ta":          ta,
                "count":       count,
                "total_count": cell_total.get(cell_key, 0),
                "trials":      cell_trials.get(cell_key, []),
            }
            row_total += count
        row_totals[bm] = row_total

    grand_total = total_tagged

    # ── Assemble result ───────────────────────────────────────────
    result = {
        "available":   True,
        "rows":        rows,
        "columns":     top_tas,
        "cells":       cells,
        "row_totals":  row_totals,
        "col_totals":  col_totals,
        "grand_total": grand_total,
        "meta": {
            "master_db_file":    db_path.name,
            "total_drug_trials": len(drug_trials),
            "total_tagged":      total_tagged,
            "export_date":       meta.get("export_date"),
        },
    }

    # ── Write sidecar cache ───────────────────────────────────────
    cache_path.write_text(
        json.dumps(result, indent=2, default=str),
        encoding="utf-8",
    )

    return result
