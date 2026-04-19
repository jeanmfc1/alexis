"""
analytics/bd_sq3.py
-------------------
BD / sq3 -- Therapeutic Area Growth / Decline Over Time

Business question:
    "Which therapeutic areas are growing or shrinking year-over-year?"

Source:
    all master_DB_*.json files in storage/snapshots/clinical_trials_v2/active_universe

Sidecar cache:
    Each master DB gets a bd_sq3_cache_YYYY_QN.json written next to it
    (in the active_universe directory).  On subsequent runs, the cache
    is used when its mtime is >= the master DB mtime.  This makes the
    walk effectively free except for the most recently updated
    quarter.  Keeps peak RAM to a single master-DB parse.
"""

from __future__ import annotations
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

EXCLUDE_TAS = {"Unassigned drug study", "Non-disease drug study"}
TOP_N_TAS = 12


def _period_from_filename(fn: str) -> str:
    m = re.search(r"(\d{4})[_\s]?Q(\d)", fn, re.IGNORECASE)
    return f"{m.group(1)}_Q{m.group(2)}" if m else fn


def _sort_period(p: str) -> tuple[int, int]:
    m = re.match(r"(\d{4})_Q(\d)", p)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _yoy_period(p: str) -> str | None:
    m = re.match(r"(\d{4})_Q(\d)", p)
    return f"{int(m.group(1)) - 1}_Q{m.group(2)}" if m else None


def _compute_one_period(db_path: Path) -> dict:
    """Return {ta: {count, modalities(top5), sponsors(top5), phases(full)}}
    for a single master DB, backed by a sidecar cache next to the file."""
    cache_name = db_path.name.replace("master_DB_", "bd_sq3_cache_")
    cache_path = db_path.parent / cache_name

    if cache_path.exists():
        if os.path.getmtime(str(cache_path)) >= os.path.getmtime(str(db_path)):
            try:
                return json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                pass  # fall through to recompute

    # Full parse path (expensive, ~500MB-1GB peak for a 40k-trial file)
    try:
        with db_path.open("r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception:
        return {}

    buckets: dict = defaultdict(lambda: {"count": 0,
                                         "modalities": Counter(),
                                         "sponsors":   Counter(),
                                         "phases":     Counter()})
    for t in data.get("trials", []):
        if not t.get("is_drug_trial"):
            continue
        ta = t.get("therapeutic_area") or "Unassigned"
        if ta in EXCLUDE_TAS:
            continue
        b = buckets[ta]
        b["count"] += 1
        if t.get("modality"):
            b["modalities"][t["modality"]] += 1
        sp = (t.get("sponsor_name") or "").strip()
        if sp:
            b["sponsors"][sp] += 1
        ph = (t.get("phase") or "").upper()
        if ph:
            b["phases"][ph] += 1

    # Drop raw trials ref so the dict we keep is small
    del data

    out: dict = {}
    for ta, b in buckets.items():
        out[ta] = {
            "count":      b["count"],
            "modalities": dict(b["modalities"].most_common(5)),
            "sponsors":   dict(b["sponsors"].most_common(5)),
            "phases":     dict(b["phases"].most_common()),
        }

    try:
        cache_path.write_text(
            json.dumps(out, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass

    return out


def _growth_rate(series: list[int]) -> tuple[float | None, str]:
    non_zero = [v for v in series if v > 0]
    if len(non_zero) < 2:
        return None, "stable"
    first, last = non_zero[0], series[-1]
    if first == 0:
        return None, "growing" if last > 0 else "stable"
    growth = (last - first) / first * 100
    if growth > 10:    trend = "growing"
    elif growth < -10: trend = "declining"
    else:              trend = "stable"
    return round(growth, 1), trend


def sq3_ta_trajectory(master_db_dir: str) -> dict:
    db_dir = Path(master_db_dir)
    files = sorted(db_dir.glob("master_DB_*.json"),
                   key=lambda f: _sort_period(_period_from_filename(f.name)))
    if not files:
        return {"available": False, "reason": "no master DB files found"}

    periods = []
    per_period_counts: dict = {}
    # Iterate one file at a time; the cache path makes this cheap after the
    # first successful build.  The returned dict per period is already tiny
    # (just counts + top-N rollups), so we can keep them all resident.
    for f in files:
        p = _period_from_filename(f.name)
        periods.append(p)
        per_period_counts[p] = _compute_one_period(f)

    current_period = periods[-1]
    current = per_period_counts.get(current_period, {})

    all_tas: set = set()
    for snap in per_period_counts.values():
        all_tas.update(snap.keys())

    tas_rows = []
    for ta in sorted(all_tas):
        series = [per_period_counts[p].get(ta, {}).get("count", 0)
                  for p in periods]
        growth, trend = _growth_rate(series)

        yoy_p = _yoy_period(current_period)
        yoy_count = (per_period_counts.get(yoy_p, {})
                     .get(ta, {}).get("count", 0) if yoy_p else 0)
        cur_count = series[-1]
        yoy_delta = cur_count - yoy_count
        yoy_pct = (round((yoy_delta / yoy_count) * 100, 1)
                   if yoy_count > 0 else None)

        cur = current.get(ta, {})
        top_modalities = [{"name": m, "count": n}
                          for m, n in (cur.get("modalities") or {}).items()]
        top_sponsors   = [{"name": s, "count": n}
                          for s, n in (cur.get("sponsors") or {}).items()]
        phase_mix = dict(cur.get("phases") or {})

        tas_rows.append({
            "name":               ta,
            "history":            [{"period": p, "count": v}
                                   for p, v in zip(periods, series)],
            "current_count":      cur_count,
            "peak_count":         max(series) if series else 0,
            "total_growth_pct":   growth,
            "trend":              trend,
            "yoy_delta":          yoy_delta,
            "yoy_pct":            yoy_pct,
            "top_modalities":     top_modalities,
            "top_sponsors":       top_sponsors,
            "phase_mix":          phase_mix,
        })

    tas_rows.sort(key=lambda r: r["current_count"], reverse=True)
    top_tas  = tas_rows[:TOP_N_TAS]
    other_ta = tas_rows[TOP_N_TAS:]

    qualified = [r for r in tas_rows
                 if r["current_count"] >= 5
                 and r["total_growth_pct"] is not None]
    growing   = sorted(qualified,
                       key=lambda r: r["total_growth_pct"], reverse=True)[:5]
    declining = sorted(qualified,
                       key=lambda r: r["total_growth_pct"])[:5]

    period_totals = {
        p: sum(per_period_counts[p].get(ta, {}).get("count", 0)
               for ta in all_tas)
        for p in periods
    }

    return {
        "available":        True,
        "periods":          periods,
        "current_period":   current_period,
        "tas":              top_tas,
        "other_count":      sum(r["current_count"] for r in other_ta),
        "other_ta_count":   len(other_ta),
        "period_totals":    period_totals,
        "movers_growing":   growing,
        "movers_declining": declining,
        "meta": {
            "periods_loaded": len(periods),
            "unique_tas":     len(all_tas),
            "excluded_tas":   sorted(EXCLUDE_TAS),
        },
    }
