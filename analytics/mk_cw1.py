"""
analytics/mk_cw1.py
--------------------
Marketing / cw2 (ChiCTR) -- Therapeutic-Area Momentum

Business question:
    "Which therapeutic areas are accelerating in China this week?"

Source:
    enriched ChiCTR snapshot (for this-week new-trial counts by TA)
    plus prior ChiCTR snapshots (to compute a baseline weekly rate).

Baseline calculation:
    Prior ChiCTR snapshots are FULL cumulative corpora, not weekly slices.
    So we compute weekly additions via consecutive-pair set differences:
        for (older, newer) in zip(priors_asc, priors_asc[1:]):
            newer.drug_ta_counts - older.drug_ta_ncts
        = number of new drug trials per TA appearing between those snapshots.
    Baseline = mean of these per-pair counts across all pair windows.
    If fewer than 2 prior snapshots exist, fall back to
    total_drug_trials / 52 as a coarse weekly rate estimate.

Trend definition:
    accelerating: this_week >= 1.5x baseline AND this_week >= 3
    slowing:      this_week <= 0.5x baseline AND baseline   >= 2
    new:          baseline == 0 AND this_week > 0
    steady:       anything else
"""

from collections import Counter, defaultdict
from statistics import mean

ACCELERATING_RATIO = 1.5
ACCELERATING_MIN   = 3
SLOWING_RATIO      = 0.5
SLOWING_MIN_BASE   = 2


def _classify_trend(this_week, baseline):
    if baseline == 0:
        return "new" if this_week > 0 else "steady"
    ratio = this_week / baseline
    if ratio >= ACCELERATING_RATIO and this_week >= ACCELERATING_MIN:
        return "accelerating"
    if ratio <= SLOWING_RATIO and baseline >= SLOWING_MIN_BASE:
        return "slowing"
    return "steady"


def cw2_china_ta_momentum(enriched_trials, prior_snapshots):
    # 1. This-week new drug trials grouped by TA
    new_drug = [
        t for t in enriched_trials
        if t.get("update_type") == "new" and t.get("is_drug_trial")
    ]
    this_counts = Counter(
        (t.get("therapeutic_area") or "Unassigned") for t in new_drug
    )
    total_new = sum(this_counts.values())

    # Top modality per TA (colour signal for cards)
    top_mod_by_ta = {}
    for ta in this_counts:
        mod_counts = Counter(
            t.get("modality") for t in new_drug
            if (t.get("therapeutic_area") or "Unassigned") == ta
        )
        top_mod_by_ta[ta] = mod_counts.most_common(1)[0][0] if mod_counts else None

    # 2. Baseline via consecutive-pair deltas, normalised to weekly rate.
    #    Filters out "backfill" pairs (very short spacing with improbably
    #    large deltas; usually the scraper catching up on historical data
    #    rather than genuine registrations).
    from datetime import datetime as _dt

    MIN_DAYS_BETWEEN     = 3          # pairs closer than this are likely backfill
    MAX_DRUG_PER_DAY     = 500        # cap for realistic daily drug-trial adds
    SCALE_TO_WEEKLY_DAYS = 7.0

    def _parse_as_of(s):
        try:
            return _dt.fromisoformat(str(s)[:10]).date()
        except Exception:
            return None

    baseline_per_ta = defaultdict(list)
    pair_windows = 0
    pair_windows_skipped = 0
    if prior_snapshots:
        snaps_asc = sorted(
            prior_snapshots,
            key=lambda s: (s.get("metadata", {}) or {}).get("as_of", "")
        )
        if len(snaps_asc) >= 2:
            for older, newer in zip(snaps_asc, snaps_asc[1:]):
                old_as_of = _parse_as_of(
                    (older.get("metadata", {}) or {}).get("as_of"))
                new_as_of = _parse_as_of(
                    (newer.get("metadata", {}) or {}).get("as_of"))
                if not (old_as_of and new_as_of):
                    pair_windows_skipped += 1
                    continue
                days = (new_as_of - old_as_of).days
                if days < MIN_DAYS_BETWEEN:
                    pair_windows_skipped += 1
                    continue

                older_ids = {
                    t.get("nct_id") for t in older.get("trials", [])
                    if t.get("is_drug_trial") and t.get("nct_id")
                }
                added = [
                    t for t in newer.get("trials", [])
                    if t.get("is_drug_trial")
                    and t.get("nct_id") not in older_ids
                ]
                # Skip pairs whose per-day rate is implausible -- usually
                # scrape backfill, not real registrations.
                if days > 0 and (len(added) / days) > MAX_DRUG_PER_DAY:
                    pair_windows_skipped += 1
                    continue

                scale = SCALE_TO_WEEKLY_DAYS / max(days, 1)
                by_ta = Counter(
                    (t.get("therapeutic_area") or "Unassigned") for t in added
                )
                for ta, n in by_ta.items():
                    baseline_per_ta[ta].append(n * scale)
                pair_windows += 1
        else:
            only = snaps_asc[0]
            by_ta_total = Counter(
                (t.get("therapeutic_area") or "Unassigned")
                for t in only.get("trials", []) if t.get("is_drug_trial")
            )
            for ta, n in by_ta_total.items():
                baseline_per_ta[ta].append(n / 52.0)

    # If no valid baseline pair survived filtering, signal honestly.
    no_valid_baseline = (pair_windows == 0) and not baseline_per_ta
    if no_valid_baseline and prior_snapshots:
        return {
            "available": False,
            "reason": (
                "No valid baseline could be computed from ChiCTR prior "
                "snapshots. All "
                f"{pair_windows_skipped} consecutive-pair windows were "
                "either spaced less than 3 days apart or their per-day "
                "delta exceeded the MAX_DRUG_PER_DAY cap (usually scrape "
                "backfill, not genuine registrations). Schedule weekly "
                "ChiCTR snapshots -- see pipelines/run_chictr_scrape.py -- "
                "so at least two snapshots sit 7+ days apart before the "
                "next diff."
            ),
            "pair_windows_skipped": pair_windows_skipped,
        }

    # 3. Build item rows
    all_tas = set(this_counts) | set(baseline_per_ta)
    items = []
    for ta in all_tas:
        this_n   = this_counts.get(ta, 0)
        base_avg = mean(baseline_per_ta[ta]) if baseline_per_ta.get(ta) else 0.0
        trend    = _classify_trend(this_n, base_avg)
        ratio    = (this_n / base_avg) if base_avg > 0 else None
        items.append({
            "ta":           ta,
            "this_week":    this_n,
            "baseline":     round(base_avg, 2),
            "ratio":        round(ratio, 2) if ratio is not None else None,
            "trend":        trend,
            "top_modality": top_mod_by_ta.get(ta),
        })

    trend_rank = {"accelerating": 0, "new": 1, "steady": 2, "slowing": 3}
    items.sort(key=lambda r: (trend_rank.get(r["trend"], 9),
                              -(r["ratio"] or 0),
                              -r["this_week"]))

    # 4. Build 2x2 summary cards (mirrors mk_wq1 layout)
    accel = [i for i in items if i["trend"] == "accelerating"]
    slow  = [i for i in items if i["trend"] == "slowing"]
    fresh = [i for i in items if i["trend"] == "new"]

    total_baseline = round(sum(mean(v) for v in baseline_per_ta.values() if v), 1)
    overall_ratio  = round(total_new / total_baseline, 2) if total_baseline > 0 else None

    def top_n(rows, n=4, key="this_week"):
        return [{"ta": r["ta"], "value": r[key], "ratio": r["ratio"],
                 "modality": r["top_modality"]} for r in rows[:n]]

    cards = [
        {
            "title":  "NEW DRUG TRIALS",
            "value":  total_new,
            "sub":    (f"baseline ~{total_baseline}/week"
                       + (f"  ({overall_ratio}x)" if overall_ratio else "")),
            "detail": top_n(items, 4, "this_week"),
            "note":   "Volume vs baseline across all TAs",
        },
        {
            "title":  "ACCELERATING TAs",
            "value":  len(accel),
            "sub":    f"{ACCELERATING_RATIO}x baseline + min {ACCELERATING_MIN} trials",
            "detail": top_n(accel, 4, "this_week"),
            "note":   "Where Chinese activity is concentrating",
        },
        {
            "title":  "NEW / EMERGING TAs",
            "value":  len(fresh),
            "sub":    "trials with no prior-week activity",
            "detail": top_n(fresh, 4, "this_week"),
            "note":   "TAs absent from prior snapshots",
        },
        {
            "title":  "SLOWING TAs",
            "value":  len(slow),
            "sub":    f"<= {SLOWING_RATIO}x baseline, baseline >= {SLOWING_MIN_BASE}",
            "detail": top_n(slow, 4, "baseline"),
            "note":   "Categories cooling vs recent weeks",
        },
    ]

    return {
        "available":      total_new > 0 or bool(baseline_per_ta),
        "items":          items,
        "cards":          cards,
        "total_new":      total_new,
        "total_baseline": total_baseline,
        "snapshots_used":      len(prior_snapshots),
        "pair_windows":        pair_windows,
        "pair_windows_skipped": pair_windows_skipped,
        "thresholds": {
            "accelerating_ratio": ACCELERATING_RATIO,
            "accelerating_min":   ACCELERATING_MIN,
            "slowing_ratio":      SLOWING_RATIO,
            "slowing_min_base":   SLOWING_MIN_BASE,
        },
    }
