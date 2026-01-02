# details: uses trial.interventions from normalize_v2 to determine drug vs non-drug with no fallback

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # TYPE_CHECKING avoids import cycles at runtime
    from storage.models_v2 import ClinicalTrialSignalV2


def is_drug_trial_v2(trial: "ClinicalTrialSignalV2") -> bool:
    """
    Return True if the normalized trial has at least one experimental drug intervention.
    This strict classifier has no fallback. It does NOT use text heuristics or MeSH.
    
    Args:
        trial: a ClinicalTrialSignalV2 object from normalize_v2
    
    Returns:
        bool: True if any experimental drug present, False otherwise
    """
    # trial.interventions now contains only experimental drug interventions
    # because normalize_v2 filtered out controls and non-drugs.
    return bool(trial.interventions)
