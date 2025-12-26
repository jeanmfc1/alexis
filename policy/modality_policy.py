"""
policy.modality_policy

Canonical modality labels + anchor vocab for Modality v1.x.

This policy file defines *what concepts exist* (labels + keyword anchors),
not classifier behavior / precedence.
"""

from __future__ import annotations

from typing import Dict, List

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
    # imaging (often diagnostic / procedure-adjacent, but treat as device/digital in v1)
    "mri",
    "ct",
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
