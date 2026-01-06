from storage.models_v2 import ClinicalTrialSignalV2


# -------------------------------------------------
# TA × Modality counts (TRUE DRUG TRIALS ONLY)
# -------------------------------------------------

def ta_modality_counts_true_drugs(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    """
    Therapeutic Area × Modality counts for TRUE DRUG trials only.
    Non-drug trials are excluded.
    """
    counts: dict = {}

    for t in trials:
        if not t.is_drug_trial:
            continue  # critical: exclude non-drug trials

        ta = t.therapeutic_area or "Unknown"
        modality = t.modality or "Unknown"

        if ta not in counts:
            counts[ta] = {}

        counts[ta][modality] = counts[ta].get(modality, 0) + 1

    return counts


# -------------------------------------------------
# High-level drug vs non-drug counts
# -------------------------------------------------

def drug_trial_counts(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    """
    Global counts separating drug and non-drug trials.
    """
    total = len(trials)
    drug_trials = [t for t in trials if t.is_drug_trial]

    return {
        "total_trials": total,
        "drug_trials": len(drug_trials),
        "non_drug_trials": total - len(drug_trials),
        "drug_trials_with_unknown_modality": sum(
            1 for t in drug_trials if t.modality is None
        ),
    }


# -------------------------------------------------
# INFO flag counts (TRUE DRUG TRIALS ONLY)
# -------------------------------------------------

def info_flag_counts_true_drugs(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    """
    Count INFO flags for TRUE DRUG trials only.
    """
    counts: dict = {}

    for t in trials:
        if not t.is_drug_trial:
            continue  # critical: exclude non-drug trials

        for flag in t.info_flags or []:
            counts[flag] = counts.get(flag, 0) + 1

    return counts


# -------------------------------------------------
# Drug INFO overview (sanity anchor)
# -------------------------------------------------

def drug_info_overview(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    """
    Compact overview to understand INFO flags impact
    on TRUE DRUG trials.
    """
    drug_trials = [t for t in trials if t.is_drug_trial]

    return {
        "drug_trials_total": len(drug_trials),
        "drug_trials_with_info_flags": sum(
            1 for t in drug_trials if t.info_flags
        ),
        "drug_trials_with_unknown_modality": sum(
            1 for t in drug_trials if t.modality is None
        ),
        "drug_trials_unknown_with_info": sum(
            1
            for t in drug_trials
            if t.modality is None and t.info_flags
        ),
    }
