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
