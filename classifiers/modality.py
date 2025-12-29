from __future__ import annotations

from storage.models import ClinicalTrialSignal

from typing import Dict, List

from policy.modality_policy import (
    PROCEDURE_TERMS,
    DEVICE_DIGITAL_TERMS,
    BEHAVIORAL_EXERCISE_TERMS,
    DRUG_LIKE_TERMS,
    has_drug_name_signal,
)

import re

_SHORT_TOKEN_RE_CACHE: Dict[str, re.Pattern] = {}

def _has_any(text: str, terms: List[str]) -> bool:
    """
    Returns True if any term matches text.

    - Long terms: simple substring match (fast, safe)
    - Short alphabetic tokens (<=3 letters like ct/mri/pet): regex word-boundary match
      to avoid false positives like 'restriCTion' matching 'ct'.
    """
    for t in terms:
        if not t:
            continue

        t = t.lower()

        # Short alpha tokens are ambiguous as substrings. Require whole-token match.
        if len(t) <= 3 and t.isalpha():
            pat = _SHORT_TOKEN_RE_CACHE.get(t)
            if pat is None:
                # \b ensures t is a standalone token (ct, mri, pet), not inside another word
                pat = re.compile(rf"\b{re.escape(t)}\b")
                _SHORT_TOKEN_RE_CACHE[t] = pat
            if pat.search(text):
                return True
        else:
            if t in text:
                return True

    return False

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

    # 4) Drug-like signals (still coarse) + drug identifier patterns
    if _has_any(text, DRUG_LIKE_TERMS) or has_drug_name_signal(raw_text):
        return "Small Molecule"

    # 5) Default: if interventional and not clearly non-drug
    return "Other/Unknown"
