from types import SimpleNamespace

from analytics.modality_audit import audit_trials


def trial(
    *,
    nct_id="NCT00000000",
    study_type="INTERVENTIONAL",
    interventions=None,
    modality=None,
):
    return SimpleNamespace(
        nct_id=nct_id,
        study_type=study_type,
        interventions=list(interventions or []),
        modality=modality,
    )


def test_observational_mismatch_is_flagged():
    t = trial(
        nct_id="NCT1",
        study_type="OBSERVATIONAL",
        interventions=["Questionnaire"],
        modality="Behavioral/Exercise",
    )
    flags, infos, counts = audit_trials([t])
    assert any(f["type"] == "OBSERVATIONAL_MISMATCH" for f in flags)


def test_observational_correct_is_not_flagged():
    t = trial(
        nct_id="NCT2",
        study_type="OBSERVATIONAL",
        interventions=["Registry follow-up"],
        modality="Observational/Diagnostic",
    )
    flags, infos, counts = audit_trials([t])
    assert not flags


def test_empty_interventions_mismatch_is_flagged():
    t = trial(
        nct_id="NCT3",
        interventions=[],
        modality="Small Molecule",
    )
    flags, infos, counts = audit_trials([t])
    assert any(f["type"] == "EMPTY_INTERVENTIONS_MISMATCH" for f in flags)


def test_small_molecule_with_device_anchor_is_flagged():
    t = trial(
        nct_id="NCT4",
        interventions=["CPAP Device"],
        modality="Small Molecule",
    )
    flags, infos, counts = audit_trials([t])
    assert any(f["type"] == "NON_DRUG_ANCHOR_IN_SMALL_MOLECULE" for f in flags)


def test_small_molecule_default_generates_info_not_flag():
    t = trial(
        nct_id="NCT5",
        interventions=["Investigational Product XYZ"],
        modality="Small Molecule",
    )
    flags, infos, counts = audit_trials([t])

        # Should NOT be a hard flag (no procedure/device/behavioral anchors present)
    assert not any(f["type"] == "NON_DRUG_ANCHOR_IN_SMALL_MOLECULE" for f in flags)

    # Should be an INFO (small molecule label without drug evidence anchors)
    assert any(
        i["type"] in ("SMALL_MOLECULE_DEFAULTED", "SMALL_MOLECULE_NO_DRUG_ANCHOR")
        for i in infos
    )

def test_device_digital_without_anchor_is_info():
    t = trial(
        nct_id="NCT6",
        interventions=["Standard of care"],
        modality="Device/Digital",
    )
    flags, infos, counts = audit_trials([t])
    assert not flags
    assert any(i["type"] == "DEVICE_NO_ANCHOR" for i in infos)

def test_behavioral_without_anchor_is_info():
    t = trial(
        nct_id="NCT7",
        interventions=["Lifestyle modification program"],
        modality="Behavioral/Exercise",
    )
    flags, infos, counts = audit_trials([t])
    assert not flags
    assert any(i["type"] == "BEHAVIORAL_NO_ANCHOR" for i in infos)


def test_mixed_non_drug_signals_is_info():
    t = trial(
        nct_id="NCT8",
        interventions=["Surgery", "Post-op rehabilitation program", "mri SCAN"],
        modality="Procedure/Radiation",
    )
    flags, infos, counts = audit_trials([t])
    assert not flags
    assert any(i["type"] == "MIXED_NON_DRUG_SIGNALS" for i in infos)


def test_invalid_label_is_flagged():
    t = trial(
        nct_id="NCT9",
        interventions=["Tablet 10 mg"],
        modality="NotARealModality",
    )
    flags, infos, counts = audit_trials([t])
    assert any(f["type"] == "INVALID_LABEL" for f in flags)
