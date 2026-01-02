import pytest

from policy.type_modality_policy_v2 import type_to_base_modality
from policy.mesh_tree_modality_policy_v2 import mesh_tree_to_submodality
from policy.text_modality_policy_v2 import text_modality_from_text

def classify_trial_modality(iv_type, mesh_ids, mesh_terms, text):
    """
    Local helper function that mimics the logic in trial_modality_v2.py
    """
    base = type_to_base_modality(iv_type)
    # try MeSH first
    for mid, term in zip(mesh_ids, mesh_terms):
        sub = mesh_tree_to_submodality(mid, term, base)
        if sub:
            return sub
    # fallback to text
    text_sub = text_modality_from_text(text, base)
    return text_sub or base

@pytest.mark.parametrize("iv_type,mesh_ids,mesh_terms,text,expected", [
    # small molecule via MeSH
    ("DRUG", ["D000068696"], ["Rilpivirine"], "Rilpivirine tablet", "small_molecule"),

    # antibody via MeSH
    ("BIOLOGICAL", ["D000081657"], ["Trastuzumab"], "Herceptin antibody", "monoclonal_antibody"),

    # vaccine via MeSH
    ("BIOLOGICAL", ["D000087503"], ["Influenza Vaccine"], "flu vaccine", "vaccine"),

    # oligo via MeSH
    ("GENETIC", ["D016376"], ["Antisense Oligonucleotide"], "", "oligonucleotide"),

    # fusion protein via MeSH
    ("BIOLOGICAL", ["D011993"], ["Fusion Protein"], "", "fusion_protein"),

    # fallback to text
    ("DRUG", [None], [None], "peptide vaccine candidate", "vaccine"),
])
def test_end_to_end_modality(iv_type, mesh_ids, mesh_terms, text, expected):
    assert classify_trial_modality(iv_type, mesh_ids, mesh_terms, text) == expected
