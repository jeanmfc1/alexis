import re
from typing import Optional

"""
Text-based fallback rules for drug modality inference.

These rules run *only when MeSH lookup is absent or inconclusive*.
We keep this separate so semantic (MeSH) logic and heuristic (text) logic
don’t get mixed in one place.

The goal is to capture common textual patterns indicative of
subclasses such as:
  - monoclonal_antibody
  - fusion_protein
  - vaccine
  - oligonucleotide
  - small_molecule
  - gene_therapy
  - etc.
"""

# Patterns mapped to submodality
# These regexes are deliberately simple and domain-focused.
TEXT_PATTERN_TO_SUBMODALITY = [
    (re.compile(r"\bmonoclonal\b", re.IGNORECASE), "monoclonal_antibody"),
    (re.compile(r"\bmab\b", re.IGNORECASE),            "monoclonal_antibody"),

    (re.compile(r"\bfusion protein\b", re.IGNORECASE),  "fusion_protein"),
    (re.compile(r"\bfusion\b.*\bprotein\b", re.IGNORECASE), "fusion_protein"),

    (re.compile(r"\bo(n|l)ucleotid(e|es)\b", re.IGNORECASE), "oligonucleotide"),

    (re.compile(r"\bvaccin(e|es)\b", re.IGNORECASE),    "vaccine"),

    (re.compile(r"\bgene therap(y|ies)\b", re.IGNORECASE), "gene_therapy"),
    (re.compile(r"\bgene editing\b", re.IGNORECASE),   "gene_therapy"),

    # small molecule ligands and descriptors
    (re.compile(r"\binhibitor\b", re.IGNORECASE),       "small_molecule"),
    (re.compile(r"\bagonist\b", re.IGNORECASE),         "small_molecule"),
    (re.compile(r"\bantagonist\b", re.IGNORECASE),      "small_molecule"),
    (re.compile(r"\bmodulator\b", re.IGNORECASE),       "small_molecule"),
    (re.compile(r"\bblocker\b", re.IGNORECASE),         "small_molecule"),
]

def text_modality_from_text(text: str, base_modality: str) -> Optional[str]:
    """
    Returns a modality subcategory inferred from free text.
    Called only if MeSH lookup returned None.

    Args:
        text: free text (trial title, intervention names, etc.)
        base_modality: a base category from structured intervention.type

    Returns:
        A submodality label or None
    """
    if not text:
        return None

    # Check patterns in order for the first match.
    # Prioritization is left to the order in TEXT_PATTERN_TO_SUBMODALITY.
    for pattern, submod in TEXT_PATTERN_TO_SUBMODALITY:
        if pattern.search(text):
            return submod

    # If no textual match and base_modality is informative, return base
    if base_modality and base_modality != "other_drug":
        return base_modality

    # Otherwise, no confident inference
    return None
