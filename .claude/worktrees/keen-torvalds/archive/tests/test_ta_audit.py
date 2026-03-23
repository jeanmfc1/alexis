from __future__ import annotations

from analytics.ta_audit import audit_trials
from policy.ta_policy import TA_MSK, TA_NEURO, TA_CARDIO


def _mismatches(infos):
    return [i for i in infos if i.assigned_ta != i.suggested_ta]


def test_audit_no_info_mismatches_for_known_cases():
    trials = [
        {
            "nct_id": "NCT_SUBACROMIAL",
            "title": "ChatGPT and DeepSeek-Assisted Rehabilitation in Subacromial Pain",
            "conditions": ["Subacromial Pain Syndrome"],
            "therapeutic_area": TA_MSK,
        },
        {
            "nct_id": "NCT_PATELLO",
            "title": "Adjunctive Effects of Heat vs Contrast Therapy With Otago Exercises on Patellofemoral Pain Syndrome",
            "conditions": ["Patellofemoral Pain Syndrome"],
            "therapeutic_area": TA_MSK,
        },
        {
            "nct_id": "NCT_ANT_KNEE",
            "title": "Muscle Strength Loss and Its Effect on Knee Cap Motion in Volunteers With Anterior Knee Pain",
            "conditions": ["Anterior Knee Pain", "Patellofemoral Pain Syndrome"],
            "therapeutic_area": TA_MSK,
        },
        {
            "nct_id": "NCT_NEUROMOD",
            "title": "Pain Intervention With Needling: Pilot Of Integrated Neuromodulation Techniques",
            "conditions": ["Pain"],
            "therapeutic_area": TA_NEURO,
        },
        {
            "nct_id": "NCT_SCS_STROKE",
            "title": "Closed Loop Spinal Cord Stimulation for Neuromodulation of Upper Motor Neuron Lesion Spasticity",
            "conditions": ["Chronic Pain", "Stroke", "Spasticity"],
            "therapeutic_area": TA_NEURO,
        },
        {
            "nct_id": "NCT_PHANTOM",
            "title": "Operant Conditioning of Sensory Brain Responses to Reduce Phantom Limb Pain in People With Limb Amputation",
            "conditions": ["Phantom Limb Pain After Amputation"],
            "therapeutic_area": TA_NEURO,
        },
        {
            "nct_id": "NCT_STROKE_CARDIO",
            "title": "Blood Pressure Control After Ischemic Stroke",
            "conditions": ["Ischemic Stroke"],
            "therapeutic_area": TA_CARDIO,
        },
    ]

    flags, infos, counts = audit_trials(trials)

    # No hard violations for these canonical examples
    assert flags == []

    # No INFO mismatches: assigned should match suggested (or audit should skip)
    assert _mismatches(infos) == []
