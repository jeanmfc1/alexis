"""
analytics/bd_wq1.py
────────────────────
BD / wq1 — Sponsor Action Table with Priority Score

Business question:
    "Which sponsors filed new trials this week that we should contact?"

Source:
    enriched file trials[]
    Requires update_type == "new" and sponsor_class == "INDUSTRY".
    The snapshot alone cannot answer this — it contains ALL updated trials
    (new + existing). Only the enriched file carries update_type.

Returns:
    list of sponsor dicts, sorted by priority_score descending.
    Each entry is one row in the Action Table card.

Output fields per sponsor:
    sponsor_name    str   — display name
    new_trial_count int   — new drug trials filed this week
    modalities      list  — unique modality labels, most-common first
    top_phase       str   — most common phase across their trials
    priority_score  float — Σ (modality_weight × phase_weight) per trial
    priority_label  str   — "HIGH" / "MED" / "LOW"
    trials          list  — [{nct_id, title, modality, phase, overall_status,
                             modality_source, therapeutic_area, ta_evidence,
                             first_posted_date}] for row expand

Priority label thresholds
    (a sponsor with 3 gene-therapy Phase-1 trials scores 3 × 3.0 × 4 = 36):
    HIGH  score >= 12
    MED   score >= 4
    LOW   score <  4
"""

from collections import defaultdict

from analytics.shared import modality_weight, phase_weight


def wq1_sponsor_action_table(enriched_trials: list) -> list:
    """
    Build the sponsor action table from enriched trial records.

    Args:
        enriched_trials: trials list from enriched_*.json (drug_only=True)

    Returns:
        list of sponsor row dicts, sorted by priority_score descending
    """
    # 1. Filter: new registrations, INDUSTRY, drug trials only
    industry_drug = [
        t for t in enriched_trials
        if t.get("update_type") == "new"
        and (t.get("sponsor_class") or "").upper() == "INDUSTRY"
        and t.get("is_drug_trial", True)   # enriched is drug_only; guard kept
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
        modalities = [
            m for m, _ in sorted(mod_counts.items(), key=lambda x: x[1], reverse=True)
        ]

        # Top phase — most common phase across their trials
        phase_counts: dict[str, int] = defaultdict(int)
        for t in sponsor_trials:
            phase_counts[t.get("phase") or "Unknown"] += 1
        top_phase = max(phase_counts, key=phase_counts.__getitem__)

        # Priority score — sum of modality_weight × phase_weight per trial
        score = sum(
            modality_weight(t.get("modality")) * phase_weight(t.get("phase"))
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
        trial_rows = []
        for t in sponsor_trials:
            mod_src = t.get("modality_source") or "intervention_type"

            trial_rows.append({
                "nct_id":            t.get("nct_id"),
                "title":             t.get("title"),
                "modality":          t.get("modality"),
                "phase":             t.get("phase"),
                "overall_status":    t.get("overall_status"),
                "modality_source":   mod_src,
                "therapeutic_area":  t.get("therapeutic_area"),
                "ta_evidence":       t.get("therapeutic_areas_detected"),
                "first_posted_date": t.get("first_posted_date"),
            })

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
