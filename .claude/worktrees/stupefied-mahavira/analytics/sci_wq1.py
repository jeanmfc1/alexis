"""
analytics/sci_wq1.py
─────────────────────
Scientific / wq1 — TA × Modality Bubble Matrix

Business question:
    "Where is new drug trial activity clustering this week, and how does it
     compare to our baseline?"

Source:
    enriched file trials[] (update_type == "new", is_drug_trial == True)
    prior_weeks list from pick_prior_snapshots() in the pipeline
    master_db_summary for fallback heat comparison

Heat formula (week-over-week rate change):
    prior_avg_pct[ta][mod] = mean(
        prior[ta_mod][ta][mod] / prior[drug_new_total]
        for each prior week that has data for this cell
    )
    current_pct = count / week_total
    heat = (current_pct - prior_avg_pct) / max(prior_avg_pct, 0.001)
    clamped to [-1, +1]

    heat >= +0.15 → red (hotter than average)
    heat <= -0.15 → blue (cooler than average)
    otherwise    → neutral grey

    Falls back to master DB comparison when no prior weeks available.
    heat = None when neither source is loaded.
    heat = +1 (max red) for cells never seen in prior weeks.
"""

from collections import defaultdict


MAX_TA  = 12
MAX_MOD = 10


def wq7_ta_modality_matrix(
    enriched_trials:   list,
    master_db_summary: dict,
    prior_weeks:       list,
) -> dict:
    """
    Build the TA × Modality bubble matrix with heat scoring.

    Args:
        enriched_trials:   trials list from enriched_*.json
        master_db_summary: summary{} from master_DB_*.json (may be {})
        prior_weeks:       list of prior week dicts from pick_prior_snapshots()

    Returns:
        dict with keys: available, has_heat, heat_mode, prior_weeks_used,
        prior_window_labels, rows, columns, cells, row_totals, col_totals,
        grand_total, db_total, week_total
    """
    # ── 1. Count current week new drug registrations ───────────────────────
    ta_mod_week: dict = defaultdict(lambda: defaultdict(int))
    cell_trials: dict = defaultdict(list)

    for t in enriched_trials:
        if t.get("update_type") != "new":
            continue
        if not t.get("is_drug_trial", True):
            continue
        ta  = t.get("therapeutic_area") or "Unknown"
        mod = t.get("modality")         or "Unknown"
        ta_mod_week[ta][mod] += 1
        cell_key = f"{ta}||{mod}"
        cell_trials[cell_key].append({
            "nct_id": t.get("nct_id"),
            "title":  t.get("title"),
            "phase":  t.get("phase") or "—",
        })

    if not ta_mod_week:
        return {
            "available":        False,
            "rows":             [],
            "columns":          [],
            "cells":            {},
            "row_totals":       {},
            "col_totals":       {},
            "grand_total":      0,
            "has_heat":         False,
            "heat_mode":        "none",
            "prior_weeks_used": 0,
        }

    # ── 2. Select top TAs and modalities ───────────────────────────────────
    ta_totals  = {ta: sum(m.values()) for ta, m in ta_mod_week.items()}
    mod_totals: dict = defaultdict(int)
    for mods in ta_mod_week.values():
        for mod, n in mods.items():
            mod_totals[mod] += n

    top_tas  = sorted(ta_totals,  key=ta_totals.__getitem__,  reverse=True)[:MAX_TA]
    top_mods = sorted(mod_totals, key=mod_totals.__getitem__, reverse=True)[:MAX_MOD]

    week_total  = sum(mod_totals.values()) or 1
    grand_total = sum(ta_totals[ta] for ta in top_tas)

    # ── 3. Decide heat mode and compute baseline ───────────────────────────
    has_prior  = bool(prior_weeks)
    db_ta_mod  = (master_db_summary or {}).get("ta_modality_counts_true_drugs", {})
    db_dtc     = (master_db_summary or {}).get("drug_trial_counts", {})
    db_total   = db_dtc.get("drug_trials", 0)
    has_master = bool(db_ta_mod and db_total)

    if has_prior:
        heat_mode        = "rolling_avg"
        prior_weeks_used = len(prior_weeks)

        # Per-cell prior average proportion
        prior_avg_pct: dict = {}
        for ta in top_tas:
            for mod in top_mods:
                contributions = []
                for pw in prior_weeks:
                    pw_total = pw.get("drug_new_total") or 0
                    if pw_total > 0:
                        pw_count = (pw.get("ta_mod") or {}).get(ta, {}).get(mod, 0)
                        contributions.append(pw_count / pw_total)
                prior_avg_pct[(ta, mod)] = (
                    sum(contributions) / len(contributions) if contributions else 0.0
                )

    elif has_master:
        heat_mode        = "master_db"
        prior_weeks_used = 0
    else:
        heat_mode        = "none"
        prior_weeks_used = 0

    # ── 4. Build cells ─────────────────────────────────────────────────────
    cells = {}
    for ta in top_tas:
        for mod in top_mods:
            count = ta_mod_week[ta].get(mod, 0)

            # Prior-week average count for panel display
            prior_avg_count = None
            if has_prior and prior_weeks:
                counts = [
                    (pw.get("ta_mod") or {}).get(ta, {}).get(mod, 0)
                    for pw in prior_weeks
                ]
                prior_avg_count = round(sum(counts) / len(counts), 1) if counts else None

            # Compute heat
            heat       = None
            heat_label = None
            if count > 0:
                if heat_mode == "rolling_avg":
                    avg_pct  = prior_avg_pct.get((ta, mod), 0.0)
                    curr_pct = count / week_total
                    raw      = (curr_pct - avg_pct) / max(avg_pct, 0.001)
                    heat     = max(-1.0, min(1.0, raw))

                    if avg_pct == 0:
                        heat_label = "new this week — not seen in prior weeks"
                    else:
                        delta_pct = round(heat * 100, 0)
                        if heat >= 0.15:
                            heat_label = f"▲ {abs(delta_pct):.0f}% above {prior_weeks_used}-week avg"
                        elif heat <= -0.15:
                            heat_label = f"▼ {abs(delta_pct):.0f}% below {prior_weeks_used}-week avg"
                        else:
                            heat_label = f"≈ in line with {prior_weeks_used}-week avg"

                elif heat_mode == "master_db":
                    expected_pct = db_ta_mod.get(ta, {}).get(mod, 0) / db_total
                    curr_pct     = count / week_total
                    raw          = (curr_pct - expected_pct) / max(expected_pct, 0.001)
                    heat         = max(-1.0, min(1.0, raw))
                    delta_pct    = round(heat * 100, 0)
                    if heat >= 0.15:
                        heat_label = f"▲ {abs(delta_pct):.0f}% above master DB baseline"
                    elif heat <= -0.15:
                        heat_label = f"▼ {abs(delta_pct):.0f}% below master DB baseline"
                    else:
                        heat_label = "≈ at master DB baseline"

            baseline_n = db_ta_mod.get(ta, {}).get(mod, 0) if has_master else None

            key = f"{ta}||{mod}"
            cells[key] = {
                "ta":              ta,
                "mod":             mod,
                "count":           count,
                "baseline_n":      baseline_n,
                "prior_avg_count": prior_avg_count,
                "heat":            round(heat, 3) if heat is not None else None,
                "heat_label":      heat_label,
                "trials":          cell_trials.get(key, []),
            }

    row_totals = {ta:  sum(ta_mod_week[ta].get(m,   0) for m  in top_mods) for ta  in top_tas}
    col_totals = {mod: sum(ta_mod_week[ta].get(mod, 0) for ta in top_tas)  for mod in top_mods}

    prior_window_labels = [pw.get("window_label", "") for pw in prior_weeks]

    return {
        "available":           True,
        "has_heat":            heat_mode != "none",
        "heat_mode":           heat_mode,
        "prior_weeks_used":    prior_weeks_used,
        "prior_window_labels": prior_window_labels,
        "rows":                top_tas,
        "columns":             top_mods,
        "cells":               cells,
        "row_totals":          row_totals,
        "col_totals":          col_totals,
        "grand_total":         grand_total,
        "db_total":            db_total,
        "week_total":          week_total,
    }
