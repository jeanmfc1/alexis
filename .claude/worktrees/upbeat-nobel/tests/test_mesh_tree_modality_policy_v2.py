import pytest

from policy.mesh_tree_modality_policy_v2 import mesh_tree_to_submodality

# You may want to mark these with a slow/net marker if API calls are involved
@pytest.mark.parametrize("mesh_id,term,base,expected", [
    # Small molecules — should match D02 / D03 / D04
    ("D000068696", "Rilpivirine", "drug", "small_molecule"),  # tree includes D02 and D03
    ("D000069059", "Atorvastatin", "drug", "small_molecule"), # organic statin example

    # Antibodies (monoclonal) — deeply nested prefix
    # Example: Trastuzumab (ID may vary by MeSH version)
    ("D000069579", "Ranibizumab", "biologic", "monoclonal_antibody"),

    # Fusion protein example — use a known fusion protein MeSH ID
    ("D011993", "Recombinant Fusion Protein", "biologic", "fusion_protein"),

    # Vaccines under protein branch
    ("D000087503", "Influenza Vaccine, Live", "drug", "vaccine"),

    # Oligonucleotide example (nucleic acid)
    ("D016376", "Antisense Oligonucleotide", "drug", "oligonucleotide"),

    # If no MeSH match and fallback applies, base modality should persist
    (None, "Unknown text", "small_molecule", None),
])
def test_mesh_tree_to_submodality(mesh_id, term, base, expected):
    result = mesh_tree_to_submodality(mesh_id)
    assert result.modality == expected

