"""
analytics/sci_sq3.py
--------------------
Scientific / sq9 -- Confidence Dashboard (Approach C)

Business question:
    "How reliable is our classification, and where should we improve?"

Framework (Approach C -- fair, decoupled):
    1. Modality confidence   -- denominator = trials with intervention_meshes
                                (excludes trials where NLM gave no MeSH data)
    2. TA confidence          -- denominator = all drug trials
    3. Data coverage          -- informational: what % had MeSH data at all
    4. Flag breakdown         -- why MeSH failed when it was available
    5. Per-TA drill-down      -- both modality + TA confidence per TA

Reads modality_source and therapeutic_area_source directly from the
master DB (no heuristic re-derivation).

Sidecar cache:
    Writes sci_sq3_cache_YYYY_QN.json next to the master DB.
"""

import json
import os
from collections import Counter, defaultdict
from pathlib import Path


def _modality_confidence(t: dict) -> str | None:
    """Classify modality confidence for a drug trial.

    Returns "high", "medium", or None (excluded -- no MeSH data available).
    """
    if not t.get("intervention_meshes"):
        return None

    src = t.get("modality_source")
    if src == "mesh_tree":
        return "high"
    return "medium"


def _ta_confidence(t: dict) -> str:
    """Classify TA confidence for a drug trial."""
    src = t.get("therapeutic_area_source")
    if src == "mesh_evidence":
        return "high"
    return "low"


def _dominant_flag(trials: list) -> str:
    """Return the most common info_flag across a list of trial dicts."""
    flags: list = []
    for t in trials:
        flags.extend(t.get("info_flags") or [])
    if not flags:
        return "no_mesh_data"
    return Counter(flags).most_common(1)[0][0]


MIN_TA_COUNT = 50
MAX_PRIORITIES = 15


def sq9_confidence_dashboard(master_db_path: str) -> dict:
    """
    Build confidence dashboard payload from the master DB.

    Args:
        master_db_path: absolute path to master_DB_YYYY_QN.json

    Returns:
        dict with keys: available, modality_confidence, ta_confidence,
        data_coverage, flag_breakdown, per_ta, improvement_priorities
    """
    db_path = Path(master_db_path)

    # -- Sidecar cache --
    cache_name = db_path.name.replace("master_DB_", "sci_sq3_cache_")
    cache_path = db_path.parent / cache_name

    if cache_path.exists():
        if os.path.getmtime(str(cache_path)) >= os.path.getmtime(str(db_path)):
            return json.loads(cache_path.read_text(encoding="utf-8"))

    # -- Load full master DB --
    with db_path.open("r", encoding="utf-8", errors="replace") as f:
        raw = json.load(f)

    drug_trials = [t for t in raw.get("trials", []) if t.get("is_drug_trial")]
    total = len(drug_trials)

    if total == 0:
        return {"available": False}

    # Section 1: Modality confidence
    # Denominator: only trials that had intervention_meshes
    mod_with_mesh = [t for t in drug_trials if t.get("intervention_meshes")]
    mod_denom = len(mod_with_mesh)

    mod_tiers = Counter(_modality_confidence(t) for t in drug_trials)
    mod_high   = mod_tiers.get("high", 0)
    mod_medium = mod_tiers.get("medium", 0)

    modality_confidence = {
        "denominator":  mod_denom,
        "high_count":   mod_high,
        "high_pct":     round(mod_high / mod_denom * 100, 1) if mod_denom else 0,
        "medium_count": mod_medium,
        "medium_pct":   round(mod_medium / mod_denom * 100, 1) if mod_denom else 0,
        "score":        round(
            (mod_high * 1.0 + mod_medium * 0.6) / mod_denom * 100, 1
        ) if mod_denom else 0,
    }

    # Section 2: TA confidence
    ta_tiers = Counter(_ta_confidence(t) for t in drug_trials)
    ta_high = ta_tiers.get("high", 0)
    ta_low  = ta_tiers.get("low", 0)

    ta_confidence = {
        "denominator": total,
        "high_count":  ta_high,
        "high_pct":    round(ta_high / total * 100, 1),
        "low_count":   ta_low,
        "low_pct":     round(ta_low / total * 100, 1),
        "score":       round(ta_high / total * 100, 1),
    }

    # Section 3: Data coverage (informational)
    cond_mesh_count = sum(1 for t in drug_trials if t.get("condition_meshes"))

    data_coverage = {
        "total_drug_trials":          total,
        "modality_mesh_available":    mod_denom,
        "modality_mesh_coverage_pct": round(mod_denom / total * 100, 1),
        "ta_mesh_available":          cond_mesh_count,
        "ta_mesh_coverage_pct":       round(cond_mesh_count / total * 100, 1),
    }

    # Section 4: Flag breakdown (why MeSH failed)
    flag_counts = Counter()
    for t in drug_trials:
        flags = t.get("info_flags") or []
        if "mesh_available_but_not_used" in flags:
            for f in flags:
                if f.startswith("mesh_reason:"):
                    flag_counts[f] += 1

    # Section 5: Per-TA drill-down
    ta_groups = defaultdict(list)
    for t in drug_trials:
        ta = t.get("therapeutic_area") or "Unknown"
        ta_groups[ta].append(t)

    per_ta = []
    for ta, ta_trials in ta_groups.items():
        n = len(ta_trials)
        if n < MIN_TA_COUNT:
            continue

        ta_with_mesh = sum(1 for t in ta_trials if t.get("intervention_meshes"))
        ta_mod_high  = sum(
            1 for t in ta_trials if t.get("modality_source") == "mesh_tree"
        )
        ta_ta_high = sum(
            1 for t in ta_trials
            if t.get("therapeutic_area_source") == "mesh_evidence"
        )

        per_ta.append({
            "ta":           ta,
            "total":        n,
            "mod_mesh_pct": round(ta_with_mesh / n * 100, 1),
            "mod_high_pct": round(ta_mod_high / ta_with_mesh * 100, 1) if ta_with_mesh else 0,
            "ta_high_pct":  round(ta_ta_high / n * 100, 1),
        })

    per_ta.sort(key=lambda r: r["ta_high_pct"])

    # Section 6: Improvement priorities
    ta_mod_groups = defaultdict(list)
    for t in drug_trials:
        ta_key  = t.get("therapeutic_area") or "Unknown"
        mod_key = t.get("modality") or "Unknown"
        ta_mod_groups[(ta_key, mod_key)].append(t)

    priorities = []
    for (ta, mod), cell_trials in ta_mod_groups.items():
        low_trials = [
            t for t in cell_trials
            if t.get("modality_source") != "mesh_tree"
            and t.get("therapeutic_area_source") != "mesh_evidence"
        ]
        if not low_trials:
            continue
        cell_n = len(cell_trials)
        low_n  = len(low_trials)
        priorities.append({
            "ta":             ta,
            "modality":       mod,
            "total":          cell_n,
            "low_count":      low_n,
            "pct_low":        round(low_n / cell_n * 100, 1),
            "impact_score":   round(low_n * (cell_n / total) * 100, 2),
            "dominant_issue": _dominant_flag(low_trials),
            "sample_nct_ids": [t.get("nct_id", "") for t in low_trials[:3]],
        })

    priorities.sort(key=lambda r: r["impact_score"], reverse=True)
    priorities = priorities[:MAX_PRIORITIES]

    result = {
        "available":              True,
        "modality_confidence":    modality_confidence,
        "ta_confidence":          ta_confidence,
        "data_coverage":          data_coverage,
        "flag_breakdown":         dict(flag_counts),
        "per_ta":                 per_ta,
        "improvement_priorities": priorities,
    }

    # -- Write sidecar cache --
    try:
        cache_path.write_text(
            json.dumps(result, separators=(",", ":"), default=str),
            encoding="utf-8",
        )
    except Exception:
        pass

    return result
