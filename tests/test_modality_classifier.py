from types import SimpleNamespace

from classifiers.modality import assign_modality


def trial(*, study_type="INTERVENTIONAL", interventions=None):
    return SimpleNamespace(
        study_type=study_type,
        interventions=list(interventions or []),
    )


def test_observational_is_observational_diagnostic():
    t = trial(study_type="OBSERVATIONAL", interventions=["Some intervention-like text"])
    assert assign_modality(t) == "Observational/Diagnostic"


def test_empty_interventions_returns_other_unknown():
    t = trial(interventions=[])
    assert assign_modality(t) == "Other/Unknown"


def test_procedure_radiation_keywords_win():
    t = trial(interventions=["Low Dose Radiation Therapy"])
    assert assign_modality(t) == "Procedure/Radiation"


def test_surgery_keywords_win():
    t = trial(interventions=["Robotic-Assisted Surgery"])
    assert assign_modality(t) == "Procedure/Radiation"


def test_device_digital_cpap_is_device_digital():
    t = trial(interventions=["CPAP"])
    assert assign_modality(t) == "Device/Digital"


def test_device_digital_mhealth_is_device_digital():
    t = trial(interventions=["mHealth Supportive Care Program"])
    assert assign_modality(t) == "Device/Digital"


def test_device_digital_mobile_application_is_device_digital():
    t = trial(interventions=["Mobile-based application"])
    assert assign_modality(t) == "Device/Digital"


def test_behavioral_exercise_exercise_training_is_behavioral_exercise():
    t = trial(interventions=["12-week individualized aerobic exercise training"])
    assert assign_modality(t) == "Behavioral/Exercise"


def test_behavioral_exercise_cbt_is_behavioral_exercise():
    t = trial(interventions=["Cognitive Behavioral Therapy (CBT)"])
    assert assign_modality(t) == "Behavioral/Exercise"


def test_behavioral_exercise_questionnaire_is_behavioral_exercise():
    t = trial(interventions=["Questionnaire"])
    assert assign_modality(t) == "Behavioral/Exercise"


def test_small_molecule_drug_like_signals():
    t = trial(interventions=["Clarithromycin 500mg Tablets"])
    assert assign_modality(t) == "Small Molecule"


def test_default_interventional_with_nonempty_interventions_is_small_molecule():
    t = trial(interventions=["Guselkumab"])
    assert assign_modality(t) == "Small Molecule"


def test_precedence_procedure_beats_device_digital():
    # If both appear, we intentionally consider it Procedure/Radiation first
    t = trial(interventions=["Surgery with digital app follow-up"])
    assert assign_modality(t) == "Procedure/Radiation"


def test_precedence_device_digital_beats_drug_like():
    # Imaging text can include drug-like words in some trials; Device/Digital should win
    t = trial(interventions=["PET imaging with placebo control"])
    assert assign_modality(t) == "Device/Digital"


def test_precedence_behavioral_exercise_beats_drug_like():
    # Some behavioral studies mention "dose" or similar; Behavioral/Exercise should win
    t = trial(interventions=["Exercise training dose escalation schedule"])
    assert assign_modality(t) == "Behavioral/Exercise"
