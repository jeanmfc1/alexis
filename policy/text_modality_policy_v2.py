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
    (re.compile(r"vaccin", re.IGNORECASE), "vaccine"),          # vaccine, vaccines, vaccination, nanovaccine, autovaccine
    (re.compile(r"\bneoantigen\b", re.IGNORECASE), "vaccine"),  # neoantigen vaccines without "vaccine" in name

    # Gene therapy — expanded
    (re.compile(r"\bgene therap(y|ies)\b", re.IGNORECASE), "gene_therapy"),
    (re.compile(r"\bgene editing\b", re.IGNORECASE), "gene_therapy"),
    (re.compile(r"\bgene transfer\b", re.IGNORECASE), "gene_therapy"),
    (re.compile(r"\bcrispr\b", re.IGNORECASE), "gene_therapy"),
    (re.compile(r"\bviral vector\b", re.IGNORECASE), "gene_therapy"),
    (re.compile(r"\blentiviral\b", re.IGNORECASE), "gene_therapy"),
    (re.compile(r"\bretroviral\b", re.IGNORECASE), "gene_therapy"),
    (re.compile(r"\baav\d*\b", re.IGNORECASE), "gene_therapy"),       # AAV, AAV5, AAV9
    (re.compile(r"\boncolytic\b", re.IGNORECASE), "gene_therapy"),     # oncolytic virus
    # mRNA that is not a vaccine (e.g. mRNA TCR T-cells, mRNA encoding protein)
    # vaccine pattern above catches mRNA vaccines; this catches remaining mRNA modalities
    (re.compile(r"\bmrna\b", re.IGNORECASE), "gene_therapy"),

    # Cell therapy — missing entirely from v1
    (re.compile(r"\bcar[-\s]?t\b", re.IGNORECASE), "cell_therapy"),
    (re.compile(r"\bcar[-\s]?nk\b", re.IGNORECASE), "cell_therapy"),
    (re.compile(r"\bcell (injection|infusion|therapy)\b", re.IGNORECASE), "cell_therapy"),
    (re.compile(r"\btumor[- ]infiltrating lymphocyte", re.IGNORECASE), "cell_therapy"),
    (re.compile(r"\b(t-reg|treg)[- ]depleted\b", re.IGNORECASE), "cell_therapy"),
    (re.compile(r"\bdonor lymphocyte infusion\b", re.IGNORECASE), "cell_therapy"),
    (re.compile(r"\b\bdli\b", re.IGNORECASE), "cell_therapy"),         # DLI = donor lymphocyte infusion
    (re.compile(r"\bnk cell\b", re.IGNORECASE), "cell_therapy"),
    (re.compile(r"\bdendritic cell\b", re.IGNORECASE), "cell_therapy"),
    (re.compile(r"\bcd34\+?\b.*\bcell\b", re.IGNORECASE), "cell_therapy"),
    (re.compile(r"\btcr[-\s]?t\b", re.IGNORECASE), "cell_therapy"),    # TCR-T cells

    # Radiopharmaceuticals — missing entirely from v1
    # Bracket isotope notation: [18F], [11C], [68Ga], [177Lu], [89Zr], [225Ac]
    (re.compile(r"\[\d+[A-Za-z]+\]", re.IGNORECASE), "radiopharmaceutical"),
    # Spelled-out isotopes
    (re.compile(r"\b(ga[-\s]?68|68ga|gallium[-\s]?68)\b", re.IGNORECASE), "radiopharmaceutical"),
    (re.compile(r"\b(lu[-\s]?177|177lu|lutetium[-\s]?177)\b", re.IGNORECASE), "radiopharmaceutical"),
    (re.compile(r"\b(zr[-\s]?89|89zr|zirconium[-\s]?89)\b", re.IGNORECASE), "radiopharmaceutical"),
    (re.compile(r"\b(ac[-\s]?225|225ac|actinium[-\s]?225)\b", re.IGNORECASE), "radiopharmaceutical"),
    (re.compile(r"\bradioligand therap(y|ies)\b", re.IGNORECASE), "radiopharmaceutical"),
    (re.compile(r"\bpet (imaging|tracer|radiotracer)\b", re.IGNORECASE), "radiopharmaceutical"),
    (re.compile(r"\bfapi\b", re.IGNORECASE), "radiopharmaceutical"),   # fibroblast activation protein inhibitor tracers

    # Biologics (recombinant proteins) — catch rh-prefix and spelled-out recombinant
    (re.compile(r"\brecombinant human\b", re.IGNORECASE), "biologic"),
    (re.compile(r"\brh[a-z]{2,}\b"), "biologic"),               # rhEPO, rhBNP, rhGCSF — case-sensitive: excludes rhPSMA
    (re.compile(r"\brecombinant (protein|peptide|enzyme|factor)\b", re.IGNORECASE), "biologic"),

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
