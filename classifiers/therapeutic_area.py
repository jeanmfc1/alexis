# ALEXIS/classifiers/therapeutic_area.py

from __future__ import annotations
from typing import Iterable, List, Optional, Dict
from storage.models_v2 import ClinicalTrialSignalV2
import re

from policy.ta_policy import (
    TA_ONCOLOGY, TA_INFECTIOUS, TA_IMMUNO, TA_NEURO, TA_CARDIO,
    TA_METABOLIC, TA_RARE, TA_MSK, TA_OTHER,
    BENIGN_GUARD_KWS, STROKE_PATS,
    ONCOLOGY_KW, INFECTIOUS_KW, IMMUNO_KW, NEURO_KW, CARDIO_KW,
    METABOLIC_KW, RARE_KW, MSK_KW,
    PAIN_SYNDROME_PATS, PDPN_PATS,
    NON_CARDIO_CATHETER_EXCLUSIONS, CARDIO_CATHETER_CONTEXT,
    NON_CARDIAC_VALVE_EXCLUSIONS, CARDIAC_VALVE_CONTEXT,
    CARDIO_STENT_CONTEXT, STROKE_NEURO_FOCUS_TERMS, TA_PSYCHIATRY,
    TA_GI, TA_RESPIRATORY, TA_OPHTHALMOLOGY, TA_UROLOGY, TA_NON_DISEASE,
)

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

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

# ---------------------------------------------------------------------
# EXISTING single-label TA assignment (UNCHANGED)
# ---------------------------------------------------------------------

def assign_therapeutic_area(trial: ClinicalTrialSignalV2) -> str | None:
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

    # Devices / cardio context
    if ("stent" in text or "stenting" in text) and any(ctx in text for ctx in CARDIO_STENT_CONTEXT):
        return TA_CARDIO
    if "catheter" in text and not any(x in text for x in NON_CARDIO_CATHETER_EXCLUSIONS):
        if any(k in text for k in CARDIO_CATHETER_CONTEXT):
            return TA_CARDIO
    if "valve" in text and not any(x in text for x in NON_CARDIAC_VALVE_EXCLUSIONS):
        if any(k in text for k in CARDIAC_VALVE_CONTEXT) or ("tavr" in text) or ("tavi" in text):
            return TA_CARDIO

    # Neuromodulation / neurostimulation
    if any(k in text for k in [
        "neuromodulation", "neurostimulation",
        "spinal cord stimulation", "spinal cord stimulator",
        "scs", "dorsal root ganglion", "drg stimulation",
        "peripheral nerve stimulation", "pns",
    ]):
        return TA_NEURO

    # Oncology (guarded)
    if not benign_guard and _has_any(text, ONCOLOGY_KW):
        return TA_ONCOLOGY

    # Stroke routing
    stroke_hit = any(p.search(text) for p in STROKE_PATS)
    if stroke_hit and ("cancer" not in text):
        if any(k in text for k in STROKE_NEURO_FOCUS_TERMS):
            return TA_NEURO
        return TA_CARDIO

    # Pain syndromes
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
            if any(k in text for k in [
                "neuromodulation", "neurostimulation",
                "spinal cord stimulation", "scs",
                "stimulator", "fibromyalgia", "crps",
                "complex regional pain syndrome",
            ]):
                return TA_NEURO
            if "back pain" in text or "low back pain" in text or "myofascial pain" in text:
                return TA_MSK
            if "chronic pain" in text:
                return TA_OTHER

    # MSK before Immunology
    if _has_any(text, MSK_KW):
        return TA_MSK

    # Preferred order
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

# ---------------------------------------------------------------------
# NEW: Multi-label TA detection using condition MeSH ancestry
# ---------------------------------------------------------------------

TA_MESH_ROOTS = {

    # -----------------------------
    # Oncology
    # -----------------------------
    TA_ONCOLOGY: [
        {"id": "D009369", "term": "Neoplasms"},
    ],

    # -----------------------------
    # Immunology / Inflammation
    # -----------------------------
    TA_IMMUNO: [
        {"id": "D007154", "term": "Immune System Diseases"},
        {"id": "D001327", "term": "Autoimmune Diseases"},
        {"id": "D006967", "term": "Hypersensitivity"},
        {"id": "D010437", "term": "Inflammation"},
        {"id": "D012871", "term": "Skin Diseases"},              # immune-mediated subset
        {"id": "D003875", "term": "Dermatitis"},                # inflammatory skin disease
        {"id": "D006425", "term": "Hemic and Lymphatic Diseases"},  # immune hematology
    ],

    # -----------------------------
    # Neurology / CNS
    # -----------------------------
    TA_NEURO: [
        {"id": "D009422", "term": "Nervous System Diseases"},
        {"id": "D002493", "term": "Central Nervous System Diseases"},
    ],

    # -----------------------------
    # Psychiatry
    # -----------------------------
    TA_PSYCHIATRY: [
        {"id": "D001523", "term": "Mental Disorders"},
        {"id": "D009422", "term": "Mood Disorders"},
        {"id": "D003863", "term": "Depressive Disorder"},
        {"id": "D013493", "term": "Substance-Related Disorders"},
    ],

    # -----------------------------
    # Cardiovascular
    # -----------------------------
    TA_CARDIO: [
        {"id": "D002318", "term": "Cardiovascular Diseases"},
    ],

    # -----------------------------
    # Metabolic / Endocrine
    # -----------------------------
    TA_METABOLIC: [
        {"id": "D008659", "term": "Metabolic Diseases"},
        {"id": "D009750", "term": "Nutritional and Metabolic Diseases"},
        {"id": "D004700", "term": "Endocrine System Diseases"},   # IMPORTANT ADD
    ],

    # -----------------------------
    # Gastrointestinal / Hepatic
    # -----------------------------
    TA_GI: [
        {"id": "D004064", "term": "Digestive System Diseases"},
        {"id": "D008099", "term": "Liver Diseases"},
    ],

    # -----------------------------
    # Respiratory
    # -----------------------------
    TA_RESPIRATORY: [
        {"id": "D012140", "term": "Respiratory Tract Diseases"},
        {"id": "D008171", "term": "Lung Diseases"},
    ],

    # -----------------------------
    # Ophthalmology
    # -----------------------------
    TA_OPHTHALMOLOGY: [
        {"id": "D005128", "term": "Eye Diseases"},
        {"id": "D012121", "term": "Retinal Diseases"},
    ],

    # -----------------------------
    # Urology
    # -----------------------------
    TA_UROLOGY: [
        {"id": "D014596", "term": "Urogenital Diseases"},
        {"id": "D014607", "term": "Urologic Diseases"},
    ],

    # -----------------------------
    # Musculoskeletal
    # -----------------------------
    TA_MSK: [
        {"id": "D009140", "term": "Musculoskeletal Diseases"},
    ],

    # -----------------------------
    # Infectious Disease
    # -----------------------------
    TA_INFECTIOUS: [
        {"id": "D007239", "term": "Infections"},
    ],

    # -----------------------------
    # Rare / Genetic
    # -----------------------------
    TA_RARE: [
        {"id": "D030342", "term": "Genetic Diseases, Inborn"},
        {"id": "D009358", "term": "Congenital, Hereditary, and Neonatal Diseases and Abnormalities"},
    ],
}


def detect_therapeutic_area_evidence(
    trial: ClinicalTrialSignalV2,
) -> dict[str, list[dict]]:

    """
    Return mapping: TA -> list of matched MeSH roots (id + term).
    Used for audit and explainability.
    """
    evidence: Dict[str, List[Dict[str, str]]] = {}

    ancestors = trial.condition_mesh_ancestors or []
    ancestor_ids = {
        a.id
        for a in ancestors
        if hasattr(a, "id") and isinstance(a.id, str)
    }

    for ta, roots in TA_MESH_ROOTS.items():
        matches = [r for r in roots if r["id"] in ancestor_ids]
        if matches:
            evidence[ta] = matches

    return evidence
