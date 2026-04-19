"""
analytics/mk_wq2.py
--------------------
Marketing / wq5 -- Modality & TA Over/Under Index

Business question:
    "Which modalities and therapeutic areas are trending this week
     vs the 4-week moving average -- anything we should write about?"

Source:
    enriched_trials[] (for this-week counts; filter update_type=='new')
    prior_weeks[]    from pick_prior_snapshots() for the baseline
    snap_summary + master_db_summary as fallbacks when no prior weeks

Index:
    index = this_week_count / max(baseline_avg, 0.5)
    z     = (this_week - baseline_avg) / (baseline_std or 1)

    hot:     index >= 1.75 AND this_week >= 5
    rising:  1.25 <= index < 1.75
    cold:    index <= 0.60 AND baseline_avg >= 5
    steady:  else
    new:     baseline_avg == 0 AND this_week > 0 (index=None, z=None)
"""

from __future__ import annotations
from collections import Counter, defaultdict
from statistics import mean, stdev

HOT_THRESHOLD   = 1.75
RISING_MIN      = 1.25
COLD_THRESHOLD  = 0.60
COLD_MIN_BASE   = 5
HOT_MIN_COUNT   = 5
BASELINE_FLOOR  = 0.5
TOP_N           = 12


def _new_drug(enriched_trials):
    return [
        t for t in enriched_trials
        if t.get("update_type") == "new" and t.get("is_drug_trial")
    ]


def _classify(this_week: int, base_avg: float) -> str:
    if base_avg == 0:
        return "new" if this_week > 0 else "steady"
    idx = this_week / max(base_avg, BASELINE_FLOOR)
    if idx >= HOT_THRESHOLD and this_week >= HOT_MIN_COUNT:
        return "hot"
    if idx >= RISING_MIN:
        return "rising"
    if idx <= COLD_THRESHOLD and base_avg >= COLD_MIN_BASE:
        return "cold"
    return "steady"


def _row(name: str, this_week: int, base_values: list, samples: list) -> dict:
    base_avg = mean(base_values) if base_values else 0.0
    base_std = stdev(base_values) if len(base_values) >= 2 else 0.0
    if base_avg > 0:
        index = round(this_week / max(base_avg, BASELINE_FLOOR), 2)
    else:
        index = None
    z = round((this_week - base_avg) / max(base_std, 1.0), 2) if base_std > 0 else None
    trend = _classify(this_week, base_avg)
    return {
        "name":        name,
        "this_week":   this_week,
        "baseline":    round(base_avg, 2),
        "baseline_std": round(base_std, 2),
        "index":       index,
        "z":           z,
        "trend":       trend,
        "samples":     samples[:5],
    }


def wq5_modality_index_chart(snap_summary: dict | None = None,
                             master_db_summary: dict | None = None,
                             enriched_trials: list | None = None,
                             prior_weeks: list | None = None) -> dict:
    """
    Keeps the historical signature (snap_summary, master_db_summary) so that
    generate_weekly_viz.py does not need to change if it only passes those
    two.  But when the caller provides enriched_trials and prior_weeks the
    function computes the over/under index properly; otherwise it falls
    back to {available: False}.
    """
    if not enriched_trials:
        return {"available": False, "reason": "no enriched_trials passed"}

    new_drug = _new_drug(enriched_trials)
    if not new_drug:
        return {"available": False, "reason": "no new drug trials this week"}

    # This-week counts
    mod_this = Counter(); ta_this = Counter()
    mod_samples = defaultdict(list); ta_samples = defaultdict(list)
    for t in new_drug:
        mod = t.get("modality") or "Unknown"
        ta  = t.get("therapeutic_area") or "Unassigned"
        mod_this[mod] += 1; ta_this[ta] += 1
        sample = {
            "nct_id":   t.get("nct_id"),
            "title":    (t.get("title") or "")[:220],
            "sponsor":  t.get("sponsor_name"),
            "phase":    t.get("phase"),
            "modality": t.get("modality"),
            "ta":       t.get("therapeutic_area"),
            "source_url": (
                f"https://clinicaltrials.gov/study/{t.get('nct_id')}"
                if (t.get("nct_id") or "").startswith("NCT")
                else t.get("source_url")
            ),
        }
        if len(mod_samples[mod]) < 5: mod_samples[mod].append(sample)
        if len(ta_samples[ta])  < 5: ta_samples[ta].append(sample)

    # Baseline from prior_weeks. Only ENRICHED entries have genuine weekly
    # new-trial counts; snapshot_summary entries carry CUMULATIVE counts and
    # would make every index look cold. Filter them out.
    mod_baseline = defaultdict(list); ta_baseline = defaultdict(list)
    priors_used = 0
    priors_skipped_summary = 0
    if prior_weeks:
        for pw in prior_weeks:
            if pw.get("source") != "enriched":
                priors_skipped_summary += 1
                continue
            pw_ta_mod = pw.get("ta_mod") or {}
            mod_sum = Counter(); ta_sum = Counter()
            for ta, mods in pw_ta_mod.items():
                ta_sum[ta] += sum(mods.values())
                for mod, n in mods.items():
                    mod_sum[mod] += n
            for m, n in mod_sum.items(): mod_baseline[m].append(n)
            for ta, n in ta_sum.items(): ta_baseline[ta].append(n)
            priors_used += 1

    if priors_used == 0:
        return {
            "available": False,
            "reason": (
                f"Need >=1 prior week with an enriched changelog file "
                f"to compute a weekly baseline. Skipped "
                f"{priors_skipped_summary} snapshot-summary priors "
                f"(cumulative counts, not weekly). Run "
                f"analytics/run_update_categorizer.py on past weeks first."
            ),
        }

    # All labels
    all_mods = set(mod_this) | set(mod_baseline)
    all_tas  = set(ta_this)  | set(ta_baseline)

    mods_rows = [_row(m, mod_this.get(m, 0), mod_baseline.get(m, []),
                      mod_samples.get(m, [])) for m in all_mods]
    tas_rows  = [_row(t, ta_this.get(t, 0),  ta_baseline.get(t, []),
                      ta_samples.get(t, []))  for t in all_tas]

    # Sort: hot first, rising next, steady, new, cold; tie on index desc
    rank = {"hot": 0, "rising": 1, "new": 2, "steady": 3, "cold": 4}
    keyf = lambda r: (rank.get(r["trend"], 9), -(r["index"] or 0), -r["this_week"])
    mods_rows.sort(key=keyf)
    tas_rows.sort(key=keyf)

    return {
        "available":       True,
        "modalities":      mods_rows[:TOP_N],
        "tas":             tas_rows[:TOP_N],
        "meta": {
            "prior_weeks_used":      priors_used,
            "priors_skipped_summary": priors_skipped_summary,
            "thresholds": {
                "hot":    HOT_THRESHOLD,
                "rising": RISING_MIN,
                "cold":   COLD_THRESHOLD,
                "hot_min_count": HOT_MIN_COUNT,
                "cold_min_base": COLD_MIN_BASE,
                "baseline_floor": BASELINE_FLOOR,
            },
            "total_new": sum(mod_this.values()),
        },
    }
