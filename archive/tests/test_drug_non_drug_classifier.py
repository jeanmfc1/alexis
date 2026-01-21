from types import SimpleNamespace
from classifiers.drug_non_drug import is_drug_trial

def trial(interventions):
    return SimpleNamespace(interventions=interventions)

def test_drug_name_suffix_counts_as_drug():
    t = trial(["Guselkumab"])
    assert is_drug_trial(t) is True

def test_dose_plus_context_counts_as_drug():
    t = trial(["Clarithromycin 500 mg tablet"])
    assert is_drug_trial(t) is True

def test_placebo_only_is_not_drug():
    t = trial(["PET imaging with placebo control"])
    assert is_drug_trial(t) is False

def test_imaging_only_is_not_drug():
    t = trial(["MRI scan", "Questionnaire"])
    assert is_drug_trial(t) is False

def test_vaccine_counts_as_drug():
    t = trial(["mRNA vaccine"])
    assert is_drug_trial(t) is True

def test_radiopharmaceutical_activity_unit_counts_as_drug_when_route_present():
    t = trial(["Lutetium-177 infusion 7.4 GBq"])
    assert is_drug_trial(t) is True

def test_mg_per_kg_dose_counts_as_drug_with_route():
    t = trial(["DrugX 2 mg/kg IV infusion"])
    assert is_drug_trial(t) is True

def test_placebo_plus_clear_drug_identity_is_drug():
    t = trial(["Placebo", "Guselkumab"])
    assert is_drug_trial(t) is True

def test_sham_only_is_not_drug():
    t = trial(["Sham procedure"])
    assert is_drug_trial(t) is False

def test_drug_identity_in_title_counts_as_drug():
    t = SimpleNamespace(interventions=["Placebo"], title="Study of Guselkumab in psoriasis")
    assert is_drug_trial(t) is True

