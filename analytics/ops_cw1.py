"""
analytics/ops_cw1.py
────────────────────
Operations / cw4 (ChiCTR) — Pipeline Health & Classifier Confidence

Business question:
    "Is the ChiCTR data pipeline healthy? Can we trust today's classifications?"

Source:
    current ChiCTR snapshot + enriched file + checkpoint file mtimes.

Provenance note:
    Everything here is introspection of the ML pipeline. No external data.

Returns:
    dict:
      freshness:
        current_as_of:    ISO date of the snapshot's as_of field
        days_since:       int — days since as_of
        scrape_mtime:     ISO timestamp of chictr_details_checkpoint.jsonl
        scrape_age_days:  int
      counts:
        current_total:    int
        current_drug:     int
        drug_share:       float
      classifier_overrides:
        gene_therapy_override:     int  — trials bumped to gene_therapy by regex
        radiopharma_rejected:      int  — trials downgraded from radio to non_drug
        low_confidence_biologic:   int  — biologic predictions below 0.75
      modality_distribution:  {modality: count}
      ta_distribution:        {ta: count}  (top 15)
      info_flag_counts:       {flag: count}
      sample_low_confidence:  list of 10 low-conf biologic trials for review
"""

from collections import Counter
from datetime import date, datetime
from pathlib import Path


def cw4_china_pipeline_health(current_snap: dict,
                              checkpoint_path: str | Path = "storage/chictr_details_checkpoint.jsonl"
                              ) -> dict:
    """Introspect the ChiCTR pipeline state.

    Args:
        current_snap: parsed dict of today's ChiCTR snapshot JSON
        checkpoint_path: path to the details JSONL
    """
    meta   = current_snap.get("metadata", {}) or {}
    trials = current_snap.get("trials", []) or []

    as_of = meta.get("as_of")
    try:
        as_of_date = date.fromisoformat(as_of) if as_of else None
    except ValueError:
        as_of_date = None
    days_since = (date.today() - as_of_date).days if as_of_date else None

    ckpt = Path(checkpoint_path)
    if ckpt.exists():
        scrape_mtime_dt = datetime.fromtimestamp(ckpt.stat().st_mtime)
        scrape_mtime    = scrape_mtime_dt.isoformat(timespec="seconds")
        scrape_age_days = (datetime.now() - scrape_mtime_dt).days
    else:
        scrape_mtime    = None
        scrape_age_days = None

    drug_trials = [t for t in trials if t.get("is_drug_trial")]
    current_total = len(trials)
    current_drug  = len(drug_trials)
    drug_share    = (current_drug / current_total) if current_total else 0.0

    # Count override flags
    gt_override   = 0
    rp_rejected   = 0
    low_conf_bio  = 0
    info_counter: Counter = Counter()
    sample_low_conf: list = []

    for t in trials:
        flags = t.get("info_flags") or []
        for f in flags:
            info_counter[f] += 1
            if f.startswith("override:gene_therapy"):
                gt_override += 1
            if f == "low_confidence_biologic":
                low_conf_bio += 1
                if len(sample_low_conf) < 10:
                    sample_low_conf.append({
                        "nct_id":     t.get("nct_id"),
                        "title":      (t.get("title") or "")[:180],
                        "modality":   t.get("modality"),
                        "sponsor":    t.get("sponsor_name"),
                        "source_url": t.get("source_url"),
                    })
        # radiopharma rejection: modality ended up non_drug via radio gate
        if "override:non_drug" in flags and not t.get("is_drug_trial"):
            rp_rejected += 1

    modality_dist = Counter(
        (t.get("modality") or "unknown") for t in drug_trials
    )
    ta_dist = Counter(
        (t.get("therapeutic_area") or "Unassigned") for t in drug_trials
    )

    return {
        "freshness": {
            "current_as_of":   as_of,
            "days_since":      days_since,
            "scrape_mtime":    scrape_mtime,
            "scrape_age_days": scrape_age_days,
        },
        "counts": {
            "current_total": current_total,
            "current_drug":  current_drug,
            "drug_share":    round(drug_share, 3),
        },
        "classifier_overrides": {
            "gene_therapy_override":   gt_override,
            "radiopharma_rejected":    rp_rejected,
            "low_confidence_biologic": low_conf_bio,
        },
        "modality_distribution":  dict(modality_dist.most_common()),
        "ta_distribution":        dict(ta_dist.most_common(15)),
        "info_flag_counts":       dict(info_counter.most_common()),
        "sample_low_confidence":  sample_low_conf,
    }
