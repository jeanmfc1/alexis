# analytics/ta_audit.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple
import re

from policy.ta_policy import (
    TA_ONCOLOGY, TA_INFECTIOUS, TA_IMMUNO, TA_NEURO, TA_CARDIO, TA_METABOLIC, TA_RARE, TA_MSK, TA_OTHER,
    BENIGN_GUARD_KWS,
    ONCOLOGY_KW, INFECTIOUS_KW, IMMUNO_KW, NEURO_KW, CARDIO_KW, METABOLIC_KW, RARE_KW, MSK_KW,
    PAIN_SYNDROME_PATS, PDPN_PATS,
    NON_CARDIO_CATHETER_EXCLUSIONS, CARDIO_CATHETER_CONTEXT,
    NON_CARDIAC_VALVE_EXCLUSIONS, CARDIAC_VALVE_CONTEXT, CARDIO_STENT_CONTEXT,
    STROKE_PATS, STROKE_NEURO_FOCUS_TERMS, AUDIT_NEURO_ANCHORS, AUDIT_CARDIO_ANCHORS, 
    AUDIT_IMMUNO_ANCHORS, AUDIT_MSK_ANCHORS, AUDIT_METABOLIC_ANCHORS, AUDIT_RARE_ANCHORS, AUDIT_INFECTIOUS_ANCHORS
)

@dataclass(frozen=True)
class TAFlag:
    nct_id: str
    assigned_ta: str
    expected_ta: str
    reason: str
    title: str
    conditions: List[str]

@dataclass(frozen=True)
class TAInfo:
    nct_id: str
    assigned_ta: str
    suggested_ta: str
    reason: str
    title: str
    conditions: List[str]

def _text(title: str | None, conditions: List[str] | None) -> str:
    parts: List[str] = []
    if title:
        parts.append(title)
    if conditions:
        for c in conditions:
            if c:
                parts.append(c)
    return " ".join(parts).lower()

def audit_trials(trials: Iterable[dict]) -> Tuple[List[TAFlag], List[TAInfo], Dict[str, int]]:
    flags: List[TAFlag] = []
    counts: Dict[str, int] = {}
    infos: List[TAInfo] = []

    def bump(reason: str) -> None:
        counts[reason] = counts.get(reason, 0) + 1

    for t in trials:
        nct = (t.get("nct_id") or "").strip()
        title = t.get("title") or ""
        conditions = t.get("conditions") or []
        assigned = (t.get("therapeutic_area") or "Unknown").strip()

        txt = _text(title, conditions)
        benign_guard = any(k in txt for k in BENIGN_GUARD_KWS)

        # PCI context → Cardiovascular
        pci_cardiac_context = ["coronary", "cardiac", "myocardial", "stemi", "mi ", "angioplasty", "stent", "cad"]
        if "pci" in txt and any(k in txt for k in pci_cardiac_context):
            expected = TA_CARDIO
            if assigned != expected:
                reason = "pci_cardiac_context_should_be_cardiovascular"
                flags.append(TAFlag(nct, assigned, expected, reason, title, conditions))
                bump(reason)
            continue

        # Cardio devices with context/exclusions
        device_hit = any(k in txt for k in ["stent", "angioplasty", "pacemaker", "defibrillator"])
        tavr_pat = re.compile(r"\btavr\b")
        tavi_pat = re.compile(r"\btavi\b")
        if not device_hit and (tavr_pat.search(txt) or tavi_pat.search(txt)):
            device_hit = True

        if not device_hit and "catheter" in txt:
            if any(x in txt for x in NON_CARDIO_CATHETER_EXCLUSIONS):
                pass
            elif any(k in txt for k in CARDIO_CATHETER_CONTEXT):
                device_hit = True

        if not device_hit and "valve" in txt:
            if any(x in txt for x in NON_CARDIAC_VALVE_EXCLUSIONS):
                pass
            elif any(k in txt for k in CARDIAC_VALVE_CONTEXT) or tavr_pat.search(txt) or tavi_pat.search(txt):
                device_hit = True

        if device_hit:
            if "stent" in txt or "stenting" in txt:
                if not any(k in txt for k in CARDIO_STENT_CONTEXT):
                    pass
                else:
                    expected = TA_CARDIO
                    if assigned != expected:
                        reason = "cardio_device_should_be_cardiovascular"
                        flags.append(TAFlag(nct, assigned, expected, reason, title, conditions))
                        bump(reason)
                    continue
            else:
                expected = TA_CARDIO
                if assigned != expected:
                    reason = "cardio_device_should_be_cardiovascular"
                    flags.append(TAFlag(nct, assigned, expected, reason, title, conditions))
                    bump(reason)
                continue

        # Pain syndromes alignment (INFO-only)
        cancer_kws = ["cancer", "tumor", "tumour", "carcinoma", "sarcoma", "lymphoma", "leukemia", "myeloma", "metastatic", "malignant", "oncology"]
        if not any(ck in txt for ck in cancer_kws):
            pdpn_hit = any(p.search(txt) for p in PDPN_PATS)
            pain_syndrome_hit = any(p.search(txt) for p in PAIN_SYNDROME_PATS)
            if pain_syndrome_hit and not pdpn_hit:
                has_anchor = (
                    any(k in txt for k in AUDIT_NEURO_ANCHORS) or
                    any(k in txt for k in AUDIT_CARDIO_ANCHORS) or
                    any(k in txt for k in AUDIT_IMMUNO_ANCHORS) or
                    any(k in txt for k in AUDIT_MSK_ANCHORS) or
                    any(k in txt for k in AUDIT_METABOLIC_ANCHORS) or
                    any(k in txt for k in AUDIT_RARE_ANCHORS) or
                    any(k in txt for k in AUDIT_INFECTIOUS_ANCHORS)
                )

                if has_anchor:
                    continue  # <-- do NOT create an INFO record

                if not has_anchor:
                    if ("fibromyalgia" in txt) or ("crps" in txt) or ("complex regional pain syndrome" in txt) or ("spinal cord stimulation" in txt) or ("scs" in txt) or ("neuromodulation" in txt) or ("neurostimulation" in txt) or ("stimulator" in txt) or ("phantom limb" in txt) or ("phantom limb pain" in txt):
                        suggested = TA_NEURO
                        reason = "info_pain_syndrome_expected_neurology___cns"
                    elif ("back pain" in txt) or ("low back pain" in txt) or ("myofascial pain" in txt) or ("subacromial" in txt) or ("patellofemoral" in txt) or ("patello femoral" in txt):
                        suggested = TA_MSK
                        reason = "info_pain_syndrome_expected_musculoskeletal"
                    else:
                        suggested = TA_OTHER
                        reason = "info_pain_syndrome_expected_other"

                infos.append(
                    TAInfo(
                        nct_id=nct,
                        assigned_ta=assigned,
                        suggested_ta=suggested,
                        reason=reason,
                        title=title,
                        conditions=conditions,
                    )
                )
                if assigned != suggested:
                    bump(reason)
                    # INFO-only; do not flag violation or continue

        # Brain tumors → Oncology
        brain_onco_kws = ["glioma", "glioblastoma", "gbm", "medulloblastoma", "ependymoma", "astrocytoma", "high grade glioma", "malignant glioma", "brain tumor", "brain cancer"]
        if any(k in txt for k in brain_onco_kws):
            expected = TA_ONCOLOGY
            if assigned != expected:
                reason = "brain_tumor_should_be_oncology"
                flags.append(TAFlag(nct, assigned, expected, reason, title, conditions))
                bump(reason)
            continue

        # Melanoma → Oncology (overrides Rare/Genetic if present)
        melanoma_kws = ["melanoma"]
        if any(k in txt for k in melanoma_kws) and not benign_guard:
            expected = TA_ONCOLOGY
            if assigned != expected:
                reason = "melanoma_should_be_oncology"
                flags.append(TAFlag(nct, assigned, expected, reason, title, conditions))
                bump(reason)
            continue

        # Stroke → Cardio by default; Neuro if CNS focus
        stroke_hit = any(p.search(title.lower()) for p in STROKE_PATS)
        if not stroke_hit and conditions:
            for c in conditions:
                if c and any(p.search(c.lower()) for p in STROKE_PATS):
                    stroke_hit = True
                    break
        if stroke_hit and ("cancer" not in txt):
            expected = TA_NEURO if any(k in txt for k in STROKE_NEURO_FOCUS_TERMS) else TA_CARDIO
            if assigned != expected:
                reason = "stroke_expected_" + ("neuro" if expected == TA_NEURO else "cardio")
                flags.append(TAFlag(nct, assigned, expected, reason, title, conditions))
                bump(reason)
            continue

        # Long COVID + neuro anchors → Neurology
        if ("long covid" in txt or "long covid-19" in txt or "long covid19" in txt) and any(
            kw in txt for kw in ["stroke", "parkinson", "multiple sclerosis", "ms "]
        ):
            expected = TA_NEURO
            if assigned != expected:
                reason = "long_covid_mixed_neuro_should_be_neuro"
                flags.append(TAFlag(nct, assigned, expected, reason, title, conditions))
                bump(reason)
            continue

        # Malignancy language → Oncology unless benign guard
        malignancy_kws = ["malignancy", "malignancies", "t cell malignancy", "blood cancer"]
        spread_kws = ["carcinomatosis", "metastases", "metastasis", "metastatic disease"]
        if (any(k in txt for k in malignancy_kws) or any(k in txt for k in spread_kws)) and not benign_guard:
            expected = TA_ONCOLOGY
            if assigned != expected:
                reason = "malignancy_language_should_be_oncology"
                flags.append(TAFlag(nct, assigned, expected, reason, title, conditions))
                bump(reason)
            continue

        # Osteoarthritis and MSK contexts → Musculoskeletal
        if any(k in txt for k in ["osteoarthritis", "hip osteoarthritis", "knee osteoarthritis", "arthroplasty", "hip arthroplasty", "knee arthroplasty", "total knee arthroplasty", "total hip arthroplasty"]) and not benign_guard:
            expected = TA_MSK
            if assigned != expected:
                reason = "osteoarthritis_should_be_msk"
                flags.append(TAFlag(nct, assigned, expected, reason, title, conditions))
                bump(reason)
            continue

    return flags, infos, counts