"""
analytics/mk_sq1.py
────────────────────
MK / sq1 — Modality Landscape for Thought Leadership Content

Business question:
    "What is the current modality landscape for thought leadership content?"

Source:
    Master DB trials[] (full active universe — ALL sponsors, not just industry).
    Requires is_drug_trial=True.

Returns:
    dict with available, total_drug_trials, periods, modalities, meta.

Sidecar cache:
    On first compute, writes mk_sq1_cache_YYYY_QN.json next to the master DB.
    Subsequent calls load from cache if cache mtime >= DB mtime.
"""

import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from analytics.shared import modality_weight


def _period_from_filename(fname: str) -> str | None:
    """Extract YYYY_QN from master_DB_YYYY_QN.json."""
    m = re.search(r'(\d{4})_(Q\d)', fname)
    return f"{m.group(1)}_{m.group(2)}" if m else None


def _sort_period(period: str) -> tuple:
    """Sortable tuple from YYYY_QN."""
    m = re.match(r'(\d{4})_Q(\d)', period)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _maturity_label(phase_dist: dict) -> str:
    """Classify phase distribution as early-heavy, late-heavy, or balanced."""
    total = sum(phase_dist.values())
    if total == 0:
        return "balanced"
    early = 0
    late = 0
    for k, v in phase_dist.items():
        ku = k.upper()
        if "PHASE2/PHASE3" in ku:
            early += v
        elif any(x in ku for x in ("EARLY", "PHASE1", "PHASE2")):
            early += v
        elif any(x in ku for x in ("PHASE3", "PHASE4")):
            late += v
    if early / total > 0.50:
        return "early-heavy"
    if late / total > 0.50:
        return "late-heavy"
    return "balanced"


MIN_TRIALS = 5


def sq1_modality_landscape(master_db_path: str) -> dict:
    """
    Compute modality landscape for a single master DB.

    Args:
        master_db_path: absolute path to master_DB_YYYY_QN.json

    Returns:
        dict with keys: available, total_drug_trials, period, modalities, meta
    """
    db_path = Path(master_db_path)

    cache_name = db_path.name.replace("master_DB_", "mk_sq1_cache_")
    cache_path = db_path.parent / cache_name

    if cache_path.exists():
        if os.path.getmtime(str(cache_path)) >= os.path.getmtime(str(db_path)):
            return json.loads(cache_path.read_text(encoding="utf-8"))

    with db_path.open("r", encoding="utf-8", errors="replace") as f:
        raw = json.load(f)

    trials = raw.get("trials", [])
    meta = raw.get("metadata", {})

    drug_trials = [t for t in trials if t.get("is_drug_trial")]

    by_mod: dict[str, list] = defaultdict(list)
    for t in drug_trials:
        mod = t.get("modality") or "Unknown"
        by_mod[mod].append(t)

    total = len(drug_trials)

    mod_rows = []
    for mod_name, mod_trials in by_mod.items():
        count = len(mod_trials)
        if count < MIN_TRIALS:
            continue

        pct = round(100 * count / total, 2) if total else 0

        ta_counts = Counter(
            t.get("therapeutic_area") or "Unknown" for t in mod_trials
        )
        top_tas = [
            {"name": name, "count": cnt}
            for name, cnt in ta_counts.most_common(5)
            if name and not any(x in name.lower() for x in ("unassigned", "non-disease"))
        ]

        phase_counts = Counter(
            t.get("phase") or "NA" for t in mod_trials
        )
        phase_dist = dict(phase_counts.most_common())

        maturity = _maturity_label(phase_dist)

        sponsors = set(t.get("sponsor_name") or "Unknown" for t in mod_trials)
        unique_sponsors = len(sponsors)

        class_counts = Counter(
            (t.get("sponsor_class") or "OTHER").upper() for t in mod_trials
        )
        sponsor_class_split = dict(class_counts.most_common())

        cw = modality_weight(mod_name)

        mod_rows.append({
            "name":                mod_name,
            "count":               count,
            "pct":                 pct,
            "top_tas":             top_tas,
            "phase_dist":          phase_dist,
            "maturity":            maturity,
            "unique_sponsors":     unique_sponsors,
            "sponsor_class_split": sponsor_class_split,
            "complexity_weight":   cw,
        })

    mod_rows.sort(key=lambda r: r["count"], reverse=True)

    period = _period_from_filename(db_path.name)

    result = {
        "available":        True,
        "total_drug_trials": total,
        "period":           period,
        "modalities":       mod_rows,
        "meta": {
            "master_db_file":    db_path.name,
            "total_drug_trials": total,
            "unique_modalities": len(mod_rows),
            "export_date":       meta.get("export_date"),
        },
    }

    cache_path.write_text(
        json.dumps(result, indent=2, default=str),
        encoding="utf-8",
    )

    return result


def sq1_full_history(master_db_dir: str) -> dict:
    """
    Compute modality landscape for ALL master DBs in a directory,
    assemble time series, compute trends and YoY deltas.

    Args:
        master_db_dir: path to directory containing master_DB_*.json files

    Returns:
        dict ready for the SQ1ModalityLandscape JSX component
    """
    db_dir = Path(master_db_dir)
    db_files = sorted(db_dir.glob("master_DB_*.json"), key=lambda f: f.name)

    if not db_files:
        return {"available": False}

    all_snapshots: list[dict] = []
    for db_file in db_files:
        period = _period_from_filename(db_file.name)
        if not period:
            continue
        snapshot = sq1_modality_landscape(str(db_file))
        all_snapshots.append(snapshot)

    if not all_snapshots:
        return {"available": False}

    all_snapshots.sort(key=lambda s: _sort_period(s.get("period", "")))

    periods = [s["period"] for s in all_snapshots]
    current = all_snapshots[-1]

    period_lookup: dict[str, dict[str, dict]] = {}
    for snap in all_snapshots:
        p = snap["period"]
        mod_map = {}
        for m in snap["modalities"]:
            mod_map[m["name"]] = {"count": m["count"], "pct": m["pct"]}
        period_lookup[p] = mod_map

    for mod in current["modalities"]:
        name = mod["name"]

        history = []
        for p in periods:
            pm = period_lookup.get(p, {}).get(name)
            if pm:
                history.append({"period": p, "count": pm["count"], "pct": pm["pct"]})
            else:
                history.append({"period": p, "count": 0, "pct": 0})
        mod["history"] = history

        non_zero = [h for h in history if h["count"] > 0]
        if len(non_zero) >= 2:
            first_count = non_zero[0]["count"]
            last_count = non_zero[-1]["count"]
            if first_count > 0:
                growth = (last_count - first_count) / first_count * 100
                mod["growth_rate"] = round(growth, 1)
                if growth > 10:
                    mod["trend"] = "growing"
                elif growth < -10:
                    mod["trend"] = "declining"
                else:
                    mod["trend"] = "stable"
            else:
                mod["growth_rate"] = None
                mod["trend"] = "growing" if last_count > 0 else "stable"
        else:
            mod["growth_rate"] = None
            mod["trend"] = "stable"

        latest_period = periods[-1]
        m_yoy = re.match(r'(\d{4})_Q(\d)', latest_period)
        if m_yoy:
            yoy_period = f"{int(m_yoy.group(1)) - 1}_Q{m_yoy.group(2)}"
            yoy_data = period_lookup.get(yoy_period, {}).get(name)
            if yoy_data:
                mod["delta_yoy_count"] = mod["count"] - yoy_data["count"]
                mod["delta_yoy_pct_pts"] = round(mod["pct"] - yoy_data["pct"], 2)
            else:
                mod["delta_yoy_count"] = None
                mod["delta_yoy_pct_pts"] = None
        else:
            mod["delta_yoy_count"] = None
            mod["delta_yoy_pct_pts"] = None

    result = {
        "available":        True,
        "total_drug_trials": current["total_drug_trials"],
        "periods":          periods,
        "modalities":       current["modalities"],
        "meta": {
            **current["meta"],
            "periods_loaded": len(periods),
        },
    }

    return result

