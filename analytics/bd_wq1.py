"""
analytics/bd_wq1.py
────────────────────
BD / wq1 — Sponsor Action Table with Priority Score

Business question:
    "Which sponsors filed new trials this week that we should contact?"

Source:
    enriched file trials[]
    Requires update_type == "new" (retrospective completions already
    excluded upstream as update_type == "new_inactive").  Accepts ALL
    sponsor classes (INDUSTRY, NIH, ACADEMIC, OTHER, UNKNOWN); the UI
    surfaces an INDUSTRY-only badge count so BD can focus if needed.

Returns:
    dict: { rows, counts, meta }
        rows:   list of sponsor dicts sorted by priority desc
        counts: { total, industry, nih, academic, other }
        meta:   { industry_trial_count, total_trial_count }

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
    # 1. Filter: new registrations, drug trials only (all sponsor classes)
    new_drug = [
        t for t in enriched_trials
        if t.get("update_type") == "new"
        and t.get("is_drug_trial", True)   # enriched is drug_only; guard kept
    ]

    # 2. Group by sponsor_name
    by_sponsor: dict[str, list] = defaultdict(list)
    for t in new_drug:
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
            # Derive modality_source from info_flags if not set
            # (backward compat for data generated before the classifier fix)
            mod_src = t.get("modality_source")
            if not mod_src:
                flags = t.get("info_flags") or []
                if "base_reason:no_mesh" in flags:
                    mod_src = "intervention_type"
                elif "mesh_available_but_not_used" in flags:
                    mod_src = "text"
                elif t.get("intervention_meshes"):
                    mod_src = "mesh_tree"
                else:
                    mod_src = "intervention_type"

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

        # Sponsor class (most common across this sponsor's new trials)
        cls_counts: dict[str, int] = defaultdict(int)
        for t in sponsor_trials:
            cls_counts[(t.get("sponsor_class") or "UNKNOWN").upper()] += 1
        sponsor_class = max(cls_counts, key=cls_counts.__getitem__)

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

    # 4. Sort by priority_score descending (highest urgency first)
    rows.sort(key=lambda r: r["priority_score"], reverse=True)

    # 5. Aggregate counts (sponsor-level + trial-level) for the UI header
    sponsor_class_counts: dict[str, int] = defaultdict(int)
    trial_class_counts:   dict[str, int] = defaultdict(int)
    for r in rows:
        sponsor_class_counts[r["sponsor_class"]] += 1
        trial_class_counts[r["sponsor_class"]]   += r["new_trial_count"]

    return {
        "rows":   rows,
        "counts": {
            "sponsors":         len(rows),
            "trials":           sum(r["new_trial_count"] for r in rows),
            "by_sponsor_class": dict(sponsor_class_counts),
            "by_trial_class":   dict(trial_class_counts),
            "industry_sponsors": sponsor_class_counts.get("INDUSTRY", 0),
            "industry_trials":   trial_class_counts.get("INDUSTRY", 0),
        },
    }
