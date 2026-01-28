from storage.models_v2 import ClinicalTrialSignalV2
from policy.text_modality_policy_v2 import text_modality_from_text
from policy.ta_policy import TA_NON_DISEASE
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

        intent = getattr(t, "study_intent", None)
        if intent == "non_disease":
            counts["non_disease"] += 1
        elif intent == "disease":
            counts["disease"] += 1

    return counts

# -------------------------------------------------
# Non-disease study categories (trial-level)
# -------------------------------------------------

CAT_SAFETY = "Safety & Tolerability Characterization (Non-escalation)"
CAT_PROCEDURAL = "Procedural / Perioperative Analgesia & Anesthesia"
CAT_PK = "Clinical Pharmacokinetics (PK / Exposure)"
CAT_ESC = "Phase I Dose Escalation & Tolerability (SAD/MAD/FIH)"
CAT_FORM = "Formulation / Delivery Optimization"
CAT_BIOM = "Biomarker / Imaging / Method Validation (Drug-involved)"
CAT_BABE = "Bioavailability / Bioequivalence (BA/BE)"
CAT_DDI = "Drug–Drug Interaction (DDI)"
CAT_MOA = "Mechanism of Action / Target Engagement (Non-disease)"
CAT_ADME = "ADME / Mass Balance"
CAT_FOOD = "Food Effect"
CAT_ORGAN_IMPAIR = "Organ Impairment (Renal/Hepatic)"
CAT_HV = "Healthy Volunteers (Non-disease)"

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

SAD_MAD_REGEX = re.compile(
    r"\bsingle\s+ascending\s+dose\b|\bmultiple\s+ascending\s+dose\b|\bSAD\b|\bMAD\b",
    re.IGNORECASE,
)

DOSE_ESCALATION_REGEX = re.compile(
    r"\bdose\s+escalation\b|\bdose\s+expansion\b|\bdose[-\s]?ranging\b",
    re.IGNORECASE,
)

FIH_REGEX = re.compile(
    r"\bfirst[-\s]?in[-\s]?human\b|\bFIH\b",
    re.IGNORECASE,
)

FOOD_EFFECT_REGEX = re.compile(
    r"\bfood[-\s]?effect\b|\bfed\b.*\bfasted\b|\bhigh[-\s]?fat\b",
    re.IGNORECASE,
)

QT_REGEX = re.compile(
    r"\bQTc?\b|\bthorough\s+QT\b|\bTQT\b",
    re.IGNORECASE,
)

ADME_REGEX = re.compile(
    r"\bADME\b|\bmass\s+balance\b|\bradiolabeled\b|\bcarbon[-\s]?14\b|\b14C\b",
    re.IGNORECASE,
)

# Procedural / pain / anesthesia anchors
PROCEDURAL_REGEX = re.compile(
    r"\bnerve block\b|\bgenicular\b|\bregional anesth|\banesthe|\bprocedural sedation\b|"
    r"\bpostoperative\b|\bperioperative\b|\banalges",
    re.IGNORECASE,
)

# Delivery/formulation anchors (separate from BA/BE)
FORMULATION_REGEX = re.compile(
    r"\bformulation\b|\bpatch\b|\btransdermal\b|\bophthalmic\b|\bnasal\b|\bspray\b|"
    r"\bautoinjector\b|\bpre[- ]filled\b|\bon[- ]body injector\b|\bprefilled syringe\b|"
    r"\binfusion pump\b",
    re.IGNORECASE,
)

# Biomarker / imaging / method validation anchors
BIOMARKER_REGEX = re.compile(
    r"\bbiomarker\b|\bassay\b|\bmonitoring\b|\bdiagnos|\bimaging\b|\bpet\b|\bmri\b|"
    r"\bultrasound\b|\bspect\b|\breader\b|\bconspicuity\b|\bcontrast\b",
    re.IGNORECASE,
)

# MOA / target engagement anchors (keep conservative)
MOA_REGEX = re.compile(
    r"\bmechanism\b|\btarget\b|\breceptor\b|\boccupancy\b|\bpathway\b|\binhibition\b|\bactivation\b|"
    r"\bcxcr4\b|\brage\b|\bcd38\b|\bcomplement[- ]mediated\b",
    re.IGNORECASE,
)

def has_enabling_signal(t: ClinicalTrialSignalV2) -> bool:
    """
    True if title/interventions_text contain explicit enabling-study intent
    (PK/PD, BA/BE, DDI, organ impairment, HV, SAD/MAD/FIH, food effect,
     QT/QTc, ADME, formulation/delivery, procedural anesthesia, biomarkers,
     MOA/target engagement).
    Deterministic and conservative.
    """
    text = " ".join((t.interventions_text or []) + [t.title or ""]).lower()

    return bool(
        # Core PK/PD / BA/BE / DDI
        DDI_REGEX.search(text)
        or BA_BE_REGEX.search(text)
        or PK_REGEX.search(text)
        or PKPD_REGEX.search(text)

        # Organ impairment / HV
        or ORGAN_IMPAIRMENT_REGEX.search(text)
        or HV_REGEX.search(text)

        # SAD/MAD/FIH / dose escalation
        or SAD_MAD_REGEX.search(text)
        or DOSE_ESCALATION_REGEX.search(text)
        or FIH_REGEX.search(text)

        # Food effect
        or FOOD_EFFECT_REGEX.search(text)

        # QT / cardiac safety
        or QT_REGEX.search(text)

        # ADME / mass balance
        or ADME_REGEX.search(text)

        # Procedural anesthesia / nerve block
        or PROCEDURAL_REGEX.search(text)

        # Formulation / delivery systems
        or FORMULATION_REGEX.search(text)

        # Biomarker / imaging / assay validation
        or BIOMARKER_REGEX.search(text)

        # MOA / target engagement
        or MOA_REGEX.search(text)

        # Simple string fallbacks
        or ("formulation" in text)
        or ("delivery" in text)
    )

def assign_non_disease_study_category(
    t: ClinicalTrialSignalV2,
) -> tuple[str, list[str]]:
    """
    Assign a non-disease study category with evidence strings.

    IMPORTANT:
    - Deterministic
    - Precedence-based
    - Evidence is the list of rule labels that matched
    - If no anchors match, classify as safety/tolerability characterization by exclusion
    """

    text = " ".join((t.interventions_text or []) + [t.title or ""]).lower()

    evidence: list[str] = []

    # Precedence order MUST match the exported 239 results:
    # procedural → ADME → DDI → food → BA/BE → formulation → SAD/MAD/FIH → PK → biomarker → MOA → safety(exclusion)

    if PROCEDURAL_REGEX.search(text):
        evidence.append("procedural: PROCEDURAL_REGEX")
        return (CAT_PROCEDURAL, evidence)

    if ADME_REGEX.search(text):
        evidence.append("adme: ADME_REGEX")
        return (CAT_ADME, evidence)

    if DDI_REGEX.search(text):
        evidence.append("ddi: DDI_REGEX")
        return (CAT_DDI, evidence)

    if FOOD_EFFECT_REGEX.search(text):
        evidence.append("food_effect: FOOD_EFFECT_REGEX")
        return (CAT_FOOD, evidence)

    if BA_BE_REGEX.search(text):
        evidence.append("ba_be: BA_BE_REGEX")
        return (CAT_BABE, evidence)

    if FORMULATION_REGEX.search(text):
        evidence.append("formulation: FORMULATION_REGEX")
        return (CAT_FORM, evidence)

    if SAD_MAD_REGEX.search(text) or DOSE_ESCALATION_REGEX.search(text) or FIH_REGEX.search(text):
        evidence.append("dose_escalation: SAD_MAD/DOSE_ESCALATION/FIH")
        return (CAT_ESC, evidence)

    if PK_REGEX.search(text) or PKPD_REGEX.search(text):
        evidence.append("pk: PK_REGEX/PKPD_REGEX")
        return (CAT_PK, evidence)
    
    if ORGAN_IMPAIRMENT_REGEX.search(text):
        evidence.append("organ_impairment: ORGAN_IMPAIRMENT_REGEX")
        return (CAT_ORGAN_IMPAIR, evidence)

    if HV_REGEX.search(text):
        evidence.append("healthy_volunteers: HV_REGEX")
        return (CAT_HV, evidence)

    if BIOMARKER_REGEX.search(text):
        evidence.append("biomarker: BIOMARKER_REGEX")
        return (CAT_BIOM, evidence)

    if MOA_REGEX.search(text):
        evidence.append("moa: MOA_REGEX")
        return (CAT_MOA, evidence)

    # If no anchors matched: real category by exclusion (not "other")
    evidence.append("safety_default: no category anchors matched")
    return (CAT_SAFETY, evidence)

def non_disease_drug_subtype_summary(
    trials: list[ClinicalTrialSignalV2],
) -> dict[str, int]:
    """
    Summarize non-disease drug studies by the same categories used in
    assign_non_disease_study_category().

    Deterministic, consistent, and single-source-of-truth.
    """
    counts: dict[str, int] = {}

    for t in trials:
        if not t.is_drug_trial:
            continue

        if getattr(t, "study_intent", None) != "non_disease":
            continue

        category, _evidence = assign_non_disease_study_category(t)
        counts[category] = counts.get(category, 0) + 1

    return counts

def non_disease_study_category_summary(
    trials: list[ClinicalTrialSignalV2],
) -> dict[str, int]:
    """
    Count non-disease drug trials by study_category.
    """
    counts: dict[str, int] = {}
    for t in trials:
        if not t.is_drug_trial:
            continue
        if getattr(t, "study_intent", None) != "non_disease":
            continue

        cat = getattr(t, "study_category", None) or "UNASSIGNED"
        counts[cat] = counts.get(cat, 0) + 1

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

def drug_mesh_missing_condition_summary(
    trials: list[ClinicalTrialSignalV2],
) -> dict:
    """
    Count drug trials with missing condition MeSH.
    This is a data completeness metric, NOT intent.
    """
    return {
        "mesh_missing_condition": sum(
            1
            for t in trials
            if t.is_drug_trial and not t.condition_meshes
        )
    }

