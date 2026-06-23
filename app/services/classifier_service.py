"""Pure-Python classifier service for the ALEXIS MVP.

Wraps the three v2 classifiers behind a single ``classify_one(payload)``
entry point. No sklearn pickles are loaded — the classifiers in
``classifiers/*_v2.py`` and ``classifiers/therapeutic_area.py`` are
rule-based / lookup driven.

Both ``trial.interventions`` and ``trial.interventions_all`` are populated
from the same list because ``is_drug_trial_v2`` reads ``interventions_all``
while downstream modality logic reads ``interventions``.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from storage.models_v2 import ClinicalTrialSignalV2, InterventionV2
from classifiers.drug_non_drug_v2 import is_drug_trial_v2
from classifiers.trial_modality_v2 import assign_trial_modality_v2
from classifiers.therapeutic_area import assign_therapeutic_area


# Verbatim copy of MODALITY_COLORS from viz/alexis_weekly_dashboard.html.
# Keep keys ASCII lowercase + underscore; lookups normalise input first.
MODALITY_COLORS: dict[str, str] = {
    "small_molecule":           "#3B82F6",
    "biologic":                 "#8B5CF6",
    "monoclonal_antibody":      "#6366F1",
    "mab":                      "#6366F1",
    "adc":                      "#EC4899",
    "antibody_drug_conjugate":  "#EC4899",
    "gene_therapy":             "#22C55E",
    "cell_therapy":             "#14B8A6",
    "radiopharmaceutical":      "#F59E0B",
    "oligonucleotide":          "#EF4444",
    "peptide":                  "#A78BFA",
    "vaccine":                  "#34D399",
}

_DEFAULT_MODALITY_COLOR = "#475569"


# ---------------------------------------------------------------------------
# Input coercion
# ---------------------------------------------------------------------------
def _coerce_list(value: Any, *, field: str) -> list[str]:
    """Accept a list/tuple of strings OR a comma/newline-separated string.

    Strict: dicts, bytes, numbers, and arbitrarily-nested objects are
    rejected with a 400 rather than silently mis-classified (e.g. iterating
    a dict's keys, or stringifying a nested object). ``None`` and empty
    string yield an empty list.
    """
    if value is None or value == "":
        return []
    if isinstance(value, str):
        parts: list[str] = []
        for chunk in value.replace("\r", "\n").split("\n"):
            for piece in chunk.split(","):
                s = piece.strip()
                if s:
                    parts.append(s)
        return parts
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for v in value:
            if v is None:
                continue
            if not isinstance(v, str):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{field}: items must be strings, got "
                        f"{type(v).__name__}"
                    ),
                )
            s = v.strip()
            if s:
                out.append(s)
        return out
    raise HTTPException(
        status_code=400,
        detail=(
            f"{field} must be a list of strings or a comma/newline-separated "
            f"string, got {type(value).__name__}"
        ),
    )


def _modality_color(modality: str | None) -> str:
    if not modality:
        return _DEFAULT_MODALITY_COLOR
    key = str(modality).strip().lower()
    return MODALITY_COLORS.get(key, _DEFAULT_MODALITY_COLOR)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def classify_one(payload: dict) -> dict:
    """Classify a single user-supplied trial-like payload.

    Returns the result dict as specified in the API contract. Raises
    ``HTTPException(400)`` on validation failures so FastAPI converts them
    to clean 400 responses.
    """
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")

    title = str(payload.get("title", "") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    brief_summary = str(payload.get("brief_summary", "") or "")
    conditions = _coerce_list(payload.get("conditions"), field="conditions")
    intervention_names = _coerce_list(
        payload.get("interventions"), field="interventions"
    )

    if not intervention_names:
        raise HTTPException(
            status_code=400,
            detail="at least one intervention is required",
        )

    intervention_type = str(
        payload.get("intervention_type", "DRUG") or "DRUG"
    ).strip().upper() or "DRUG"
    study_type = str(
        payload.get("study_type", "INTERVENTIONAL") or "INTERVENTIONAL"
    ).strip().upper() or "INTERVENTIONAL"
    phase_raw = payload.get("phase")
    phase = str(phase_raw).strip() if phase_raw not in (None, "") else None

    interventions = [
        InterventionV2(name=name, type=intervention_type)
        for name in intervention_names
    ]

    trial = ClinicalTrialSignalV2(
        nct_id="USER_INPUT",
        title=title,
        brief_summary=brief_summary,
        conditions=conditions,
        study_type=study_type,
        phase=phase,
        interventions=list(interventions),
        interventions_all=list(interventions),
        interventions_text=list(intervention_names),
    )

    is_drug = bool(is_drug_trial_v2(trial))
    modality = assign_trial_modality_v2(trial)
    try:
        ta = assign_therapeutic_area(trial)
    except Exception:
        # Therapeutic-area is best-effort; never poison the whole call.
        ta = None

    return {
        "is_drug_trial": is_drug,
        "modality": modality,
        "therapeutic_area": ta,
        "info_flags": list(trial.info_flags or []),
        "modality_color": _modality_color(modality),
        "echo": {
            "title": title,
            "n_conditions": len(conditions),
            "n_interventions": len(intervention_names),
            "study_type": study_type,
            "intervention_type": intervention_type,
        },
    }
