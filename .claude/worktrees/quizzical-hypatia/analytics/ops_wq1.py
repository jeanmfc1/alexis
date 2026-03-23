"""
analytics/ops_wq1.py
─────────────────────
Operations / wq1 — Velocity Dashboard

Business question:
    "What is the new drug trial velocity this week vs. recent weeks?"

Source (current week):
    enriched_trials — new drug registrations, TA/mod/phase breakdown
    changelog       — new_active_all (all trial types)
    snap_meta       — window dates

Source (prior weeks):
    prior_weeks list from pick_prior_snapshots() (already loaded)

Returns:
    dict with 4 tile payloads:
    Tile 1 — Sparkline of new drug registrations over N weeks + pace vs avg
    Tile 2 — Diverging bars: top 3 / bottom 3 TAs by % change vs prior avg
    Tile 3 — Diverging bars: top 3 / bottom 3 modalities by % change vs prior avg
    Tile 4 — Phase 1 intake rate — arc gauge + sparkline over N weeks
"""

from collections import defaultdict
import re as _re


def wq10_velocity_dashboard(
    enriched_trials: list,
    snap_meta:       dict,
    snap_summary:    dict,
    changelog:       dict,
    prior_weeks:     list,
) -> dict:
    """
    Build the velocity dashboard payload from enriched trials and prior weeks.

    Args:
        enriched_trials: trials list from enriched_*.json
        snap_meta:       metadata{} from the snapshot
        snap_summary:    summary{} from the snapshot (not currently used but reserved)
        changelog:       reshaped changelog dict from extract_changelog()
        prior_weeks:     list of prior week dicts from pick_prior_snapshots()

    Returns:
        velocity dashboard dict; {available: False} if no enriched data
    """
    # ── Current week counts from enriched_trials ───────────────────────────
    cur_ta:    dict = defaultdict(int)
    cur_mod:   dict = defaultdict(int)
    cur_phase: dict = defaultdict(int)
    cur_drug_new = 0

    for t in enriched_trials:
        if t.get("update_type") != "new":
            continue
        if not t.get("is_drug_trial", True):
            continue
        cur_drug_new += 1
        cur_ta[t.get("therapeutic_area") or "Unknown"] += 1
        cur_mod[t.get("modality")         or "Unknown"] += 1
        cur_phase[(t.get("phase") or "NA").upper()] += 1

    cur_ta    = dict(cur_ta)
    cur_mod   = dict(cur_mod)
    cur_phase = dict(cur_phase)

    ws = snap_meta.get("window_start", "")
    we = snap_meta.get("window_end", snap_meta.get("as_of", ""))
    cur_window_label = f"{ws} → {we}" if ws else "current"

    available = cur_drug_new > 0
    has_prior = bool(prior_weeks) and len(prior_weeks) >= 1

    if not available:
        return {"available": False}

    # ── Helper: short label "Feb 27" from "YYYY-MM-DD → YYYY-MM-DD" ────────
    def short_label(window_label: str) -> str:
        dates = _re.findall(r'\d{4}-(\d{2})-(\d{2})', window_label)
        if len(dates) >= 2:
            mo_map = {
                "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
                "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
                "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
            }
            mo, dy = dates[1]
            return f"{mo_map.get(mo, mo)} {int(dy)}"
        return window_label[:10]

    # ── Tile 1: Sparkline data (oldest → current) ──────────────────────────
    sparkline_pts = []
    for pw in prior_weeks:   # already oldest-first from pick_prior_snapshots
        sparkline_pts.append({
            "window_label": pw.get("window_label", ""),
            "short_label":  short_label(pw.get("window_label", "")),
            "drug_new":     pw.get("drug_new_total", 0),
        })
    sparkline_pts.append({
        "window_label": cur_window_label,
        "short_label":  short_label(cur_window_label),
        "drug_new":     cur_drug_new,
        "is_current":   True,
    })

    prior_drug_totals = [pw.get("drug_new_total", 0) for pw in prior_weeks]
    prior_avg_drug    = sum(prior_drug_totals) / len(prior_drug_totals) if prior_drug_totals else None
    pace_delta_pct    = None
    if prior_avg_drug and prior_avg_drug > 0:
        pace_delta_pct = round((cur_drug_new - prior_avg_drug) / prior_avg_drug * 100, 1)

    # ── Tiles 2 & 3: Diverging bar helper ─────────────────────────────────
    SKIP_LABELS = {
        "unassigned drug study", "unassigned", "unknown",
        "non-disease", "non_disease", "other",
    }

    def _pct_change_bars(cur_counts: dict, cur_total: int,
                         prior_key: str, max_bars: int = 3) -> list:
        if cur_total == 0:
            return []
        all_keys = set(cur_counts.keys())
        for pw in prior_weeks:
            all_keys |= set((pw.get(prior_key) or {}).keys())

        bars = []
        for key in all_keys:
            if key.lower() in SKIP_LABELS:
                continue
            c_pct  = cur_counts.get(key, 0) / cur_total
            pw_pcts = []
            for pw in prior_weeks:
                pw_total = pw.get("drug_new_total") or 0
                if pw_total > 0:
                    pw_pcts.append((pw.get(prior_key) or {}).get(key, 0) / pw_total)
            avg_pct = sum(pw_pcts) / len(pw_pcts) if pw_pcts else 0.0

            # Skip negligible entries (< 0.5% both current and average)
            if c_pct < 0.005 and avg_pct < 0.005:
                continue

            raw_delta = (c_pct - avg_pct) / max(avg_pct, 0.001) * 100
            bars.append({
                "label":       key,
                "current_pct": round(c_pct * 100, 1),
                "avg_pct":     round(avg_pct * 100, 1),
                "delta_pct":   round(raw_delta, 1),
                "current_n":   cur_counts.get(key, 0),
            })

        bars.sort(key=lambda b: b["delta_pct"], reverse=True)
        gainers   = bars[:max_bars]
        decliners = sorted(bars, key=lambda b: b["delta_pct"])[:max_bars]
        # Gainers descending, then decliners ascending (most negative last)
        combined  = gainers + [b for b in decliners if b not in gainers]
        return combined

    ta_bars  = _pct_change_bars(cur_ta,  cur_drug_new, "ta_totals",  max_bars=3) if has_prior else []
    mod_bars = _pct_change_bars(cur_mod, cur_drug_new, "mod_totals", max_bars=3) if has_prior else []

    # Top TAs by absolute count (for tile 1 badges — NOT deviation)
    ta_top = sorted(
        [{"label": k, "count": v, "pct": round(v / cur_drug_new * 100, 1)}
         for k, v in cur_ta.items() if k.lower() not in SKIP_LABELS],
        key=lambda x: -x["count"]
    )

    # ── Tile 4: Phase 1 intake ─────────────────────────────────────────────
    PHASE1_KEYS = {"PHASE1", "EARLY_PHASE1", "PHASE1/PHASE2"}

    cur_p1_count = sum(v for k, v in cur_phase.items() if k in PHASE1_KEYS)
    cur_p1_pct   = round(cur_p1_count / cur_drug_new * 100, 1) if cur_drug_new else 0

    prior_p1_pcts = []
    for pw in prior_weeks:
        pc    = pw.get("phase_counts") or {}
        total = pw.get("drug_new_total") or 0
        if pc and total > 0:
            p1 = sum(v for k, v in pc.items() if k in PHASE1_KEYS)
            prior_p1_pcts.append(round(p1 / total * 100, 1))

    avg_p1_pct   = round(sum(prior_p1_pcts) / len(prior_p1_pcts), 1) if prior_p1_pcts else None
    p1_delta_pct = round(cur_p1_pct - avg_p1_pct, 1) if avg_p1_pct is not None else None

    p1_sparkline = []
    for pw in prior_weeks:
        pc    = pw.get("phase_counts") or {}
        total = pw.get("drug_new_total") or 0
        pct   = None
        if pc and total > 0:
            p1  = sum(v for k, v in pc.items() if k in PHASE1_KEYS)
            pct = round(p1 / total * 100, 1)
        p1_sparkline.append({
            "short_label": short_label(pw.get("window_label", "")),
            "pct":         pct,
        })
    p1_sparkline.append({
        "short_label": short_label(cur_window_label),
        "pct":         cur_p1_pct,
        "is_current":  True,
    })

    # ── Phase breakdown (grouped buckets, matching clinical convention) ─────
    # Group sub-phases into logical buckets so the breakdown sums to cur_drug_new
    # and the "Phase 1" row matches the gauge above it.
    PHASE_BUCKETS = [
        ("Phase 1",   {"PHASE1", "EARLY_PHASE1", "PHASE1/PHASE2"}),
        ("Phase 2",   {"PHASE2", "PHASE2/PHASE3"}),
        ("Phase 3",   {"PHASE3"}),
        ("Phase 4",   {"PHASE4"}),
        ("NA / Other", {"NA"}),
    ]
    bucket_keys_used = set()
    phase_breakdown = []
    for label, keys in PHASE_BUCKETS:
        count = sum(cur_phase.get(k, 0) for k in keys)
        bucket_keys_used |= keys
        if count > 0:
            phase_breakdown.append({
                "phase": label,
                "count": count,
                "pct":   round(count / cur_drug_new * 100, 1),
                "is_p1": label == "Phase 1",
            })
    # Catch any phases not in the buckets
    for ph, count in sorted(cur_phase.items(), key=lambda x: -x[1]):
        if ph not in bucket_keys_used and count > 0:
            phase_breakdown.append({
                "phase": ph,
                "count": count,
                "pct":   round(count / cur_drug_new * 100, 1),
                "is_p1": False,
            })

    return {
        "available":        True,
        "has_prior":        has_prior,
        "n_prior_weeks":    len(prior_weeks),
        "cur_window_label": cur_window_label,
        # Tile 1
        "sparkline":        sparkline_pts,
        "cur_drug_new":     cur_drug_new,
        "prior_avg_drug":   round(prior_avg_drug, 1) if prior_avg_drug else None,
        "pace_delta_pct":   pace_delta_pct,
        # Tile 1 badges (top TAs by count)
        "ta_top":           ta_top,
        # Tile 2
        "ta_bars":          ta_bars,
        # Tile 3
        "mod_bars":         mod_bars,
        # Tile 4
        "phase1": {
            "cur_count":  cur_p1_count,
            "cur_pct":    cur_p1_pct,
            "avg_pct":    avg_p1_pct,
            "delta_pct":  p1_delta_pct,
            "sparkline":  p1_sparkline,
            "has_prior":  bool(prior_p1_pcts),
        },
        "phase_breakdown":  phase_breakdown,
    }
