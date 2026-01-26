from storage.models_v2 import ClinicalTrialSignalV2
from policy.text_modality_policy_v2 import text_modality_from_text
import re

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

    Counts number of trials that include at least one intervention
    of each CT.gov intervention category.

    Notes:
    - Categories are NOT mutually exclusive.
    - Each trial contributes at most once per category.
    - Valid ONLY immediately after normalization.
    - NOT valid on snapshots or reclassified trials.
    """
    category_counts = {k: 0 for k in CTGOV_INTERVENTION_CATEGORIES}
    category_counts["NO_STRUCTURED_INTERVENTIONS"] = 0
    category_counts["UNEXPECTED"] = 0

    has_interventions_all = hasattr(trials[0], "interventions_all")

    for t in trials:
        ivs = t.interventions_all if has_interventions_all else []

        types = {
            iv.type.upper()
            for iv in ivs
            if isinstance(iv.type, str)
        }

        if not types:
            category_counts["NO_STRUCTURED_INTERVENTIONS"] += 1
            continue

        for tp in types:
            if tp in category_counts:
                category_counts[tp] += 1
            else:
                category_counts["UNEXPECTED"] += 1

    return {
        "_layer": "ctgov_source",
        "_requires": "interventions_all",
        "_valid_on_snapshots": False,
        "trials_with_category": category_counts,
    }

def drug_modality_summary(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    """
    Count drug trials by modality.

    Each drug trial (NCT) is counted exactly once.
    """
    counts: dict[str, int] = {}

    for t in trials:
        if not t.is_drug_trial:
            continue

        modality = t.modality or "UNASSIGNED"
        counts[modality] = counts.get(modality, 0) + 1

    return counts

def drug_therapeutic_area_summary(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    """
    Count drug trials by primary therapeutic area.

    Each drug trial (NCT) is counted exactly once.
    """
    counts: dict[str, int] = {}

    for t in trials:
        if not t.is_drug_trial:
            continue

        ta = t.therapeutic_area or "UNASSIGNED"
        counts[ta] = counts.get(ta, 0) + 1

    return counts

def drug_modality_provenance_summary(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    """
    Count how drug modality was derived:
    - mesh
    - text_fallback
    - base_only
    """
    counts = {
        "mesh": 0,
        "text_fallback": 0,
        "base_only": 0,
    }

    for t in trials:
        if not t.is_drug_trial:
            continue

        mesh_available = bool(t.intervention_meshes)
        has_info_flag = bool(t.info_flags)

        if mesh_available and not has_info_flag:
            # mesh used successfully
            counts["mesh"] += 1
        elif has_info_flag:
            # mesh present but failed → text or base
            # disambiguate text vs base
            text_blob = " ".join((t.interventions_text or []) + [t.title or ""])
            text_hit = text_modality_from_text(text_blob, t.modality)

            if text_hit:
                counts["text_fallback"] += 1
            else:
                counts["base_only"] += 1
        else:
            # no mesh at all → base or text
            counts["base_only"] += 1

    return counts

def drug_ta_provenance_summary(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    """
    Count how therapeutic area was derived for drug trials.
    """
    counts = {
        "mesh": 0,
        "text_fallback": 0,
        "multi_ta_mesh": 0,
    }

    for t in trials:
        if not t.is_drug_trial:
            continue

        if t.therapeutic_areas_detected:
            counts["mesh"] += 1
            if len(t.therapeutic_areas_detected) > 1:
                counts["multi_ta_mesh"] += 1
        else:
            counts["text_fallback"] += 1

    return counts

def drug_study_intent_summary(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    """
    Split drug trials into disease vs non-disease intent.
    """
    counts = {
        "disease": 0,
        "non_disease": 0,
    }

    for t in trials:
        if not t.is_drug_trial:
            continue

        if t.condition_meshes:
            counts["disease"] += 1
        else:
            counts["non_disease"] += 1

    return counts

PK_REGEX = re.compile(
    r"\bpharmacokinetic(s)?\b|\bpk study\b|\bpk analysis\b|\bpk evaluation\b",
    re.IGNORECASE,
)
PKPD_REGEX = re.compile(
    r"\bpk\/pd\b|\bpharmacokinetic(s)? and pharmacodynamic(s)?\b",
    re.IGNORECASE,
)
BA_BE_REGEX = re.compile(
    r"\bbioavailability\b|\bbioequivalence\b",
    re.IGNORECASE,
)
DDI_REGEX = re.compile(
    r"\bdrug[- ]drug interaction(s)?\b|\bddi study\b",
    re.IGNORECASE,
)
ORGAN_IMPAIRMENT_REGEX = re.compile(
    r"\brenal impairment\b|\bhepatic impairment\b",
    re.IGNORECASE,
)
HV_REGEX = re.compile(
    r"\bhealthy volunteer(s)?\b|\bhealthy subject(s)?\b",
    re.IGNORECASE,
)

def non_disease_drug_subtype_summary(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    """
    Subclassify non-disease drug studies by intent.
    """
    counts: dict[str, int] = {}

    for t in trials:
        if not t.is_drug_trial:
            continue

        if t.therapeutic_area != TA_NON_DISEASE:
            continue

        text = " ".join(
            (t.interventions_text or []) +
            [t.title or ""]
        ).lower()

        if DDI_REGEX.search(text):
            subtype = "DDI"
        elif BA_BE_REGEX.search(text):
            subtype = "BA/BE"
        elif PK_REGEX.search(text) or PKPD_REGEX.search(text):
            subtype = "PK"
        elif ORGAN_IMPAIRMENT_REGEX.search(text):
            subtype = "Organ impairment"
        elif HV_REGEX.search(text):
            subtype = "Healthy volunteers"
        elif "formulation" in text or "delivery" in text:
            subtype = "Formulation"
        else:
            subtype = "Other non-disease"

        counts[subtype] = counts.get(subtype, 0) + 1

    return counts

def ta_by_phase(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    counts = {}

    for t in trials:
        if not t.is_drug_trial:
            continue

        ta = t.therapeutic_area
        phase = t.phase or "UNKNOWN"

        counts.setdefault(ta, {})
        counts[ta][phase] = counts[ta].get(phase, 0) + 1

    return counts

def modality_by_phase(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    counts = {}

    for t in trials:
        if not t.is_drug_trial:
            continue

        modality = t.modality
        phase = t.phase or "UNKNOWN"

        counts.setdefault(modality, {})
        counts[modality][phase] = counts[modality].get(phase, 0) + 1

    return counts

def ta_by_sponsor_class(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    counts = {}

    for t in trials:
        if not t.is_drug_trial:
            continue

        ta = t.therapeutic_area
        sponsor = t.sponsor_class or "UNKNOWN"

        counts.setdefault(ta, {})
        counts[ta][sponsor] = counts[ta].get(sponsor, 0) + 1

    return counts

def multi_ta_rate_by_phase(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    totals = {}
    multi = {}

    for t in trials:
        if not t.is_drug_trial:
            continue

        phase = t.phase or "UNKNOWN"
        totals[phase] = totals.get(phase, 0) + 1

        if (
            hasattr(t, "therapeutic_areas_detected")
            and t.therapeutic_areas_detected
            and len(t.therapeutic_areas_detected) > 1
        ):
            multi[phase] = multi.get(phase, 0) + 1

    return {
        phase: multi.get(phase, 0) / totals[phase]
        for phase in totals
    }


