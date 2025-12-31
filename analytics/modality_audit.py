from __future__ import annotations

from collections import Counter
from typing import Dict, List, Tuple, Any
import re

from analytics.modality_audit_writer import write_modality_info_artifact

from policy.modality_policy import (
    MODALITY_LABELS,
    PROCEDURE_TERMS,
    DEVICE_DIGITAL_TERMS,
    BEHAVIORAL_EXERCISE_TERMS,
    DRUG_LIKE_TERMS,
    has_drug_name_signal,
    _has_any
)

from classifiers.drug_non_drug import is_drug_trial

def _text_blob(trial) -> str:
    interventions = getattr(trial, "interventions", None) or []
    return " ".join(interventions).lower().strip()

def _raw_blob(trial) -> str:
    interventions = getattr(trial, "interventions", None) or []
    return " ".join(interventions).strip()

def audit_trials(
    trials: List[Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    """
    Audit modality assignments for internal consistency.
    """
    flags: List[Dict[str, Any]] = []
    infos: List[Dict[str, Any]] = []
    counts: Counter = Counter()

    for tr in trials:
        nct_id = getattr(tr, "nct_id", None) or getattr(tr, "id", None) or "UNKNOWN"
        study_type = getattr(tr, "study_type", None)
        modality = getattr(tr, "modality", None)

        text = _text_blob(tr)
        raw_text = _raw_blob(tr)

        has_proc = _has_any(text, PROCEDURE_TERMS)
        has_dev = _has_any(text, DEVICE_DIGITAL_TERMS)
        has_beh = _has_any(text, BEHAVIORAL_EXERCISE_TERMS)
        has_drug = is_drug_trial(tr)

        counts["trials_total"] += 1
        counts[f"modality::{modality}"] += 1

        # --- Hard validations ---
        if modality not in MODALITY_LABELS:
            flags.append(
                {
                    "nct_id": nct_id,
                    "type": "INVALID_LABEL",
                    "message": f"Modality '{modality}' is not a recognized label.",
                }
            )
            counts["flags_invalid_label"] += 1
            continue

        if study_type == "OBSERVATIONAL" and modality != "Observational/Diagnostic":
            flags.append(
                {
                    "nct_id": nct_id,
                    "type": "OBSERVATIONAL_MISMATCH",
                    "message": "study_type is OBSERVATIONAL but modality is not Observational/Diagnostic.",
                    "study_type": study_type,
                    "modality": modality,
                }
            )
            counts["flags_observational_mismatch"] += 1

        if not text and modality not in ("Other/Unknown", "Observational/Diagnostic"):
            flags.append(
                {
                    "nct_id": nct_id,
                    "type": "EMPTY_INTERVENTIONS_MISMATCH",
                    "message": (
                        "Interventions are empty but modality is not "
                        "Other/Unknown (or Observational/Diagnostic)."
                    ),
                    "modality": modality,
                }
            )
            counts["flags_empty_interventions_mismatch"] += 1

        if modality == "Small Molecule" and not has_drug and (has_proc or has_dev or has_beh):
            flags.append(
                {
                    "nct_id": nct_id,
                    "type": "NON_DRUG_ANCHOR_IN_SMALL_MOLECULE",
                    "message": (
                        "Small Molecule assigned but non-drug anchors detected "
                        "(procedure/device/behavioral)."
                    ),
                    "anchors": {
                        "procedure": has_proc,
                        "device_digital": has_dev,
                        "behavioral_exercise": has_beh,
                    },
                }
            )
            counts["flags_non_drug_in_small_molecule"] += 1

        # --- INFO (explanatory / ambiguity) ---
        if modality == "Procedure/Radiation" and not has_proc:
            infos.append(
                {
                    "nct_id": nct_id,
                    "type": "PROC_NO_ANCHOR",
                    "message": (
                        "Procedure/Radiation assigned but no procedure anchors "
                        "found in intervention text."
                    ),
                }
            )
            counts["info_proc_no_anchor"] += 1

        if modality == "Device/Digital" and not has_dev:
            infos.append(
                {
                    "nct_id": nct_id,
                    "type": "DEVICE_NO_ANCHOR",
                    "message": (
                        "Device/Digital assigned but no device/digital anchors "
                        "found in intervention text."
                    ),
                }
            )
            counts["info_device_no_anchor"] += 1

        if modality == "Behavioral/Exercise" and not has_beh:
            infos.append(
                {
                    "nct_id": nct_id,
                    "type": "BEHAVIORAL_NO_ANCHOR",
                    "message": (
                        "Behavioral/Exercise assigned but no behavioral/exercise "
                        "anchors found in intervention text."
                    ),
                }
            )
            counts["info_behavioral_no_anchor"] += 1

        if modality == "Small Molecule" and not has_drug:
            infos.append(
                {
                    "nct_id": nct_id,
                    "type": "SMALL_MOLECULE_DEFAULTED",
                    "message": (
                        "Small Molecule assigned without drug-like anchors "
                        "(likely defaulted)."
                    ),
                }
            )
            counts["info_small_molecule_defaulted"] += 1

                # --- INFO (primary/secondary non-drug signals) ---
        non_drug_hits = []
        if has_proc:
            non_drug_hits.append("Procedure/Radiation")
        if has_dev:
            non_drug_hits.append("Device/Digital")
        if has_beh:
            non_drug_hits.append("Behavioral/Exercise")

        # Primary intent uses the same precedence as the classifier.
        primary = None
        if has_proc:
            primary = "Procedure/Radiation"
        elif has_dev:
            primary = "Device/Digital"
        elif has_beh:
            primary = "Behavioral/Exercise"

        secondary = [x for x in non_drug_hits if x != primary]
            
        if has_drug and modality in ("Procedure/Radiation", "Device/Digital", "Behavioral/Exercise"):
            infos.append({
                "nct_id": nct_id,
                "type": "POSSIBLE_DRUG_FALSE_NEGATIVE",
                "message": "Drug evidence detected but modality is non-drug; likely drug trial with assessment interventions.",
                "modality": modality,
                "anchors": {"procedure": has_proc, "device_digital": has_dev, "behavioral_exercise": has_beh},
            })
            counts["info_possible_drug_false_negative"] += 1

        if (not has_drug) and modality == "Small Molecule":
            infos.append({
                "nct_id": nct_id,
                "type": "POSSIBLE_DRUG_FALSE_POSITIVE",
                "message": "No drug evidence detected but modality is Small Molecule; likely misclassified as drug.",
                "modality": modality,
            })
            counts["info_possible_drug_false_positive"] += 1


        # If this is a drug trial (has_drug True), non-drug signals are usually assessments/endpoints.
        # Do NOT call this "mixed non-drug signals". Track separately.
        if modality == "Small Molecule" and has_drug and len(non_drug_hits) >= 1:
            infos.append(
                {
                    "nct_id": nct_id,
                    "type": "DRUG_WITH_NON_DRUG_ASSESSMENTS",
                    "message": (
                        "Drug trial includes non-drug assessment components "
                        "(procedure/device/behavioral)."
                    ),
                    "primary_non_drug": primary,
                    "secondary_non_drug": secondary,
                    "anchors": {
                        "procedure": has_proc,
                        "device_digital": has_dev,
                        "behavioral_exercise": has_beh,
                    },
                }
            )
            counts["info_drug_with_non_drug_assessments"] += 1

        # Only call it MIXED_NON_DRUG_SIGNALS when the trial is NOT primarily drug-like.
        elif len(non_drug_hits) >= 3:
            infos.append(
                {
                    "nct_id": nct_id,
                    "type": "MIXED_NON_DRUG_SIGNALS",
                    "message": (
                        "Multiple non-drug anchor families detected "
                        "(procedure/device/behavioral)."
                    ),
                    "primary_non_drug": primary,
                    "secondary_non_drug": secondary,
                    "anchors": {
                        "procedure": has_proc,
                        "device_digital": has_dev,
                        "behavioral_exercise": has_beh,
                    },
                }
            )
            counts["info_mixed_non_drug_signals"] += 1



    # --- Persist INFO artifact (side-effect, isolated) ---
    write_modality_info_artifact(
        infos,
        context={
            "module": "analytics.modality_audit",
            "function": "audit_trials",
            "n_trials": len(trials),
        },
    )

    return flags, infos, dict(counts)

