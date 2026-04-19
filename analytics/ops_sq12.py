"""
analytics/ops_sq12.py
---------------------
Ops / sq12 -- Phase Transition Pipeline

Business question:
    "What phase transitions are coming in the next 1/2/3 years,
     based on active trials' projected completion dates?"

Source:
    Active-universe master DB (current snapshot only).

For each active drug trial with a parseable primary_completion_date (or
fallback completion_date):
    year_offset = floor((completion_date - today) / 365)
    predicted_next_phase = PHASE_NEXT.get(current_phase)
    bucket into (year_offset, current_phase, next_phase)

Returns dict consumed by viz/ops_sq12.jsx (Sankey flow renderer).
"""

from __future__ import annotations
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

PHASE_NEXT = {
    "EARLY_PHASE1": "PHASE1",
    "PHASE1":       "PHASE2",
    "PHASE1/PHASE2": "PHASE2",
    "PHASE2":       "PHASE3",
    "PHASE2/PHASE3": "PHASE3",
    "PHASE3":       "PHASE4",
    "PHASE4":       "MARKETED",
    "NA":           None,
    "":             None,
}
ACTIVE_STATUSES = {"RECRUITING", "NOT_YET_RECRUITING",
                   "ENROLLING_BY_INVITATION", "ACTIVE_NOT_RECRUITING"}
HORIZON_YEARS = 3   # 0, +1, +2, +3
STALE_WINDOW_DAYS = 0   # past completion_date + still active = stale


def _parse_date(s: str | None) -> date | None:
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _phase_norm(p: str | None) -> str:
    if not p:
        return ""
    return str(p).upper().replace(" ", "_").replace("/", "/")


def sq12_transition_pipeline(master_db_path: str) -> dict:
    p = Path(master_db_path)
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception as exc:
        return {"available": False, "reason": f"could not read master DB: {exc}"}

    trials = data.get("trials", [])
    today = date.today()

    # Per-window tallies
    windows: dict[int, dict] = {
        i: {"count": 0,
            "by_phase": Counter(),
            "by_modality": Counter(),
            "by_ta": Counter()}
        for i in range(HORIZON_YEARS + 1)
    }
    transitions: dict = defaultdict(lambda: {
        "count": 0,
        "modalities": Counter(),
        "examples": []
    })
    flagged: list = []

    total_active_drug = 0
    with_completion = 0
    stale_count = 0

    for t in trials:
        if not t.get("is_drug_trial"):
            continue
        status = (t.get("overall_status") or "").upper()
        if status not in ACTIVE_STATUSES:
            continue
        total_active_drug += 1

        raw = t.get("primary_completion_date") or t.get("completion_date")
        cd = _parse_date(raw)
        if not cd:
            continue
        with_completion += 1

        phase_cur = _phase_norm(t.get("phase"))
        phase_next = PHASE_NEXT.get(phase_cur)
        offset_days = (cd - today).days
        year_offset = offset_days // 365

        if cd < today:
            stale_count += 1
            # keep in flagged list as "delayed"
            flagged.append({
                "nct_id":   t.get("nct_id"),
                "title":    (t.get("title") or "")[:200],
                "sponsor":  t.get("sponsor_name"),
                "phase":    phase_cur,
                "projected_completion": raw,
                "reason":   "stale: past completion_date but still active",
                "days_overdue": -offset_days,
            })
            continue

        if year_offset > HORIZON_YEARS:
            continue

        win = windows.setdefault(year_offset, {"count": 0,
            "by_phase": Counter(), "by_modality": Counter(),
            "by_ta": Counter()})
        win["count"] += 1
        win["by_phase"][phase_cur or "-"] += 1
        if t.get("modality"):
            win["by_modality"][t["modality"]] += 1
        if t.get("therapeutic_area"):
            win["by_ta"][t["therapeutic_area"]] += 1

        if phase_next:
            key = (phase_cur, phase_next, year_offset)
            rec = transitions[key]
            rec["count"] += 1
            if t.get("modality"):
                rec["modalities"][t["modality"]] += 1
            if len(rec["examples"]) < 8:
                rec["examples"].append({
                    "nct_id":  t.get("nct_id"),
                    "title":   (t.get("title") or "")[:200],
                    "sponsor": t.get("sponsor_name"),
                    "modality": t.get("modality"),
                    "ta":      t.get("therapeutic_area"),
                    "projected_completion": raw,
                    "source_url": (
                        f"https://clinicaltrials.gov/study/{t.get('nct_id')}"
                        if (t.get("nct_id") or "").startswith("NCT")
                        else None
                    ),
                })

        # Flag if within 90 days
        if 0 <= offset_days <= 90:
            flagged.append({
                "nct_id":   t.get("nct_id"),
                "title":    (t.get("title") or "")[:200],
                "sponsor":  t.get("sponsor_name"),
                "phase":    phase_cur,
                "projected_completion": raw,
                "reason":   "completing within 90 days",
                "days_out": offset_days,
            })

    # Window labels and arrays
    window_list = []
    for i in range(HORIZON_YEARS + 1):
        w = windows.get(i, {"count": 0, "by_phase": Counter(),
                            "by_modality": Counter(), "by_ta": Counter()})
        label = ("completing in ≤12 mo" if i == 0
                 else f"completing in {i}–{i+1} y")
        window_list.append({
            "year_offset":   i,
            "label":         label,
            "count":         w["count"],
            "by_phase":      dict(w["by_phase"].most_common()),
            "by_modality":   dict(w["by_modality"].most_common(8)),
            "by_ta":         dict(w["by_ta"].most_common(8)),
        })

    trans_list = []
    for (phase_from, phase_to, yoff), rec in transitions.items():
        trans_list.append({
            "from_phase":  phase_from,
            "to_phase":    phase_to,
            "year_offset": yoff,
            "count":       rec["count"],
            "modalities":  dict(rec["modalities"].most_common(5)),
            "examples":    rec["examples"],
        })
    trans_list.sort(key=lambda r: -r["count"])

    # Order flagged: stale first (by days_overdue desc), then soon (days_out asc)
    flagged.sort(key=lambda r: (
        0 if r["reason"].startswith("stale") else 1,
        -r.get("days_overdue", 0),
        r.get("days_out", 0),
    ))

    return {
        "available":     True,
        "forecast_anchor": today.isoformat(),
        "horizon_years": HORIZON_YEARS,
        "windows":       window_list,
        "transitions":   trans_list,
        "flagged":       flagged[:100],
        "meta": {
            "active_trials":           total_active_drug,
            "trials_with_completion":  with_completion,
            "completion_coverage_pct": (
                round((with_completion / total_active_drug) * 100, 1)
                if total_active_drug else 0.0
            ),
            "stale_count":             stale_count,
        },
    }
