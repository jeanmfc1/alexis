import re

"""
Text-based fallback modality refinement.
These patterns are intentionally heuristic and should only be used as fallback
when structured intervention.type and MeSH tree rules cannot classify.
"""

TEXT_PATTERN_TO_SUBMODALITY = [
    # Antibodies and antibody-like biologics
    (re.compile(r"\bmonoclonal\b", re.IGNORECASE), "monoclonal_antibody"),
    (re.compile(r"\bantibody\b", re.IGNORECASE), "monoclonal_antibody"),
    (re.compile(r"\bbispecific\b", re.IGNORECASE), "monoclonal_antibody"),
    (re.compile(r"\bbite\b", re.IGNORECASE), "monoclonal_antibody"),
    (re.compile(r"\bmab\b", re.IGNORECASE), "monoclonal_antibody"),

    # Fusion proteins
    (re.compile(r"\bfusion protein\b", re.IGNORECASE), "fusion_protein"),
    (re.compile(r"\bfusion\b.*\bprotein\b", re.IGNORECASE), "fusion_protein"),

    # Oligonucleotides
    (re.compile(r"\boligonucleotid(e|es)\b", re.IGNORECASE), "oligonucleotide"),
    (re.compile(r"\bantisense\b", re.IGNORECASE), "oligonucleotide"),
    (re.compile(r"\bsirna\b", re.IGNORECASE), "oligonucleotide"),
    (re.compile(r"\baso\b", re.IGNORECASE), "oligonucleotide"),

    # Vaccines
    (re.compile(r"\bvaccin(e|es)\b", re.IGNORECASE), "vaccine"),

    # Gene therapy
    (re.compile(r"\bgene therap(y|ies)\b", re.IGNORECASE), "gene_therapy"),
    (re.compile(r"\bgene editing\b", re.IGNORECASE), "gene_therapy"),
    (re.compile(r"\bcrispr\b", re.IGNORECASE), "gene_therapy"),
    (re.compile(r"\bviral vector\b", re.IGNORECASE), "gene_therapy"),

    # Small-molecule-ish hints (low specificity, keep late)
    (re.compile(r"\bsmall molecule\b", re.IGNORECASE), "small_molecule"),
    (re.compile(r"\binhibitor\b", re.IGNORECASE), "small_molecule"),
    (re.compile(r"\bagonist\b", re.IGNORECASE), "small_molecule"),
    (re.compile(r"\bantagonist\b", re.IGNORECASE), "small_molecule"),
    (re.compile(r"\bmodulator\b", re.IGNORECASE), "small_molecule"),
]


def text_modality_from_text(text: str | None, base_modality: str) -> str | None:
    """
    Return a refined submodality from free text if possible.

    Rules:
    - If text is empty/None: return None
    - If any pattern matches: return its submodality
    - If no match: propagate base_modality (except when base_modality is empty)
    """
    if not text:
        return None

    for pat, submod in TEXT_PATTERN_TO_SUBMODALITY:
        if pat.search(text):
            return submod

    return base_modality if base_modality else None
