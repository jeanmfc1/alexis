"""
policy.modality_policy

Canonical modality labels + anchor vocab for Modality v1.x.

This policy file defines *what concepts exist* (labels + keyword anchors),
not classifier behavior / precedence.
"""

from __future__ import annotations

from typing import Dict, List

import re

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
    # Abbreviations (safe because _has_any uses word-boundaries for short tokens)
    "ct",
    "mri",
    "pet",
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
