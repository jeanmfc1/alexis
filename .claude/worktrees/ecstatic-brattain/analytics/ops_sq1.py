"""
analytics/ops_sq1.py
────────────────────
Operations / sq1 — Workload Forecast by Complexity Tier

Business question:
    "What is the total workload forecast by complexity tier?"

Source:
    Master DB trials[] (full active universe).
    Requires is_drug_trial=True.

Scoring formula:
    score = modality_weight x phase_complexity x enrollment_scale

    modality_weight   — gene/cell=3, mAb=2, vaccine=1.5, SM=1  (shared.py)
    phase_complexity  — Phase3=4, Phase2=2, Phase1=1            (shared.py)
    enrollment_scale  — >2000=2.5, 501-2000=2.0, 201-500=1.5,
                        51-200=1.0, <=50=0.5                    (shared.py)

Tier cutoffs:
    Critical >= 10.0  (e.g. Phase 3 mAb with 500+ patients)
    High     >= 6.0   (e.g. Phase 3 SM with 300+ patients)
    Medium   >= 3.0   (e.g. Phase 2 SM with 200+ patients)
    Low      <  3.0   (e.g. Phase 1 anything small)

Returns:
    dict with:
        tiers                list  — 4 entries (Critical/High/Medium/Low), each with
                                     volume, workload, platform split, top modalities,
                                     top phases, top TAs
        grand_total_volume   int   — total drug trials scored
        grand_total_workload float — sum of all scores
        meta                 dict  — master DB provenance info

Sidecar cache:
    On first compute, writes ops_sq1_cache_YYYY_QN.json next to the master DB.
    Subsequent calls load from cache if cache mtime >= DB mtime.
"""

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from analytics.shared import (
    modality_weight,
    phase_complexity,
    enrollment_scale,
    assay_platform,
)


# ── Tier definitions ──────────────────────────────────────────────────────
# Ordered highest-first.  _assign_tier walks down and returns the first match.
# score = modality_weight x phase_complexity x enrollment_scale
# Range: 0.5 (early-phase SM, <=50 pts) to 30.0 (Phase 3 gene therapy, >2000 pts)

TIERS = [
    ("Critical", 10.0),
    ("High",      6.0),
    ("Medium",    3.0),
    ("Low",       0.0),
]


def _assign_tier(score: float) -> str:
    """Return tier name for a given complexity score."""
    for name, threshold in TIERS:
        if score >= threshold:
            return name
    return "Low"


# ── Main function ─────────────────────────────────────────────────────────

def sq10_workload_forecast(master_db_path: str) -> dict:
    """
    Compute workload forecast by complexity tier from the master DB.

    Args:
        master_db_path: absolute path to master_DB_YYYY_QN.json

    Returns:
        dict with keys: available, tiers, grand_total_volume,
        grand_total_workload, meta
    """
    db_path = Path(master_db_path)

    # ── Sidecar cache ─────────────────────────────────────────────
    cache_name = db_path.name.replace("master_DB_", "ops_sq1_cache_")
    cache_path = db_path.parent / cache_name

    if cache_path.exists():
        if os.path.getmtime(str(cache_path)) >= os.path.getmtime(str(db_path)):
            return json.loads(cache_path.read_text(encoding="utf-8"))

    # ── Load full master DB ───────────────────────────────────────
    with db_path.open("r", encoding="utf-8", errors="replace") as f:
        raw = json.load(f)

    trials = raw.get("trials", [])
    meta = raw.get("metadata", {})

    # ── Filter: drug trials only ──────────────────────────────────
    drug_trials = [t for t in trials if t.get("is_drug_trial")]

    if not drug_trials:
        return {"available": False}

    # ── Score each trial and assign to a tier ─────────────────────
    # We store lightweight per-trial info (not the full record) so
    # we can build breakdowns without bloating the JSON payload.

    tier_trials: dict[str, list] = defaultdict(list)

    for t in drug_trials:
        mod_w   = modality_weight(t.get("modality"))
        phase_c = phase_complexity(t.get("phase"))
        enroll  = t.get("enrollment") or 0
        enr_s   = enrollment_scale(enroll)
        score   = mod_w * phase_c * enr_s
        tier    = _assign_tier(score)

        tier_trials[tier].append({
            "score":            score,
            "modality":         t.get("modality") or "Unknown",
            "phase":            t.get("phase") or "NA",
            "therapeutic_area": t.get("therapeutic_area") or "Unknown",
            "platform":         assay_platform(t.get("modality")),
            "enrollment":       enroll,
        })

    # ── Build per-tier summaries ──────────────────────────────────
    tier_rows = []
    grand_volume   = 0
    grand_workload = 0.0

    for tier_name, _ in TIERS:
        bucket   = tier_trials.get(tier_name, [])
        volume   = len(bucket)
        workload = sum(t["score"] for t in bucket)

        # Counts for breakdowns
        mod_counts      = Counter(t["modality"] for t in bucket)
        phase_counts    = Counter(t["phase"] for t in bucket)
        ta_counts       = Counter(t["therapeutic_area"] for t in bucket)
        platform_counts = Counter(t["platform"] for t in bucket)

        grand_volume   += volume
        grand_workload += workload

        tier_rows.append({
            "name":       tier_name,
            "volume":     volume,
            "workload":   round(workload, 1),
            # Percentages filled in below once grand totals are known
            "pct_volume":   0,
            "pct_workload": 0,
            # Platform split (LCMS / LBA / Hybrid)
            "platform_split": {
                p: platform_counts.get(p, 0)
                for p in ["LCMS", "LBA", "Hybrid"]
            },
            # Top breakdowns for drill-down
            "top_modalities": [
                {"name": m, "count": c}
                for m, c in mod_counts.most_common(5)
            ],
            "top_phases": [
                {"name": p, "count": c}
                for p, c in phase_counts.most_common()
            ],
            "top_tas": [
                {"name": ta, "count": c}
                for ta, c in ta_counts.most_common(5)
                if not any(x in ta.lower()
                           for x in ("unassigned", "unknown", "non-disease"))
            ],
        })

    # Fill in percentages now that we know grand totals
    for row in tier_rows:
        if grand_volume > 0:
            row["pct_volume"] = round(100 * row["volume"] / grand_volume, 1)
        if grand_workload > 0:
            row["pct_workload"] = round(100 * row["workload"] / grand_workload, 1)

    # ── Assemble result ───────────────────────────────────────────
    result = {
        "available":            True,
        "tiers":                tier_rows,
        "grand_total_volume":   grand_volume,
        "grand_total_workload": round(grand_workload, 1),
        "meta": {
            "master_db_file":    db_path.name,
            "total_drug_trials": len(drug_trials),
            "export_date":       meta.get("export_date"),
        },
    }

    # ── Write sidecar cache ───────────────────────────────────────
    cache_path.write_text(
        json.dumps(result, indent=2, default=str),
        encoding="utf-8",
    )

    return result
