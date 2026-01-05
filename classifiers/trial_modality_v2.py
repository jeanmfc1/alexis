from __future__ import annotations
from typing import TYPE_CHECKING, Optional

# IMPORT your V1 text matching modality util
from classifiers.drug_modality_v1 import match_modality_from_text

from policy.type_modality_policy_v2 import type_to_base_modality
from policy.mesh_tree_modality_policy_v2 import mesh_tree_to_submodality

if TYPE_CHECKING:
    from storage.models_v2 import ClinicalTrialSignalV2, MeshTermV2


def assign_trial_modality_v2(trial: "ClinicalTrialSignalV2") -> str:
    """
    Assign a refined modality label for a confirmed drug trial based on:
       1) Structured intervention.type → base modality
       2) MeSH descriptor tree numbers → detailed subcategory
       3) Legacy text matcher → fallback
       4) Default to base

    Args:
        trial: ClinicalTrialSignalV2 with experimental drug interventions and MeSH data

    Returns:
        modality: str from your taxonomy (e.g., small_molecule, monoclonal_antibody, vaccine, etc.)
    """
    # Reset INFO flags for this run
    trial.info_flags.clear()
    mesh_available = bool(getattr(trial, "intervention_meshes", []))

    # --- 1) Base modality from structured intervention.type ---

    base_modalities: list[str] = []
    for iv in getattr(trial, "interventions", []) or []:
        if iv.type:
            base = type_to_base_modality(iv.type)
            base_modalities.append(base)

    # choose representative base modality (first, majority, etc.)
    base_modality = base_modalities[0] if base_modalities else "other_drug"

    # --- 2) Always try MeSH tree refinement (highest quality) ---

    # collect all candidate MeSH submodalities
    mesh_submods: list[str] = []
    mesh_used = False

    for m in getattr(trial, "intervention_meshes", []) or []:
        mesh_result = mesh_tree_to_submodality(m.id)
        if mesh_result.modality:
            mesh_used = True
            mesh_submods.append(mesh_result.modality)

    if mesh_submods:
        # resolve priority (policy logic), e.g., pick the most specific
        return _resolve_modality_priority(mesh_submods, base_modality)
    
    if mesh_available and not mesh_used:
        trial.info_flags.append("mesh_available_but_not_used")

    # --- 3) Fallback: use legacy text matcher from ALEXIS V1 ---

    text_blob = " ".join((trial.interventions_text or []) + [trial.title or ""])
    text_submod = match_modality_from_text(text_blob, base_modality)
    if text_submod:
        return text_submod

    # --- 4) Default to base modality if no refinement ---

    return base_modality


def _resolve_modality_priority(candidates: list[str], base: str) -> str:
    """
    Given candidate submodalities from MeSH (or other signals),
    resolve a single modality label. You may refine this logic
    further with priority lists or weighting.

    For now, simple majority or first group.
    """

    from collections import Counter

    counts = Counter(candidates)
    top, _ = counts.most_common(1)[0]
    return top
