import pytest

from policy.text_modality_policy_v2 import text_modality_from_text

@pytest.mark.parametrize("text,base,expected", [
    ("Fully human monoclonal antibody against X", "biologic", "monoclonal_antibody"),
    ("BiTE bispecific antibody construct", "biologic", "monoclonal_antibody"),
    ("Fusion protein IL-2 receptor blocker", "biologic", "fusion_protein"),
    ("Novel oligonucleotide antisense agent", "drug", "oligonucleotide"),
    ("COVID vaccine candidate", "drug", "vaccine"),
    ("Small molecule inhibitor of kinase", "drug", "small_molecule"),
    ("Gene therapy editing vector", "genetic", "gene_therapy"),

    # if no match, base modality propagates
    ("Unmatched text", "biologic", "biologic"),
    ("", "small_molecule", None),
])
def test_text_modality_from_text(text, base, expected):
    assert text_modality_from_text(text, base) == expected
