"""
analytics/bd_cw1.py
────────────────────
BD / cw1 (ChiCTR) — Chinese Sponsor Action Table

Business question:
    "Which Chinese sponsors filed new drug trials this week that we should track?"

Source:
    enriched ChiCTR snapshot trials[] with update_type == "new".
    The diff_chictr_snapshots.py pipeline adds update_type.

Provenance note:
    ChiCTR sponsor_class is inferred from funding_source + primary_sponsor
    text (~70% accurate). Both drug-trial status and modality come from
    intl_drug_classifier_v2 (ML). Treat results as directional, not audit-grade.

Returns:
    list of sponsor row dicts, sorted by new_trial_count descending.
"""

from collections import defaultdict

from analytics.shared import modality_weight, phase_weight


def cw1_china_sponsor_action_table(enriched_trials: list) -> list:
    """Build the Chinese-sponsor action table from enriched ChiCTR trials.

    Args:
        enriched_trials: trials list from chictr_enriched_*.json

    Returns:
        list of sponsor row dicts, sorted by priority_score descending
    """
    # 1. Filter: new registrations, drug trials only. No industry filter yet —
    #    most ChiCTR sponsors are Chinese universities/hospitals; we show all
    #    and let the UI filter chip handle the industry subset.
    new_drug = [
        t for t in enriched_trials
        if t.get("update_type") == "new" and t.get("is_drug_trial")
    ]

    # 2. Group by sponsor_name
    by_sponsor: dict[str, list] = defaultdict(list)
    for t in new_drug:
        name = (t.get("sponsor_name") or "Unknown Sponsor").strip()
        by_sponsor[name].append(t)

    rows = []
    for sponsor_name, sponsor_trials in by_sponsor.items():
        mod_counts: dict[str, int] = defaultdict(int)
        for t in sponsor_trials:
            mod_counts[t.get("modality") or "Unknown"] += 1
        modalities = [m for m, _ in sorted(mod_counts.items(),
                                           key=lambda x: x[1], reverse=True)]

        phase_counts: dict[str, int] = defaultdict(int)
        for t in sponsor_trials:
            phase_counts[t.get("phase") or "Unknown"] += 1
        top_phase = max(phase_counts, key=phase_counts.__getitem__)

        score = sum(
            modality_weight(t.get("modality")) * phase_weight(t.get("phase"))
            for t in sponsor_trials
        )
        if score >= 12:
            priority_label = "HIGH"
        elif score >= 4:
            priority_label = "MED"
        else:
            priority_label = "LOW"

        sponsor_class = (sponsor_trials[0].get("sponsor_class") or "UNKNOWN").upper()

        trial_rows = [
            {
                "nct_id":            t.get("nct_id"),
                "title":             t.get("title"),
                "modality":          t.get("modality"),
                "phase":             t.get("phase"),
                "therapeutic_area":  t.get("therapeutic_area"),
                "modality_source":   t.get("modality_source") or "intl_classifier",
                "source_url":        t.get("source_url"),
                "first_posted_date": t.get("first_posted_date"),
            }
            for t in sponsor_trials
        ]

        rows.append({
            "sponsor_name":    sponsor_name,
            "sponsor_class":   sponsor_class,
            "new_trial_count": len(sponsor_trials),
            "modalities":      modalities,
            "top_phase":       top_phase,
            "priority_score":  round(score, 1),
            "priority_label":  priority_label,
            "trials":          trial_rows,
        })

    rows.sort(key=lambda r: (r["priority_score"], r["new_trial_count"]), reverse=True)
    return rows
