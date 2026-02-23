# ALEXIS/classifiers/therapeutic_area.py

from __future__ import annotations
from typing import Iterable, List, Optional, Dict
from storage.models_v2 import ClinicalTrialSignalV2
import re

from policy.ta_policy import (
    TA_ONCOLOGY, TA_INFECTIOUS, TA_IMMUNO, TA_NEURO, TA_CARDIO,
    TA_METABOLIC, TA_RARE, TA_MSK, TA_OTHER, TA_DENTAL, TA_DERMATOLOGY, TA_HEMATOLOGY,
    BENIGN_GUARD_KWS, STROKE_PATS,
    ONCOLOGY_KW, INFECTIOUS_KW, IMMUNO_KW, NEURO_KW, CARDIO_KW,
    METABOLIC_KW, RARE_KW, MSK_KW, DENTAL_KW, DERMATOLOGY_KW, HEMATOLOGY_KW, RESPIRATORY_KW,
    PAIN_SYNDROME_PATS, PDPN_PATS,
    NON_CARDIO_CATHETER_EXCLUSIONS, CARDIO_CATHETER_CONTEXT,
    NON_CARDIAC_VALVE_EXCLUSIONS, CARDIAC_VALVE_CONTEXT,
    CARDIO_STENT_CONTEXT, STROKE_NEURO_FOCUS_TERMS, TA_PSYCHIATRY,
    TA_GI, TA_RESPIRATORY, TA_OPHTHALMOLOGY, TA_UROLOGY, TA_NON_DISEASE,
    GI_KW, UROLOGY_KW, OPHTHALMOLOGY_KW, PSYCHIATRY_KW,
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
    # Use pre-cached text if available, otherwise compute
    text = getattr(trial, '_cached_title_conditions', None)
    if text is None:
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
    # Organ-system TAs (text anchors)
    if _has_any(text, GI_KW):
        return TA_GI
    if _has_any(text, UROLOGY_KW):
        return TA_UROLOGY
    if _has_any(text, OPHTHALMOLOGY_KW):
        return TA_OPHTHALMOLOGY
    # NEW: Additional specialty TAs
    if _has_any(text, RESPIRATORY_KW):
        return TA_RESPIRATORY
    if _has_any(text, DENTAL_KW):
        return TA_DENTAL
    if _has_any(text, DERMATOLOGY_KW):
        return TA_DERMATOLOGY
    if _has_any(text, HEMATOLOGY_KW):
        return TA_HEMATOLOGY
    if _has_any(text, PSYCHIATRY_KW):
        return TA_PSYCHIATRY

    return TA_OTHER

# ---------------------------------------------------------------------
# NEW: Multi-label TA detection using condition MeSH ancestry
# ---------------------------------------------------------------------

TA_MESH_ROOTS = {

    TA_ONCOLOGY: [
        {"id": "D009369", "term": "Neoplasms"},  # C04 ✓
    ],

    TA_IMMUNO: [
        {"id": "D007154", "term": "Immune System Diseases"},   # C20 ✓
        {"id": "D001327", "term": "Autoimmune Diseases"},      # C20.111 ✓
        {"id": "D006967", "term": "Hypersensitivity"},         # C20.543 ✓
        {"id": "D007249", "term": "Inflammation"},             # C23.550.470 — FIXED from D010437
    ],

    TA_NEURO: [
        {"id": "D009422", "term": "Nervous System Diseases"},  # C10 ✓
    ],

    TA_PSYCHIATRY: [
        {"id": "D001523", "term": "Mental Disorders"},             # F03 ✓
        {"id": "D003866", "term": "Depressive Disorder"},         # F03.600.300 — FIXED from D003863
        {"id": "D019966", "term": "Substance-Related Disorders"}, # C25.775/F03.900 — FIXED from D013493
    ],

    TA_CARDIO: [
        {"id": "D002318", "term": "Cardiovascular Diseases"},  # C14 ✓
    ],

    TA_METABOLIC: [
        {"id": "D009750", "term": "Nutritional and Metabolic Diseases"},  # C18 ✓
        {"id": "D004700", "term": "Endocrine System Diseases"},           # C19 ✓
    ],

    TA_GI: [
        {"id": "D004066", "term": "Digestive System Diseases"},  # C06 ✓
        {"id": "D005767", "term": "Gastrointestinal Diseases"},  # C06.405 ✓
        {"id": "D007410", "term": "Intestinal Diseases"},        # C06.405.469 ✓
        {"id": "D008107", "term": "Liver Diseases"},             # C06.552 ✓
    ],

    TA_RESPIRATORY: [
        {"id": "D012140", "term": "Respiratory Tract Diseases"},  # C08 ✓
    ],

    TA_OPHTHALMOLOGY: [
        {"id": "D005128", "term": "Eye Diseases"},     # C11 ✓
        {"id": "D014603", "term": "Uveal Diseases"},   # C11.941 ✓
        {"id": "D015862", "term": "Choroid Diseases"}, # C11.941.160 ✓
        {"id": "D012164", "term": "Retinal Diseases"}, # C11.768 — FIXED from D012121
    ],

    TA_UROLOGY: [
        {"id": "D000091642", "term": "Urogenital Diseases"},                                    # C12 ✓
        {"id": "D014570",    "term": "Urologic Diseases"},                                      # C12.050.351.968 — FIXED from D014607
        {"id": "D052776",    "term": "Female Urogenital Diseases"},                             # C12.050.351 ✓
        {"id": "D005261",    "term": "Female Urogenital Diseases and Pregnancy Complications"}, # C12.050 ✓
        {"id": "D005831",    "term": "Genital Diseases, Female"},                               # C12.050.351.500 ✓
        {"id": "D014591",    "term": "Uterine Diseases"},                                       # C12.050.351.500.852 ✓
        {"id": "D007674",    "term": "Kidney Diseases"},                                        # C12.050.351.968.419 ✓
    ],

    TA_MSK: [
        {"id": "D009140", "term": "Musculoskeletal Diseases"},  # C05 ✓
    ],

    TA_INFECTIOUS: [
        {"id": "D007239", "term": "Infections"},  # C01 ✓
    ],

    TA_RARE: [
        {"id": "D009358", "term": "Congenital, Hereditary, and Neonatal Diseases and Abnormalities"},  # C16 ✓
    ],

    TA_DENTAL: [
        {"id": "D009057", "term": "Stomatognathic Diseases"},  # C07 ✓
    ],

    TA_DERMATOLOGY: [
        {"id": "D012871", "term": "Skin Diseases"},  # C17.800 ✓
        {"id": "D003872", "term": "Dermatitis"},     # C17.800.174 — FIXED from D003875
    ],

    TA_HEMATOLOGY: [
        {"id": "D006425", "term": "Hemic and Lymphatic Diseases"},  # C15 ✓
    ],
}


# MeSH nodes that are symptom/manifestation categories — excluded from
# TA matching because they appear as ancestors of many non-disease
# conditions and would cause false TA assignments.
MESH_TRAVERSAL_EXCLUSIONS = {
    "D009461",  # Neurologic Manifestations (C10.597) — ancestor of pain,
                # nausea, vomiting, wounds; would falsely fire Neurology
}


def detect_therapeutic_area_evidence(
    trial: ClinicalTrialSignalV2,
) -> dict[str, list[dict]]:
    """
    Return mapping: TA -> list of matched MeSH roots (id + term).
    Used for audit and explainability.

    Checks both condition_meshes (the terms themselves) AND
    condition_mesh_ancestors. ct.gov's ancestor chain does not include
    the term itself, so a trial whose condition IS a root term would be
    missed if we only checked ancestors.

    IDs in MESH_TRAVERSAL_EXCLUSIONS are skipped — these are
    symptom/manifestation nodes that appear in ancestor chains of many
    non-disease conditions and would cause false TA matches.
    """
    evidence: Dict[str, List[Dict[str, str]]] = {}

    condition_ids = {
        m.id
        for m in (trial.condition_meshes or [])
        if hasattr(m, "id") and isinstance(m.id, str)
        and m.id not in MESH_TRAVERSAL_EXCLUSIONS
    }
    ancestor_ids = {
        a.id
        for a in (trial.condition_mesh_ancestors or [])
        if hasattr(a, "id") and isinstance(a.id, str)
        and a.id not in MESH_TRAVERSAL_EXCLUSIONS
    }
    all_ids = condition_ids | ancestor_ids

    for ta, roots in TA_MESH_ROOTS.items():
        matches = [r for r in roots if r["id"] in all_ids]
        if matches:
            evidence[ta] = matches

    return evidence
