"""
analytics/mk_wq1.py
────────────────────
Marketing / wq1 — Social Stat Cards

Business question:
    "What's the headline stat for this week's social/newsletter content?"

Source:
    snapshot summary{} (pre-computed by weekly_pulse_clinical_v2.py)
    enriched_counts dict for the new vs. existing split on card 1

Returns:
    list of exactly 4 card dicts — one per social stat.

Card schema:
    id      str  — "mk_wq1_c1" … "mk_wq1_c4"
    title   str  — headline label
    value   str  — big display number or name
    sub     str  — supporting line
    detail  list — [{label, value, pct?}] for breakdown rows
    note    str  — small footnote (source / caveat)

Cards:
    1. Drug Trials This Window  → drug_info_overview.drug_trials_total
                                  + new vs existing split from enriched_counts
    2. Top Therapeutic Area     → #1 TA by total drug trial count
                                  + its top 3 modalities
    3. Modality Spotlight       → top 4 modalities, count + % of drug trials
    4. Beyond Disease           → top non-disease categories
"""

from collections import defaultdict


def wq4_social_stat_cards(summary: dict, enriched_counts: dict) -> list:
    """
    Build the 4 marketing stat cards from snapshot summary data.

    Args:
        summary: snapshot summary{} dict
        enriched_counts: {available, new, existing, total} from enriched file

    Returns:
        list of 4 card dicts
    """
    dio     = summary.get("drug_info_overview", {})
    ta_mod  = summary.get("ta_modality_counts_true_drugs", {})
    intent  = summary.get("drug_study_intent", {})
    non_dis = summary.get("non_disease_study_categories", {})

    drug_total = dio.get("drug_trials_total", 0)

    # ── Card 1 : Drug Trials This Window ────────────────────────────────────
    ec = enriched_counts or {}
    detail_c1 = []
    if ec.get("available"):
        detail_c1 = [
            {"label": "New registrations", "value": ec.get("new",      0)},
            {"label": "Existing updated",  "value": ec.get("existing", 0)},
        ]
    else:
        disease_n     = intent.get("disease",     0)
        non_disease_n = intent.get("non_disease", 0)
        if disease_n or non_disease_n:
            detail_c1 = [
                {"label": "Disease studies",     "value": disease_n},
                {"label": "Non-disease studies", "value": non_disease_n},
            ]

    card1 = {
        "id":     "mk_wq1_c1",
        "title":  "Drug Trials This Window",
        "value":  f"{drug_total:,}",
        "sub":    "drug trials in the weekly pulse",
        "detail": detail_c1,
        "note":   "Source: snapshot summary — drug_info_overview",
    }

    # ── Card 2 : Top Therapeutic Area ────────────────────────────────────────
    ta_totals = {
        ta: sum(mods.values())
        for ta, mods in ta_mod.items()
        if ta and ta != "Unknown"
    }
    top_ta    = max(ta_totals, key=ta_totals.__getitem__) if ta_totals else "—"
    top_ta_n  = ta_totals.get(top_ta, 0)
    top_ta_pct = round(top_ta_n / drug_total * 100, 1) if drug_total else 0.0

    ta_mod_breakdown = sorted(
        (ta_mod.get(top_ta) or {}).items(),
        key=lambda x: x[1], reverse=True
    )[:3]
    detail_c2 = [
        {
            "label": mod,
            "value": count,
            "pct":   round(count / top_ta_n * 100, 1) if top_ta_n else 0.0,
        }
        for mod, count in ta_mod_breakdown
    ]

    card2 = {
        "id":     "mk_wq1_c2",
        "title":  "Top Therapeutic Area",
        "value":  top_ta,
        "sub":    f"{top_ta_n:,} trials · {top_ta_pct}% of drug trials",
        "detail": detail_c2,
        "note":   "Source: ta_modality_counts_true_drugs",
    }

    # ── Card 3 : Modality Spotlight ───────────────────────────────────────────
    mod_totals: dict = defaultdict(int)
    for mods in ta_mod.values():
        for mod, n in mods.items():
            mod_totals[mod] += n

    top_mods = sorted(mod_totals.items(), key=lambda x: x[1], reverse=True)[:4]
    detail_c3 = [
        {
            "label": mod.replace("_", " ").title(),
            "value": count,
            "pct":   round(count / drug_total * 100, 1) if drug_total else 0.0,
        }
        for mod, count in top_mods
    ]

    card3 = {
        "id":    "mk_wq1_c3",
        "title": "Modality Spotlight",
        "value": top_mods[0][0].replace("_", " ").title() if top_mods else "—",
        "sub":   f"leads with {top_mods[0][1]:,} trials" if top_mods else "",
        "detail": detail_c3,
        "note":  "% of drug trials in this window",
    }

    # ── Card 4 : Beyond Disease ───────────────────────────────────────────────
    top_non_dis   = sorted(non_dis.items(), key=lambda x: x[1], reverse=True)[:4]
    non_dis_total = sum(non_dis.values())
    detail_c4 = [
        {
            "label": cat.replace("_", " ").title(),
            "value": count,
            "pct":   round(count / non_dis_total * 100, 1) if non_dis_total else 0.0,
        }
        for cat, count in top_non_dis
    ]

    card4 = {
        "id":     "mk_wq1_c4",
        "title":  "Beyond Disease",
        "value":  f"{non_dis_total:,}",
        "sub":    "non-disease drug trials",
        "detail": detail_c4,
        "note":   "Source: non_disease_study_categories",
    }

    return [card1, card2, card3, card4]
