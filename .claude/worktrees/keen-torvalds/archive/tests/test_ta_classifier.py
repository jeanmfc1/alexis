from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pytest

from classifiers.therapeutic_area import assign_therapeutic_area
from policy.ta_policy import (
    TA_MSK,
    TA_NEURO,
    TA_CARDIO,
)


@dataclass
class TrialStub:
    # Minimal interface used by assign_therapeutic_area()
    title: Optional[str]
    conditions: List[str]


@pytest.mark.parametrize(
    "title,conditions,expected",
    [
        # ---- MSK pain syndromes (your fixes) ----
        (
            "ChatGPT and DeepSeek-Assisted Rehabilitation in Subacromial Pain",
            ["Subacromial Pain Syndrome"],
            TA_MSK,
        ),
        (
            "Exploring the Relationship Between Range of Motion in Knee Rehabilitation Exercises and Pain in Patellofemoral Pain Syndrome",
            ["Patello Femoral Syndrome"],
            TA_MSK,
        ),
        (
            "Adjunctive Effects of Heat vs Contrast Therapy With Otago Exercises on Patellofemoral Pain Syndrome",
            ["Patellofemoral Pain Syndrome"],
            TA_MSK,
        ),
        (
            "Popliteus Muscle Release Versus Kinesio Taping",
            ["Patellofememoral Pain Syndrome", "Patellofemoral Pain Syndrome"],
            TA_MSK,
        ),
        (
            "Muscle Strength Loss and Its Effect on Knee Cap Motion in Volunteers With Anterior Knee Pain",
            ["Patellofemoral Pain Syndrome", "Anterior Knee Pain"],
            TA_MSK,
        ),

        # ---- Neuro pain mechanisms / neuromodulation (your fixes) ----
        (
            "Pain Intervention With Needling: Pilot Of Integrated Neuromodulation Techniques",
            ["Pain"],
            TA_NEURO,
        ),
        (
            "Closed Loop Spinal Cord Stimulation for Neuromodulation of Upper Motor Neuron Lesion Spasticity",
            ["Chronic Pain", "Stroke", "Spasticity"],
            TA_NEURO,
        ),
        (
            "Operant Conditioning of Sensory Brain Responses to Reduce Phantom Limb Pain in People With Limb Amputation",
            ["Phantom Limb Pain After Amputation"],
            TA_NEURO,
        ),

        # ---- Stroke routing sanity: stroke without neuro focus should remain cardio ----
        # This is a guardrail so your new stroke-focus terms don't accidentally flip every stroke trial.
        (
            "Blood Pressure Control After Ischemic Stroke",
            ["Ischemic Stroke"],
            TA_CARDIO,
        ),
    ],
)
def test_assign_therapeutic_area_rules(title: str, conditions: List[str], expected: str) -> None:
    trial = TrialStub(title=title, conditions=conditions)
    assert assign_therapeutic_area(trial) == expected
