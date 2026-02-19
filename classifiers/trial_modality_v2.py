from __future__ import annotations
from typing import TYPE_CHECKING, Optional

from policy.text_modality_policy_v2 import text_modality_from_text
from policy.type_modality_policy_v2 import type_to_base_modality
from policy.mesh_tree_modality_policy_v2 import mesh_tree_to_submodality

if TYPE_CHECKING:
    from storage.models_v2 import ClinicalTrialSignalV2, MeshTermV2


# Curated set of MeSH ancestor terms that are unambiguous modality signals.
# Used by the ancestor fallback walk when mesh_tree_to_submodality returns
# nothing for a specific mesh ID. Deliberately restricted: broad terms like
# "Organic Chemicals", "Proteins", or "Amino Acids, Peptides, and Proteins"
# are excluded because intervention_mesh_ancestors is a flat union across ALL
# intervention meshes (drug and non-drug), and those broad terms match both.
_DRUG_ANCESTOR_SIGNALS: dict[str, str] = {
    "Antibodies, Monoclonal":                  "monoclonal_antibody",
    "Antibodies, Monoclonal, Humanized":       "monoclonal_antibody",
    "Antibodies, Monoclonal, Murine-Derived":  "monoclonal_antibody",
    "Antibodies, Monoclonal, Mouse-Human":     "monoclonal_antibody",
    "Vaccines":                                "vaccine",
    "Oligonucleotides":                        "oligonucleotide",
    "Radiopharmaceuticals":                    "radiopharmaceutical",
}


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
    for iv in getattr(trial, "interventions_all", []) or []:
        if iv.type:
            base = type_to_base_modality(iv.type)
            base_modalities.append(base)

    # choose representative base modality (first, majority, etc.)
    def select_best_modality(modalities):
        """Prioritize drug types over non-drug types"""
        if not modalities:
            return "other_drug"
    
        # Filter out non-drug if there are drug options
        drug_modalities = [m for m in modalities if m != "non_drug"]
        if drug_modalities:
            return drug_modalities[0]
    
        return modalities[0]

    base_modality = select_best_modality(base_modalities)

    # --- 2) Always try MeSH tree refinement (highest quality) ---

    # Build set of drug intervention names for filtering (lowercased for comparison).
    # intervention_meshes contains meshes for ALL intervention types in the trial —
    # we only want meshes that correspond to DRUG interventions.
    drug_intervention_names: set[str] = {
        iv.name.lower()
        for iv in (getattr(trial, "interventions_all", []) or [])
        if iv.type == "DRUG" and iv.name
    }

    # Pre-computed ancestor chain, available for fallback when direct ID lookup fails.
    all_ancestors: list["MeshTermV2"] = getattr(trial, "intervention_mesh_ancestors", []) or []

    # collect all candidate MeSH submodalities
    mesh_submods: list[str] = []
    mesh_used = False

    for m in getattr(trial, "intervention_meshes", []) or []:
        # Bug 2 fix: skip meshes that don't correspond to a DRUG intervention.
        # Prevents "Specimen Handling", "Nephrectomy", etc. from polluting candidates.
        if m.term.lower() not in drug_intervention_names:
            continue

        # Try direct lookup (works when mesh_tree has this specific ID)
        mesh_result = mesh_tree_to_submodality(m.id)
        if mesh_result.modality:
            mesh_used = True
            mesh_submods.append(mesh_result.modality)

    # Bug 1 fix: if direct lookups produced nothing, fall back to the pre-computed
    # ancestor chain. We scan once (not per-mesh) because intervention_mesh_ancestors
    # is a flat union — scanning it multiple times would just duplicate results.
    #
    # We use a restricted signal set intentionally: broad ancestor terms like
    # "Organic Chemicals" or "Proteins" are excluded because the flat list mixes
    # ancestors from drug and non-drug interventions alike. The curated set
    # (_DRUG_ANCESTOR_SIGNALS) contains only unambiguous modality signals.
    # This means the ancestor walk is an upgrade-only path: it can resolve
    # monoclonal_antibody, vaccine, oligonucleotide, or radiopharmaceutical,
    # but not small_molecule (which comes from direct lookup or text fallback).
    if not mesh_submods and all_ancestors:
        for ancestor in all_ancestors:
            anc_mod = _DRUG_ANCESTOR_SIGNALS.get(ancestor.term)
            if anc_mod:
                mesh_used = True
                mesh_submods.append(anc_mod)
                # Collect all — priority resolution picks the winner below

    if mesh_submods:
        # resolve priority — most specific modality wins (see bug 3 fix below)
        return _resolve_modality_priority(mesh_submods, base_modality)

    if mesh_available and not mesh_used:
        trial.info_flags.append("mesh_available_but_not_used")

    # --- 3) Fallback: use legacy text matcher from ALEXIS V1 ---

    text_blob = " ".join((trial.interventions_text or []) + [trial.title or ""])
    text_submod = text_modality_from_text(text_blob, base_modality)
    if text_submod:
        return text_submod


    # --- 4) Default to base modality if no refinement ---

    return base_modality


def _resolve_modality_priority(candidates: list[str], base: str) -> str:
    """
    Given candidate submodalities from MeSH, resolve a single modality label
    using a specificity priority order. Most specific modality present wins.

    Rationale: if a trial includes both a small molecule and a monoclonal antibody,
    the mAb is the more clinically significant modality and should be the label.
    Majority vote (previous logic) would mask a minority mAb in a multi-drug trial.

    Priority is highest-first: first match in the list wins.
    """

    # Ordered from most specific to least specific.
    # Anything not in this list falls through to base.
    MODALITY_PRIORITY = [
        "gene_therapy",
        "cell_therapy",
        "monoclonal_antibody",
        "antibody_protein",
        "fusion_protein",
        "bispecific_antibody",
        "vaccine",
        "oligonucleotide",
        "radiopharmaceutical",
        "biologic",
        "combination",
        "small_molecule",
        "other_drug",
    ]

    candidate_set = set(candidates)
    for modality in MODALITY_PRIORITY:
        if modality in candidate_set:
            return modality

    # Nothing matched priority list — fall back to base
    return base