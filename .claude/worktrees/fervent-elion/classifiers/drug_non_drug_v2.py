# details: uses trial.interventions from normalize_v2 to determine drug vs non-drug with no fallback

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # TYPE_CHECKING avoids import cycles at runtime
    from storage.models_v2 import ClinicalTrialSignalV2


def is_drug_trial_v2(trial: "ClinicalTrialSignalV2") -> bool:
    """
    Broad drug vs non-drug classifier.

    Rules:
    1) Only INTERVENTIONAL studies can be drug trials
    2) Role-agnostic: experimental, placebo, control all count
    3) Intervention types are preserved
    """

    # ---- StudyType gate (hard filter) ----
    if trial.study_type != "INTERVENTIONAL":
        return False

    # ---- Broad intervention-type gate ----
    drug_like_types = {
        "DRUG",
        "BIOLOGICAL",
        "COMBINATION_PRODUCT",
        "GENETIC",
    }

    types_present = {
        iv.type.upper()
        for iv in (trial.interventions_all or [])
        if isinstance(iv.type, str)
    }

    return bool(types_present & drug_like_types)

