"""
policy.modality_policy

Canonical modality labels + anchor vocab for Modality v1.x.

This policy file defines *what concepts exist* (labels + keyword anchors),
not classifier behavior / precedence.
"""

from __future__ import annotations

from typing import Dict, List, Iterable

import re

_SHORT_TOKEN_RE_CACHE = {}

def _is_short_token(term: str) -> bool:
    # short, all-alnum tokens like "mri", "ct", "pet", "iv"
    return 2 <= len(term) <= 4 and term.isalnum()

def _compile_short_token(term: str) -> re.Pattern:
    key = term.lower()
    rx = _SHORT_TOKEN_RE_CACHE.get(key)
    if rx is None:
        rx = re.compile(rf"\b{re.escape(key)}\b", re.IGNORECASE)
        _SHORT_TOKEN_RE_CACHE[key] = rx
    return rx

def _has_any(text: str, terms: Iterable[str]) -> bool:
    """
    Boundary-safe matching for short tokens; substring match for longer tokens.
    Intended for intervention-text matching across classifier and audit.
    """
    if not text:
        return False

    t = text.lower()
    for term in terms:
        if not term:
            continue
        s = term.lower()

        # Boundary-safe for short tokens (mri/ct/pet/iv)
        if _is_short_token(s):
            if _compile_short_token(s).search(t):
                return True
        else:
            if s in t:
                return True
    return False


# Drug identifier patterns (public-trial intervention strings often use codes or INN suffixes)
_DRUG_CODE_RE = re.compile(r"\b[A-Z]{2,6}[- ]?\d{2,6}\b")
_DRUG_SUFFIX_RE = re.compile(r"(mab|zumab|ximab|umab|omab|inib|parib|ciclib|vir)\b", re.IGNORECASE)

def has_drug_name_signal(raw_text: str) -> bool:
    """
    True if intervention text looks like a drug identifier (code-name or common drug suffix).
    Keep conservative: prioritize precision over recall.
    """
    if not raw_text or not raw_text.strip():
        return False
    return bool(_DRUG_CODE_RE.search(raw_text) or _DRUG_SUFFIX_RE.search(raw_text))


# --- Canonical labels (v1.x) ---
MODALITY_LABELS: List[str] = [
    "Drug",
    "Small Molecule",
    "Procedure/Radiation",
    "Device/Digital",
    "Behavioral/Exercise",
    "Observational/Diagnostic",
    "Other/Unknown",
]

# --- Anchor vocab (keep conservative; expand deliberately with tests) ---

PROCEDURE_TERMS: List[str] = [
    "radiotherapy",
    "radiation",
    "surgery",
    "surgical",
    "procedure",
    "ablation",
    "resection",
    "catheter",
    "stent",
    "implant",
    "biopsy",
    "endoscopy",
    "colonoscopy",
    "bronchoscopy",
    "laparoscopy",
    "arthroscopy",
    "angioplasty",
    "thrombectomy",
    "biospecimen collection",
]

DEVICE_DIGITAL_TERMS: List[str] = [
    # generic
    "device",
    "implant",
    "sensor",
    "wearable",
    "pump",
    "robot",
    "robotic",
    # common medical hardware / systems
    "cpap",
    "stimulation",
    "stimulator",
    "ultrasound",
    # Imaging and diagnostics (full names, high specificity)
    "computed tomography",
    "magnetic resonance imaging",
    "positron emission tomography",
    "echocardiography", "echocardiography test",
    "multigated acquisition scan",
    "bone scan",
    "x-ray imaging",
    "chest radiography",
    "radionuclide imaging",
    "diffusion tensor imaging (dti)",
    "audiometric test",
    # Abbreviations (safe because _has_any uses word-boundaries for short tokens)
    "ct",
    "mri",
    "pet",
    "dti",
    # digital health
    "app",
    "application",
    "software",
    "platform",
    "mhealth",
    "telehealth",
    "digital",
    "decision-support",
    "decision support",
    "tms",
    "tdcs",
    "tus",
    "focused ultrasound",
    "neurostimulation",
]

BEHAVIORAL_EXERCISE_TERMS: List[str] = [
    "behavioral",
    "behavioural",
    "exercise",
    "training",
    "rehabilitation",
    "physical activity",
    "physiotherapy",
    "physical therapy",
    "cbt",
    "cognitive",
    "counseling",
    "counselling",
    "education",
    "coaching",
    "mindfulness",
    # assessment instruments
    "questionnaire",
    "survey",
    "interview",
    "assessment",
    "electronic health record review",
]

DRUG_LIKE_TERMS: List[str] = [
    "placebo",
    "tablet",
    "capsule",
    "mg",
    "dose",
    "oral",
    "infusion",
    "inject",
    "injection",
    "iv",
    "subcutaneous",
    "sc",
]

# Convenient access if other modules want a mapping (audit, reporting, etc.)
ANCHORS: Dict[str, List[str]] = {
    "Procedure/Radiation": PROCEDURE_TERMS,
    "Device/Digital": DEVICE_DIGITAL_TERMS,
    "Behavioral/Exercise": BEHAVIORAL_EXERCISE_TERMS,
    "Small Molecule": DRUG_LIKE_TERMS,
}

# --- Drug identity policy (semantic, not lexical) ---

# Strong drug identity signals: these alone are sufficient
# Examples: code names, INN suffixes, biologic suffixes
DRUG_IDENTITY_REGEXES = [
    r"\b[a-z]{2,}-\d{2,}\b",          # code names like abx-101
    r"\b[a-z]+(mab|nib|statin|parib|ciclib|vir)\b",
]

# Dose units alone are NOT sufficient; they must be paired with route/form
DOSE_UNITS = ["mg", "mcg", "µg", "g", "iu", "units"]

DRUG_ROUTE_TERMS = [
    "tablet", "capsule", "oral",
    "iv", "intravenous",
    "subcutaneous", "sc",
    "injection", "inject",
    "infusion",
]

# Explicit exclusions (important!)
NON_DRUG_EXCLUSION_TERMS = [
    "placebo",
]
