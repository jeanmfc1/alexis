"""
analytics/bd_sq2.py
────────────────────
BD / sq2 — Top 25 Sponsors and What They Run

Business question:
    "Who are the top 25 sponsors and what do they run?"

Source:
    Master DB trials[] (full active universe).
    Requires is_drug_trial=True and sponsor_class=INDUSTRY.

Returns:
    dict with:
        top_sponsors      list  — 25 entries ranked by total_trials desc
        modality_leaders  dict  — per modality: top 3 sponsors
        ta_leaders        dict  — per TA: dominant sponsor + share % +
                                  phase distribution of that sponsor's
                                  trials in the TA
        meta              dict  — master DB provenance info

Sidecar cache:
    On first compute, writes sq2_cache_YYYY_QN.json next to the master DB
    file. Subsequent calls load from cache if the cache mtime >= DB mtime.
"""

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from analytics.shared import modality_weight


def sq2_top_sponsors(master_db_path: str) -> dict:
    """
    Compute top 25 industry drug trial sponsors and their profiles.

    Args:
        master_db_path: absolute path to master_DB_YYYY_QN.json

    Returns:
        dict with keys: available, top_sponsors, modality_leaders,
        ta_leaders, meta
    """
    db_path = Path(master_db_path)

    # ── Sidecar cache ─────────────────────────────────────────────
    cache_name = db_path.name.replace("master_DB_", "sq2_cache_")
    cache_path = db_path.parent / cache_name

    if cache_path.exists():
        if os.path.getmtime(str(cache_path)) >= os.path.getmtime(str(db_path)):
            return json.loads(cache_path.read_text(encoding="utf-8"))

    # ── Load full master DB ───────────────────────────────────────
    with db_path.open("r", encoding="utf-8", errors="replace") as f:
        raw = json.load(f)

    trials = raw.get("trials", [])
    meta = raw.get("metadata", {})

    # ── Filter: industry drug trials only ─────────────────────────
    industry_drug = [
        t for t in trials
        if t.get("is_drug_trial")
        and (t.get("sponsor_class") or "").upper() == "INDUSTRY"
    ]

    # ── Group by sponsor ──────────────────────────────────────────
    by_sponsor: dict[str, list] = defaultdict(list)
    for t in industry_drug:
        name = t.get("sponsor_name") or "Unknown Sponsor"
        by_sponsor[name].append(t)

    # ── Build per-sponsor profile ─────────────────────────────────
    sponsor_rows = []
    for sponsor_name, sponsor_trials in by_sponsor.items():
        total = len(sponsor_trials)

        mod_counts = Counter(
            t.get("modality") or "Unknown" for t in sponsor_trials
        )
        ta_counts = Counter(
            t.get("therapeutic_area") or "Unknown" for t in sponsor_trials
        )
        phase_counts = Counter(
            t.get("phase") or "NA" for t in sponsor_trials
        )

        top_modality = mod_counts.most_common(1)[0][0] if mod_counts else "Unknown"
        top_ta = ta_counts.most_common(1)[0][0] if ta_counts else "Unknown"

        # Complexity score — sum of modality weights across portfolio
        complexity_score = sum(
            modality_weight(t.get("modality")) for t in sponsor_trials
        )

        sponsor_rows.append({
            "sponsor_name":       sponsor_name,
            "total_trials":       total,
            "modality_breakdown": dict(mod_counts.most_common()),
            "ta_breakdown":       dict(ta_counts.most_common()),
            "phase_breakdown":    dict(phase_counts),
            "top_modality":       top_modality,
            "top_ta":             top_ta,
            "complexity_score":   round(complexity_score, 1),
        })

    # Sort by total_trials descending, take top 25
    sponsor_rows.sort(key=lambda r: r["total_trials"], reverse=True)
    top_sponsors = sponsor_rows[:25]

    # ── Modality leaders ──────────────────────────────────────────
    # Per modality, who are the top 3 sponsors?
    mod_sponsor: dict[str, Counter] = defaultdict(Counter)
    for t in industry_drug:
        mod = t.get("modality") or "Unknown"
        name = t.get("sponsor_name") or "Unknown"
        mod_sponsor[mod][name] += 1

    modality_leaders = {}
    for mod, counter in sorted(
        mod_sponsor.items(), key=lambda x: sum(x[1].values()), reverse=True
    ):
        top3 = counter.most_common(3)
        modality_leaders[mod] = [
            {"sponsor": name, "count": cnt} for name, cnt in top3
        ]

    # ── TA leaders ────────────────────────────────────────────────
    # Per TA, who is the dominant sponsor + their phase distribution
    # within that TA (not the entire TA's phase distribution).
    ta_sponsor: dict[str, Counter] = defaultdict(Counter)
    ta_totals: Counter = Counter()
    # Track phase per (TA, sponsor) for the donut charts
    ta_sponsor_phase: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for t in industry_drug:
        ta = t.get("therapeutic_area") or "Unknown"
        name = t.get("sponsor_name") or "Unknown"
        phase = t.get("phase") or "NA"
        ta_sponsor[ta][name] += 1
        ta_totals[ta] += 1
        ta_sponsor_phase[(ta, name)][phase] += 1

    ta_leaders = {}
    for ta, counter in sorted(
        ta_sponsor.items(), key=lambda x: ta_totals[x[0]], reverse=True
    ):
        if any(x in ta.lower() for x in ("unassigned", "non-disease")):
            continue
        top1_name, top1_count = counter.most_common(1)[0]
        total_in_ta = ta_totals[ta]
        share_pct = round(100 * top1_count / total_in_ta, 1) if total_in_ta else 0
        # Phase breakdown for just the dominant sponsor in this TA
        sponsor_phases = ta_sponsor_phase[(ta, top1_name)]
        ta_leaders[ta] = {
            "sponsor":    top1_name,
            "count":      top1_count,
            "total":      total_in_ta,
            "share_pct":  share_pct,
            "phase_dist": dict(sponsor_phases.most_common()),
        }

    # ── Assemble result ───────────────────────────────────────────
    result = {
        "available":        True,
        "top_sponsors":     top_sponsors,
        "modality_leaders": modality_leaders,
        "ta_leaders":       ta_leaders,
        "meta": {
            "master_db_file":      db_path.name,
            "total_industry_drug": len(industry_drug),
            "unique_sponsors":     len(by_sponsor),
            "export_date":         meta.get("export_date"),
        },
    }

    # ── Write sidecar cache ───────────────────────────────────────
    cache_path.write_text(
        json.dumps(result, indent=2, default=str),
        encoding="utf-8",
    )

    return result
