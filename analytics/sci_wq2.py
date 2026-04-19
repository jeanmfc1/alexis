"""
analytics/sci_wq2.py
--------------------
Scientific / wq8 -- Status-Change Spotlight (why_stopped focus)

Business question:
    "What business-meaningful status changes happened this week,
     with emphasis on trials that stopped and WHY?"

Source:
    enriched_trials[] with update_type == "existing" and
    update_categories emitted by analytics.update_categorizer.

Why_stopped bucketisation:
    Keyword-based classifier on the raw why_stopped text, ordered by
    concern severity. First-match wins.

Returns:
    dict with keys:
        available                : bool
        category_counts          : {cat: count} -- full update_category tally
        tier_breakdown           : {tier: count}
        status_transitions       : list[ {from, to, count, ncts[]} ]
        why_stopped_events       : list[ {nct_id, title, sponsor, phase,
                                            modality, ta, from_status,
                                            to_status, reason_text, bucket,
                                            source_url} ]
        why_stopped_buckets      : {bucket: count}
        newly_recruiting         : list of trial dicts (flipped INTO active)
        total_existing_changes   : int
        total_status_changes     : int
        meta                     : {window_start, window_end}
"""

from __future__ import annotations
import re
from collections import Counter, defaultdict
from typing import Dict, List


# ------------------------------------------------------------------
# Bucket rules -- ordered; first match wins
# ------------------------------------------------------------------
BUCKET_RULES = [
    ("safety",     re.compile(r"adverse|toxicity|safety|serious.*event|death|risk.?benefit", re.I)),
    ("efficacy",   re.compile(r"futility|efficacy|interim.*analysis|did\s+not\s+meet|primary.*endpoint|lack\s+of\s+response", re.I)),
    ("enrollment", re.compile(r"enroll|enrol|accrual|recruit|slow|insufficient.*patient|feasibility", re.I)),
    ("funding",    re.compile(r"funding|budget|financial|resource|grant", re.I)),
    ("business",   re.compile(r"strategic|business|portfolio|pipeline|prioriti[sz]|sponsor.*decision|company.*decision", re.I)),
    ("regulatory", re.compile(r"fda|ema|regulator|clinical.?hold|authority", re.I)),
    ("covid",      re.compile(r"covid|pandemic|sars.?cov", re.I)),
    ("logistics",  re.compile(r"site|investigator|manufactur|drug\s+supply|facility", re.I)),
]

ACTIVE_STATUSES = {
    "RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION",
    "ACTIVE_NOT_RECRUITING", "AVAILABLE",
}
TERMINAL_STATUSES = {"COMPLETED", "TERMINATED", "WITHDRAWN", "SUSPENDED"}
STOP_STATUSES     = {"TERMINATED", "WITHDRAWN", "SUSPENDED"}


def _bucket_why_stopped(text: str) -> str:
    if not text or not text.strip():
        return "unstated"
    for name, pat in BUCKET_RULES:
        if pat.search(text):
            return name
    return "other"


def _status_change(t: Dict) -> tuple[str | None, str | None]:
    """Pull (old, new) status from the enriched field_diffs / update_categories."""
    old_status = new_status = None
    for fd in t.get("field_diffs", []) or []:
        if fd.get("field") == "overall_status":
            old_status = (fd.get("old") or "").upper() or None
            new_status = (fd.get("new") or "").upper() or None
            break
    # Fallback: look at update_categories for a direction hint
    if old_status is None and new_status is None:
        cats = t.get("update_categories", []) or []
        for c in cats:
            if c.get("field") == "overall_status":
                old_status = (c.get("old") or "").upper() or None
                new_status = (c.get("new") or "").upper() or None
                break
    return old_status, new_status


def _why_stopped_text(t: Dict) -> str:
    """Return the current why_stopped string, preferring the enriched snapshot value."""
    if t.get("why_stopped"):
        return str(t["why_stopped"]).strip()
    for fd in t.get("field_diffs", []) or []:
        if fd.get("field") == "why_stopped":
            return (str(fd.get("new") or "")).strip()
    return ""


def wq8_classification_gap_report(enriched_trials: List[Dict],
                                  snap_summary: Dict | None = None) -> Dict:
    """
    NB: function name kept for backward compatibility with the existing
    pipelines/generate_weekly_viz.py wiring. Output shape has changed to
    the status-change spotlight described above.

    Args:
        enriched_trials: trials list from enriched_*.json (update_type
                         and update_categories already attached)
        snap_summary:    unused here; kept for call-site compat
    """
    if not enriched_trials:
        return {"available": False, "reason": "no enriched trials"}

    cat_counts: Counter = Counter()
    tier_counts: Counter = Counter()
    status_trans: dict = defaultdict(lambda: {"count": 0, "ncts": []})
    why_stopped_events: list = []
    why_stopped_buckets: Counter = Counter()
    newly_recruiting: list = []

    total_existing = 0
    total_status_changes = 0

    for t in enriched_trials:
        utype = t.get("update_type")
        if utype != "existing":
            continue
        total_existing += 1
        cats = t.get("update_categories", []) or []

        # Tally categories + tiers
        for c in cats:
            cat_counts[c.get("category", "unknown")] += 1
            tier_counts[c.get("tier", 3)] += 1

        # Status transition tracking
        old_s, new_s = _status_change(t)
        if old_s or new_s:
            total_status_changes += 1
            key = (old_s or "UNKNOWN", new_s or "UNKNOWN")
            bucket = status_trans[key]
            bucket["count"] += 1
            if len(bucket["ncts"]) < 15:
                bucket["ncts"].append({
                    "nct_id":     t.get("nct_id"),
                    "title":      (t.get("title") or "")[:200],
                    "sponsor":    t.get("sponsor_name"),
                    "phase":      t.get("phase"),
                    "modality":   t.get("modality"),
                    "ta":         t.get("therapeutic_area"),
                    "source_url": t.get("source_url"),
                })

        # Why_stopped spotlight
        if new_s in STOP_STATUSES or new_s == "COMPLETED":
            # Any terminal transition is interesting; prioritise STOPs
            reason = _why_stopped_text(t)
            if new_s in STOP_STATUSES or reason:
                bucket_name = _bucket_why_stopped(reason)
                why_stopped_buckets[bucket_name] += 1
                why_stopped_events.append({
                    "nct_id":      t.get("nct_id"),
                    "title":       (t.get("title") or "")[:240],
                    "sponsor":     t.get("sponsor_name"),
                    "sponsor_class": t.get("sponsor_class"),
                    "phase":       t.get("phase"),
                    "modality":    t.get("modality"),
                    "ta":          t.get("therapeutic_area"),
                    "from_status": old_s,
                    "to_status":   new_s,
                    "reason_text": reason,
                    "bucket":      bucket_name,
                    "source_url": (
                        f"https://clinicaltrials.gov/study/{t.get('nct_id')}"
                        if t.get("nct_id", "").startswith("NCT")
                        else t.get("source_url")
                    ),
                })

        # Newly flipped into an active status
        if new_s in ACTIVE_STATUSES and old_s and old_s not in ACTIVE_STATUSES:
            newly_recruiting.append({
                "nct_id":    t.get("nct_id"),
                "title":     (t.get("title") or "")[:200],
                "sponsor":   t.get("sponsor_name"),
                "phase":     t.get("phase"),
                "modality":  t.get("modality"),
                "ta":        t.get("therapeutic_area"),
                "from_status": old_s,
                "to_status":   new_s,
                "source_url": (
                    f"https://clinicaltrials.gov/study/{t.get('nct_id')}"
                    if t.get("nct_id", "").startswith("NCT")
                    else t.get("source_url")
                ),
            })

    # Sort why_stopped with severity priority so the UI can trust the order
    bucket_priority = {name: i for i, (name, _) in enumerate(BUCKET_RULES)}
    bucket_priority.update({"other": 90, "unstated": 99})
    late_phase = {"PHASE3": 0, "PHASE2/PHASE3": 1, "PHASE2": 2, "PHASE1/PHASE2": 3,
                  "PHASE1": 4, "EARLY_PHASE1": 5, "PHASE4": 6}
    why_stopped_events.sort(key=lambda e: (
        bucket_priority.get(e["bucket"], 50),
        late_phase.get(e.get("phase") or "", 99),
        e.get("sponsor") or "",
    ))

    status_transitions = [
        {"from_status": k[0], "to_status": k[1],
         "count": v["count"], "ncts": v["ncts"]}
        for k, v in sorted(status_trans.items(), key=lambda kv: -kv[1]["count"])
    ]

    return {
        "available":              True,
        "category_counts":        dict(cat_counts),
        "tier_breakdown":         {str(k): v for k, v in sorted(tier_counts.items())},
        "status_transitions":     status_transitions,
        "why_stopped_events":     why_stopped_events,
        "why_stopped_buckets":    dict(why_stopped_buckets.most_common()),
        "newly_recruiting":       newly_recruiting,
        "total_existing_changes": total_existing,
        "total_status_changes":   total_status_changes,
        "meta": {
            "n_trials_scanned": len(enriched_trials),
            "n_stopped_events": len(why_stopped_events),
            "n_newly_active":   len(newly_recruiting),
        },
    }
