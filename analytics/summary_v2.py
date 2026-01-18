from storage.models_v2 import ClinicalTrialSignalV2

CTGOV_INTERVENTION_CATEGORIES = [
    "BEHAVIORAL",
    "BIOLOGICAL",
    "COMBINATION_PRODUCT",
    "DEVICE",
    "DIAGNOSTIC_TEST",
    "DIETARY_SUPPLEMENT",
    "DRUG",
    "GENETIC",
    "PROCEDURE",
    "RADIATION",
    "OTHER",
]


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

def study_type_summary_all_trials(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    """
    Count trials by CT.gov StudyType (INTERVENTIONAL, OBSERVATIONAL, etc.).
    Includes ALL trials.
    """
    counts: dict = {}

    for t in trials:
        st = t.study_type or "UNKNOWN"
        counts[st] = counts.get(st, 0) + 1

    return counts

def intervention_type_summary_all_trials(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    """
    CT.gov SOURCE-LAYER summary.

    Provides:
    1) Category participation counts (non-mutually exclusive)
    2) Unique NCT counts per category

    Valid ONLY immediately after normalization.
    NOT valid on snapshots or reclassified trials.
    """
    category_counts = {k: 0 for k in CTGOV_INTERVENTION_CATEGORIES}
    category_counts["NO_STRUCTURED_INTERVENTIONS"] = 0
    category_counts["UNEXPECTED"] = 0

    unique_nct_sets = {k: set() for k in CTGOV_INTERVENTION_CATEGORIES}
    unique_nct_sets["NO_STRUCTURED_INTERVENTIONS"] = set()
    unique_nct_sets["UNEXPECTED"] = set()

    has_interventions_all = hasattr(trials[0], "interventions_all")

    for t in trials:
        ivs = t.interventions_all if has_interventions_all else []
        nct = t.nct_id

        types = {
            iv.type.upper()
            for iv in ivs
            if isinstance(iv.type, str)
        }

        if not types:
            category_counts["NO_STRUCTURED_INTERVENTIONS"] += 1
            unique_nct_sets["NO_STRUCTURED_INTERVENTIONS"].add(nct)
            continue

        for tp in types:
            if tp in category_counts:
                category_counts[tp] += 1
                unique_nct_sets[tp].add(nct)
            else:
                category_counts["UNEXPECTED"] += 1
                unique_nct_sets["UNEXPECTED"].add(nct)

    unique_nct_counts = {
        k: len(v) for k, v in unique_nct_sets.items()
    }

    return {
        "_layer": "ctgov_source",
        "_requires": "interventions_all",
        "_valid_on_snapshots": False,
        "category_counts": category_counts,
        "unique_nct_counts": unique_nct_counts,
    }



