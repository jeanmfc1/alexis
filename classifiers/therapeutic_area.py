# ALEXIS/classifiers/therapeutic_area.py

from __future__ import annotations
from typing import Iterable, List, Optional
from storage.models import ClinicalTrialSignal
import re

from policy.ta_policy import (
    TA_ONCOLOGY, TA_INFECTIOUS, TA_IMMUNO, TA_NEURO, TA_CARDIO, TA_METABOLIC, TA_RARE, TA_MSK, TA_OTHER,
    BENIGN_GUARD_KWS, STROKE_PATS,
    ONCOLOGY_KW, INFECTIOUS_KW, IMMUNO_KW, NEURO_KW, CARDIO_KW, METABOLIC_KW, RARE_KW, MSK_KW,
    PAIN_SYNDROME_PATS, PDPN_PATS,
    NON_CARDIO_CATHETER_EXCLUSIONS, CARDIO_CATHETER_CONTEXT,
    NON_CARDIAC_VALVE_EXCLUSIONS, CARDIAC_VALVE_CONTEXT, CARDIO_STENT_CONTEXT,
    STROKE_NEURO_FOCUS_TERMS,
)

def _norm_text(title: Optional[str], conditions: Optional[Iterable[str]]) -> str:
    parts: List[str] = []
    if title:
        parts.append(title)
    if conditions:
        for c in conditions:
            if c:
                parts.append(str(c))
    return " ".join(parts).lower()

def _has_any(text: str, keywords: Iterable[str]) -> bool:
    return any(kw in text for kw in keywords)

def assign_therapeutic_area(trial: ClinicalTrialSignal) -> str:
    text = _norm_text(trial.title, trial.conditions)
    if not text.strip():
        return TA_OTHER

    benign_guard = any(k in text for k in BENIGN_GUARD_KWS)

    # Infectious carveouts
    if ("tuberculous meningitis" in text) or ("tuberculosis" in text and "meningitis" in text):
        return TA_INFECTIOUS
    if " tb " in f" {text} ":
        return TA_INFECTIOUS

    # TNF is immunology, not oncology
    if "tumor necrosis factor" in text or "tnf inhibitor" in text or "tnf inhibitors" in text:
        return TA_IMMUNO

    # Long COVID + strong neuro anchors -> Neurology
    if ("long covid" in text or "long covid19" in text or "long covid-19" in text) and any(
        kw in text for kw in ["stroke", "parkinson", "multiple sclerosis", "ms "]
    ):
        return TA_NEURO

    # Devices/valves/catheters: require cardio context and exclude non-cardio uses
    if ("stent" in text or "stenting" in text) and any(ctx in text for ctx in CARDIO_STENT_CONTEXT):
        return TA_CARDIO
    if "catheter" in text and not any(x in text for x in NON_CARDIO_CATHETER_EXCLUSIONS):
        if any(k in text for k in CARDIO_CATHETER_CONTEXT):
            return TA_CARDIO
    if "valve" in text and not any(x in text for x in NON_CARDIAC_VALVE_EXCLUSIONS):
        if any(k in text for k in CARDIAC_VALVE_CONTEXT) or ("tavr" in text) or ("tavi" in text):
            return TA_CARDIO
            
    # Neuromodulation / neurostimulation -> Neurology / CNS
    # This must NOT depend on pain_syndrome_hit, because many trials just say "Pain"
    # while the intervention/approach is clearly CNS-directed.
    if any(k in text for k in [
        "neuromodulation",
        "neurostimulation",
        "spinal cord stimulation",
        "spinal cord stimulator",
        "scs",
        "dorsal root ganglion",
        "drg stimulation",
        "peripheral nerve stimulation",
        "pns",
    ]):
        return TA_NEURO

    # Oncology first (broad domain), respect benign guard
    if not benign_guard and _has_any(text, ONCOLOGY_KW):
        return TA_ONCOLOGY

    # Stroke -> Cardio by default; Neuro if CNS focus
    stroke_hit = any(p.search(text) for p in STROKE_PATS)
    if stroke_hit and ("cancer" not in text):
        if any(k in text for k in STROKE_NEURO_FOCUS_TERMS):
            return TA_NEURO
        return TA_CARDIO

    # Pain syndromes routing
    pdpn_hit = any(p.search(text) for p in PDPN_PATS)
    pain_syndrome_hit = any(p.search(text) for p in PAIN_SYNDROME_PATS)
    if pain_syndrome_hit:
        has_strong_anchor = (
            _has_any(text, METABOLIC_KW) or _has_any(text, IMMUNO_KW) or
            _has_any(text, NEURO_KW) or _has_any(text, CARDIO_KW) or
            _has_any(text, INFECTIOUS_KW) or _has_any(text, RARE_KW)
        )
        if pdpn_hit and _has_any(text, METABOLIC_KW):
            return TA_METABOLIC
        if not has_strong_anchor:
            if any(k in text for k in ["neuromodulation", "neurostimulation", "spinal cord stimulation", "scs", "stimulator", "fibromyalgia", "crps", "complex regional pain syndrome"]):
                return TA_NEURO
            if "back pain" in text or "low back pain" in text or "myofascial pain" in text:
                return TA_MSK
            if "chronic pain" in text:
                return TA_OTHER

    # Musculoskeletal direct anchors (OA, arthroplasty, mechanical pain) before Immunology
    if _has_any(text, MSK_KW):
        return TA_MSK

    # Preferred order to avoid leakage
    if _has_any(text, CARDIO_KW):
        return TA_CARDIO
    if _has_any(text, INFECTIOUS_KW):
        return TA_INFECTIOUS
    if _has_any(text, IMMUNO_KW):
        return TA_IMMUNO
    if _has_any(text, NEURO_KW):
        return TA_NEURO
    if _has_any(text, METABOLIC_KW):
        return TA_METABOLIC
    if _has_any(text, RARE_KW):
        return TA_RARE

    return TA_OTHER