from __future__ import annotations

from collections import Counter
from typing import Dict, List, Tuple, Any

from policy.modality_policy import (
    MODALITY_LABELS,
    PROCEDURE_TERMS,
    DEVICE_DIGITAL_TERMS,
    BEHAVIORAL_EXERCISE_TERMS,
    DRUG_LIKE_TERMS,
)


def _text_blob(trial) -> str:
    interventions = getattr(trial, "interventions", None) or []
    return " ".join(interventions).lower().strip()


def _has_any(text: str, terms: List[str]) -> bool:
    return any(t in text for t in terms)


def audit_trials(trials: List[Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    """
    Audit modality assignments for internal consistency.

    Hard flags (violations):
      - Observational study_type but modality not Observational/Diagnostic
      - Empty interventions but modality is not Other/Unknown or Observational/Diagnostic
      - Modality label not in MODALITY_LABELS
      - Modality == Small Molecule but strong non-drug anchors present (procedure/device/behavioral)

    INFO-only (ambiguity surfacing):
      - Procedure/Radiation modality but no procedure anchors found
      - Device/Digital modality but no device/digital anchors found
      - Behavioral/Exercise modality but no behavioral/exercise anchors found
      - Small Molecule modality but no drug-like anchors found (defaulting)
      - Multiple non-drug anchor families present (mixed signals)
    """
    flags: List[Dict[str, Any]] = []
    infos: List[Dict[str, Any]] = []
    counts: Counter = Counter()

    for tr in trials:
        nct_id = getattr(tr, "nct_id", None) or getattr(tr, "id", None) or "UNKNOWN"
        study_type = getattr(tr, "study_type", None)
        modality = getattr(tr, "modality", None)

        text = _text_blob(tr)

        has_proc = _has_any(text, PROCEDURE_TERMS)
        has_dev = _has_any(text, DEVICE_DIGITAL_TERMS)
        has_beh = _has_any(text, BEHAVIORAL_EXERCISE_TERMS)
        has_drug = _has_any(text, DRUG_LIKE_TERMS)

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
                    "message": "Interventions are empty but modality is not Other/Unknown (or Observational/Diagnostic).",
                    "modality": modality,
                }
            )
            counts["flags_empty_interventions_mismatch"] += 1

        if modality == "Small Molecule" and (has_proc or has_dev or has_beh):
            # Strong indication we misrouted a non-drug study into drug bucket.
            flags.append(
                {
                    "nct_id": nct_id,
                    "type": "NON_DRUG_ANCHOR_IN_SMALL_MOLECULE",
                    "message": "Small Molecule assigned but non-drug anchors detected (procedure/device/behavioral).",
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
                    "message": "Procedure/Radiation assigned but no procedure anchors found in intervention text.",
                }
            )
            counts["info_proc_no_anchor"] += 1

        if modality == "Device/Digital" and not has_dev:
            infos.append(
                {
                    "nct_id": nct_id,
                    "type": "DEVICE_NO_ANCHOR",
                    "message": "Device/Digital assigned but no device/digital anchors found in intervention text.",
                }
            )
            counts["info_device_no_anchor"] += 1

        if modality == "Behavioral/Exercise" and not has_beh:
            infos.append(
                {
                    "nct_id": nct_id,
                    "type": "BEHAVIORAL_NO_ANCHOR",
                    "message": "Behavioral/Exercise assigned but no behavioral/exercise anchors found in intervention text.",
                }
            )
            counts["info_behavioral_no_anchor"] += 1

        if modality == "Small Molecule" and not has_drug:
            infos.append(
                {
                    "nct_id": nct_id,
                    "type": "SMALL_MOLECULE_DEFAULTED",
                    "message": "Small Molecule assigned without drug-like anchors (likely defaulted).",
                }
            )
            counts["info_small_molecule_defaulted"] += 1

        non_drug_families = sum([1 if has_proc else 0, 1 if has_dev else 0, 1 if has_beh else 0])
        if non_drug_families >= 2:
            infos.append(
                {
                    "nct_id": nct_id,
                    "type": "MIXED_NON_DRUG_SIGNALS",
                    "message": "Multiple non-drug anchor families detected (procedure/device/behavioral).",
                    "anchors": {
                        "procedure": has_proc,
                        "device_digital": has_dev,
                        "behavioral_exercise": has_beh,
                    },
                }
            )
            counts["info_mixed_non_drug_signals"] += 1

    return flags, infos, dict(counts)
