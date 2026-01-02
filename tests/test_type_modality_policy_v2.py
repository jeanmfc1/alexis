import pytest

from policy.type_modality_policy_v2 import type_to_base_modality

@pytest.mark.parametrize("iv_type,expected", [
    ("DRUG", "small_molecule"),
    ("BIOLOGICAL", "biologic"),
    ("VACCINE", "vaccine"),
    ("GENETIC", "gene_therapy"),
    ("RADIATION", "radiopharmaceutical"),
    ("COMBINATION_PRODUCT", "combination"),
    ("DIETARY_SUPPLEMENT", "other_drug"),
    ("DEVICE", "non_drug"),
    (None, "other_drug"),
])
def test_type_to_base_modality(iv_type, expected):
    assert type_to_base_modality(iv_type) == expected
