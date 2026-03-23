
TYPE_MODALITY_MAP: dict[str, str] = {
    "DRUG":            "small_molecule",
    "BIOLOGICAL":      "biologic",
    "VACCINE":         "vaccine",         # structured type covers some vaccine concepts
    "GENETIC":         "gene_therapy",
    "RADIATION":       "radiopharmaceutical",
    "COMBINATION_PRODUCT": "combination",  # combination products may require further semantic inspection
}

def type_to_base_modality(iv_type: str | None) -> str:
    if not isinstance(iv_type, str):
        return "other_drug"

    key = iv_type.strip().upper()

    # If this intervention type maps directly, return it
    if key in TYPE_MODALITY_MAP:
        return TYPE_MODALITY_MAP[key]

    # Anything else that semantically still could be drug-related
    # (rare cases like dietary supplements) we treat as "other_drug"
    drug_like = {"DIETARY_SUPPLEMENT"}
    if key in drug_like:
        return "other_drug"

    # Otherwise, non-drug categories
    return "non_drug"
