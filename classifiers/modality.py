from storage.models import ClinicalTrialSignal

def assign_modality(trial: ClinicalTrialSignal) -> str:
    """
    Modality classifier v1 (very simple, rule-based):

    Uses intervention names (strings) to bucket the trial into:
    - Small Molecule
    - Procedure/Radiation
    - Behavioral/Assessment
    - Observational/Diagnostic
    - Other/Unknown

    This is NOT final "mAb/ADC/oligo" logic yet.
    It's a first pass that correctly handles obvious non-drug trials.
    """
    # 0) Observational studies often have no structured interventions in CT.gov
    if getattr(trial, "study_type", None) == "OBSERVATIONAL":
        return "Observational/Diagnostic"

    interventions = trial.interventions or []
    text = " ".join(interventions).lower()

    if not text.strip():
        return "Other/Unknown"

    # 1) Procedure / radiation / surgery / device-like signals
    procedure_terms = [
        "radiotherapy", "radiation", "surgery", "surgical", "procedure",
        "implant", "device", "catheter", "stent", "ablation",
    ]
    if any(term in text for term in procedure_terms):
        return "Procedure/Radiation"

    # 2) Behavioral / assessment instruments
    behavioral_terms = [
        "questionnaire", "survey", "interview", "assessment",
        "cognitive", "behavioral", "behavioural",
    ]
    if any(term in text for term in behavioral_terms):
        return "Behavioral/Assessment"

    # 3) Drug-like signals (v1 heuristic)
    drug_terms = [
        "placebo", "tablet", "capsule", "mg", "dose", "oral",
        "infusion", "inject", "injection", "iv", "subcutaneous", "sc",
    ]
    if any(term in text for term in drug_terms):
        return "Small Molecule"

    # 4) Default: if interventions exist and not clearly non-drug, treat as drug-like for now
    return "Small Molecule"


from storage.models import ClinicalTrialSignal

from policy.modality_policy import (
    PROCEDURE_TERMS,
    DEVICE_DIGITAL_TERMS,
    BEHAVIORAL_EXERCISE_TERMS,
    DRUG_LIKE_TERMS,
)


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
    text = " ".join(interventions).lower()

    if not text.strip():
        return "Other/Unknown"

    # 1) Procedure / radiation / surgery
    if any(term in text for term in PROCEDURE_TERMS):
        return "Procedure/Radiation"

    # 2) Device / digital / hardware / software
    if any(term in text for term in DEVICE_DIGITAL_TERMS):
        return "Device/Digital"

    # 3) Behavioral / exercise / rehab / education
    if any(term in text for term in BEHAVIORAL_EXERCISE_TERMS):
        return "Behavioral/Exercise"

    # 4) Drug-like signals (still coarse)
    if any(term in text for term in DRUG_LIKE_TERMS):
        return "Small Molecule"

    # 5) Default: if interventional and not clearly non-drug
    return "Small Molecule"
