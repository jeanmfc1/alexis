"""
analytics/bd_wq2.py
--------------------
BD / wq2 -- Client Trial Alert Cards

Business question:
    "Are any of our existing clients filing new trials we should know about?"

Source:
    enriched_trials[] with update_type == "new" and is_drug_trial == True
    client MDM xlsx at storage/List of MDM or Sponsor Codes.xlsx

Matching:
    4-tier fuzzy match, same heuristic used in the ad-hoc client audit:
        exact (normalised)
        loose (strip common stopwords: inc / ltd / pharma / etc.)
        jaccard_high (token Jaccard >= 0.70)
        jaccard_mid  (token Jaccard >= 0.50)

Priority score = sum over the client's new trials of
                 modality_weight * phase_weight (same as bd_wq1)
plus alert_reason boosts:
    +2.0  if any phase 3 / phase 2/3
    +2.0  if any rare modality (cell / gene / adc / radio / bispecific)
    +1.0  if multi-trial week (>= 3 new trials)

Match cache:
    storage/cache/bd_wq2_client_index.json, keyed by mtime of the xlsx.
"""

from __future__ import annotations
import json
import re
from collections import defaultdict, Counter
from pathlib import Path

from analytics.shared import modality_weight, phase_weight

CLIENT_XLSX = Path("storage/List of MDM or Sponsor Codes.xlsx")
CACHE_DIR   = Path("storage/cache")
CACHE_PATH  = CACHE_DIR / "bd_wq2_client_index.json"

RARE_MODALITIES = {"cell_therapy", "gene_therapy", "adc",
                   "bispecific_antibody", "radiopharmaceutical"}

STOPWORDS = {
    "INC","LLC","LTD","LIMITED","CORP","CORPORATION","CO","COMPANY",
    "GMBH","AG","SA","SAS","BV","NV","PLC","PTY","AB","OY","SRL","SPA",
    "SARL","KG","LP","LLP",
    "PHARMACEUTICAL","PHARMACEUTICALS","PHARMA","PHARM",
    "THERAPEUTICS","THERAPEUTIC","BIOSCIENCES","BIOSCIENCE","BIOTECH","BIO",
    "BIOTECHNOLOGY","GROUP","HOLDINGS","HOLDING","MEDICAL","MEDICINE",
    "MEDICINES","HEALTHCARE","HEALTH","INTERNATIONAL","GLOBAL","USA",
    "AMERICA","RESEARCH","LABORATORIES","LAB","LABS","SCIENCES","SCIENCE","SCI",
}


def _norm(s: str) -> str:
    s = (s or "").upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _loose(s: str) -> str:
    toks = [x for x in _norm(s).split() if x not in STOPWORDS and len(x) > 1]
    return " ".join(toks)


def _sig_toks(s: str) -> set:
    return {x for x in _norm(s).split()
            if x not in STOPWORDS and len(x) >= 3}


def _strip_cc(s: str) -> tuple[str, str | None]:
    """Return (name_sans_country, 2-letter-code) -- name is cleaned."""
    m = re.match(r"^(.*?)\s*\[([A-Z]{2})\]\s*$", (s or "").strip())
    if m:
        return m.group(1).strip(), m.group(2)
    return (s or "").strip(), None


def _load_client_index() -> dict | None:
    """Load (or build + cache) the client index from the xlsx.

    Cached structure:
        {
          "mtime":    float,
          "entries":  [ {clean, country, mdm, norm, loose, sig_toks[]}, ... ],
          "norm_idx": {norm: [entry_indices]},
          "loose_idx":{loose: [entry_indices]},
          "tok_idx":  {token: [entry_indices]},
        }
    """
    if not CLIENT_XLSX.exists():
        return None
    mtime = CLIENT_XLSX.stat().st_mtime

    if CACHE_PATH.exists():
        try:
            cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            # Invalidate old caches missing the "raw" field (pre-v2 schema)
            has_raw = bool(cached.get("entries")
                           and "raw" in cached["entries"][0])
            if cached.get("mtime") == mtime and has_raw:
                for e in cached["entries"]:
                    e["sig_toks"] = set(e["sig_toks"])
                return cached
        except Exception:
            pass

    try:
        import pandas as pd
    except ImportError:
        return None

    df = pd.read_excel(CLIENT_XLSX)
    entries = []
    norm_idx: dict = defaultdict(list)
    loose_idx: dict = defaultdict(list)
    tok_idx: dict   = defaultdict(list)

    for i, row in df.iterrows():
        raw   = str(row.get("Name") or "")
        clean, cc = _strip_cc(raw)
        if not clean:
            continue
        nm   = _norm(clean)
        lo   = _loose(clean)
        toks = _sig_toks(clean)
        mdm  = row.get("MDMID__c")
        entry = {
            "raw":      raw,
            "clean":    clean,
            "country":  cc,
            "mdm":      str(mdm) if mdm and str(mdm) != "nan" else None,
            "norm":     nm,
            "loose":    lo,
            "sig_toks": sorted(toks),
        }
        idx = len(entries)
        entries.append(entry)
        if nm:   norm_idx[nm].append(idx)
        if lo:   loose_idx[lo].append(idx)
        for t in toks:
            tok_idx[t].append(idx)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "mtime":     mtime,
        "entries":   entries,
        "norm_idx":  dict(norm_idx),
        "loose_idx": dict(loose_idx),
        "tok_idx":   dict(tok_idx),
    }
    CACHE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    for e in payload["entries"]:
        e["sig_toks"] = set(e["sig_toks"])
    return payload


def _best_match(sponsor_name: str, idx: dict) -> dict | None:
    """Return {entry, tier, conf} or None."""
    if not sponsor_name:
        return None
    nm = _norm(sponsor_name)
    lo = _loose(sponsor_name)
    toks = _sig_toks(sponsor_name)

    entries = idx["entries"]

    # Tier 1: exact
    if nm in idx["norm_idx"]:
        return {"entry": entries[idx["norm_idx"][nm][0]],
                "tier": "exact", "conf": "high"}
    # Tier 2: loose
    if lo and lo in idx["loose_idx"]:
        return {"entry": entries[idx["loose_idx"][lo][0]],
                "tier": "loose", "conf": "high"}
    # Tier 3/4: token Jaccard
    if not toks:
        return None
    cand_counts: Counter = Counter()
    for t in toks:
        for i in idx["tok_idx"].get(t, []):
            cand_counts[i] += 1
    if not cand_counts:
        return None
    best_i, best_j = None, 0.0
    for i, _ in cand_counts.most_common(40):
        other = set(entries[i]["sig_toks"])
        if not other:
            continue
        j = len(toks & other) / len(toks | other)
        if j > best_j:
            best_j, best_i = j, i
    if best_i is None:
        return None
    if best_j >= 0.70:
        return {"entry": entries[best_i], "tier": "jaccard_high",
                "conf": "medium"}
    if best_j >= 0.50:
        return {"entry": entries[best_i], "tier": "jaccard_mid",
                "conf": "low"}
    return None


def _reasons(trials: list) -> list[str]:
    reasons = []
    phases = {(t.get("phase") or "").upper() for t in trials}
    mods   = {t.get("modality") for t in trials if t.get("modality")}
    if phases & {"PHASE3", "PHASE2/PHASE3"}:
        reasons.append("Phase 3 activity")
    rare_hit = mods & RARE_MODALITIES
    if rare_hit:
        reasons.append("Rare modality: " + ", ".join(sorted(rare_hit)))
    if len(trials) >= 3:
        reasons.append(f"Multi-trial week ({len(trials)})")
    return reasons


def wq2_client_alert_cards(enriched_trials: list,
                           client_list: list | None = None) -> dict:
    """
    Args:
        enriched_trials: trials list from enriched_*.json
        client_list:     ignored (kept for signature compat); the function
                         loads the xlsx itself via the cache layer.

    Returns dict shape consumed by viz/bd_wq2.jsx
        {
          available,
          alerts:      list of client rows sorted by priority desc,
          total_new_drug,
          matched_trials,
          unmatched_trials,
          meta: {
            client_corpus_size, cache_mtime, thresholds
          }
        }
    """
    new_drug = [
        t for t in enriched_trials
        if t.get("update_type") == "new" and t.get("is_drug_trial")
    ]
    if not new_drug:
        return {"available": False, "reason": "no new drug trials"}

    idx = _load_client_index()
    if not idx:
        return {
            "available": False,
            "reason": "client list xlsx not loaded (expected at "
                      "storage/List of MDM or Sponsor Codes.xlsx)",
            "total_new_drug": len(new_drug),
        }

    by_client: dict = defaultdict(lambda: {"match": None, "trials": []})
    unmatched = 0
    for t in new_drug:
        sp = t.get("sponsor_name") or ""
        mr = _best_match(sp, idx)
        if not mr:
            unmatched += 1
            continue
        key = mr["entry"]["clean"]
        group = by_client[key]
        if not group["match"]:
            group["match"] = mr
        group["trials"].append(t)

    alerts = []
    for client_name, g in by_client.items():
        trials = g["trials"]
        entry  = g["match"]["entry"]
        tier   = g["match"]["tier"]
        conf   = g["match"]["conf"]

        score = sum(
            modality_weight(t.get("modality")) * phase_weight(t.get("phase"))
            for t in trials
        )
        reasons = _reasons(trials)
        # Reason-based boost
        if "Phase 3 activity" in reasons:     score += 2.0
        if any(r.startswith("Rare") for r in reasons): score += 2.0
        if any(r.startswith("Multi") for r in reasons): score += 1.0

        if score >= 12:   level = "HIGH"
        elif score >= 4:  level = "MED"
        else:             level = "LOW"

        mod_counts = Counter((t.get("modality") or "Unknown") for t in trials)
        top_mods = [m for m, _ in mod_counts.most_common()]
        phase_counts = Counter((t.get("phase") or "Unknown") for t in trials)
        top_phase = phase_counts.most_common(1)[0][0] if phase_counts else None

        trial_rows = [
            {
                "nct_id":            t.get("nct_id"),
                "title":             t.get("title"),
                "modality":          t.get("modality"),
                "phase":             t.get("phase"),
                "therapeutic_area":  t.get("therapeutic_area"),
                "overall_status":    t.get("overall_status"),
                "first_posted_date": t.get("first_posted_date"),
                "source_url": (
                    f"https://clinicaltrials.gov/study/{t.get('nct_id')}"
                    if (t.get("nct_id") or "").startswith("NCT")
                    else t.get("source_url")
                ),
            }
            for t in trials
        ]

        alerts.append({
            "client_name":      client_name,
            "client_name_raw":  entry.get("raw"),
            "client_country":   entry.get("country"),
            "mdm":              entry.get("mdm"),
            "match_tier":       tier,
            "match_confidence": conf,
            "matched_sponsor":  trials[0].get("sponsor_name"),
            "new_trial_count":  len(trials),
            "top_modalities":   top_mods,
            "top_phase":        top_phase,
            "priority_score":   round(score, 1),
            "alert_level":      level,
            "alert_reasons":    reasons,
            "trials":           trial_rows,
        })

    alerts.sort(key=lambda r: (r["priority_score"], r["new_trial_count"]),
                reverse=True)

    return {
        "available":        True,
        "alerts":           alerts,
        "total_new_drug":   len(new_drug),
        "matched_trials":   sum(a["new_trial_count"] for a in alerts),
        "unmatched_trials": unmatched,
        "meta": {
            "client_corpus_size": len(idx["entries"]),
            "cache_mtime":        idx["mtime"],
        },
    }
