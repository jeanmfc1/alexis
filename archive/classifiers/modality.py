from __future__ import annotations

from storage.models import ClinicalTrialSignal

from classifiers.drug_non_drug import is_drug_trial

from typing import Dict, List

from policy.modality_policy import (
    PROCEDURE_TERMS,
    DEVICE_DIGITAL_TERMS,
    BEHAVIORAL_EXERCISE_TERMS,
    DRUG_LIKE_TERMS,
    has_drug_name_signal,
    _has_any,
)

import re

def assign_modality(trial: ClinicalTrialSignal) -> str:
    """
    Modality classifier v1.1 (rule-based, conservative)

    Buckets trials into:
    - Small Molecule
    - Procedure/Radiation
    - Device/Digital
    - Behavioral/Exercise
    - Observational/Diagnostic
    - Other/Unknown

    Notes:
    - Still NOT final biologic typing (mAb / ADC / oligo)
    - Optimized to correctly exclude non-drug trials from Small Molecule
    - Deterministic, ordered by intent
    """

    # 0) Observational studies
    if getattr(trial, "study_type", None) == "OBSERVATIONAL":
        return "Observational/Diagnostic"

    interventions = trial.interventions or []

    # Interventions may already be strings; assume list[str] for now
    raw_text = " ".join(interventions)
    text = raw_text.lower()

    # Drug vs non-drug boundary (phase 1 goal)
    if is_drug_trial(trial):
        return "Drug"

    if not text.strip():
        return "Other/Unknown"

    # 1) Procedure / radiation / surgery
    if any(term in text for term in PROCEDURE_TERMS):
        return "Procedure/Radiation"

    # 2) Device / digital / hardware / software
    if _has_any(text, DEVICE_DIGITAL_TERMS):
        return "Device/Digital"

    # 3) Behavioral / exercise / rehab / education
    if _has_any(text, BEHAVIORAL_EXERCISE_TERMS):
        return "Behavioral/Exercise"

    # 5) Default: if interventional and not clearly non-drug
    return "Other/Unknown"
