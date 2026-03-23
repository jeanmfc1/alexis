"""
analytics/shared.py
───────────────────
Shared constants and helper functions used across multiple analytics modules.

Import from here instead of duplicating across bd_wq*.py / mk_wq*.py etc.
"""

import re


# ── Modality complexity weights ────────────────────────────────────────────
# Used by: bd_wq1 (priority_score), ops_sq1 (workload forecast)
# Matched case-insensitively as substrings. More specific strings must come
# before broader ones (e.g. "gene" before "biolog").
#   cell/gene therapy       = 3×
#   radiopharmaceutical /
#     oligonucleotide       = 2.5×
#   mAb / biologic          = 2×
#   vaccine                 = 1.5×
#   small molecule / other  = 1×  (default)

MODALITY_COMPLEXITY: list[tuple[str, float]] = [
    ("gene",        3.0),
    ("cell",        3.0),
    ("radio",       2.5),
    ("oligo",       2.5),
    ("monoclonal",  2.0),
    ("mab",         2.0),
    ("biolog",      2.0),
    ("vaccin",      1.5),
]
MODALITY_COMPLEXITY_DEFAULT = 1.0


def modality_weight(modality: str | None) -> float:
    """
    Return the complexity weight for a modality string.
    Matched case-insensitively against MODALITY_COMPLEXITY substrings.
    Returns MODALITY_COMPLEXITY_DEFAULT (1.0) if nothing matches.
    """
    if not modality:
        return MODALITY_COMPLEXITY_DEFAULT
    m = modality.lower()
    for substring, weight in MODALITY_COMPLEXITY:
        if substring in m:
            return weight
    return MODALITY_COMPLEXITY_DEFAULT


# ── Phase priority weights ─────────────────────────────────────────────────
# Earlier phase = higher urgency (Phase 1 sponsor is placing contracts now).

PHASE_PRIORITY: dict[str, int] = {
    "PHASE1": 4,
    "PHASE2": 3,
    "PHASE3": 2,
    "PHASE4": 1,
}
PHASE_PRIORITY_DEFAULT = 0


def phase_weight(phase: str | None) -> int:
    """
    Return the urgency weight for a phase string.
    Normalises common variants ("Phase 1", "PHASE1", "phase_1") to the
    canonical key used in PHASE_PRIORITY.
    Returns PHASE_PRIORITY_DEFAULT (0) if nothing matches.
    """
    if not phase:
        return PHASE_PRIORITY_DEFAULT
    key = re.sub(r"[^A-Z0-9]", "", phase.upper())
    if key.startswith("PHASE"):
        return PHASE_PRIORITY.get(key, PHASE_PRIORITY_DEFAULT)
    return PHASE_PRIORITY.get("PHASE" + key, PHASE_PRIORITY_DEFAULT)


# ── Phase complexity weights (ops workload) ────────────────────────────────
# Later phase = heavier workload (bigger trials, more regulatory burden).
# Contrast with phase_weight() above which measures BD urgency (reversed).
# Used by: ops_sq1 (sq10 workload forecast)

PHASE_COMPLEXITY: dict[str, float] = {
    "EARLY_PHASE1": 0.5,
    "PHASE1":       1.0,
    "PHASE1/PHASE2": 1.5,
    "PHASE2":       2.0,
    "PHASE2/PHASE3": 3.0,
    "PHASE3":       4.0,
    "PHASE4":       3.0,
}
PHASE_COMPLEXITY_DEFAULT = 1.0


def phase_complexity(phase: str | None) -> float:
    """
    Return the workload complexity weight for a phase string.
    Later phases score higher (Phase 3 = heaviest operational burden).
    Normalises common variants ("Phase 3", "PHASE3", "phase_3") to the
    canonical key used in PHASE_COMPLEXITY.
    Returns PHASE_COMPLEXITY_DEFAULT (1.0) if nothing matches.
    """
    if not phase:
        return PHASE_COMPLEXITY_DEFAULT
    key = re.sub(r"[^A-Z0-9/]", "", phase.upper())
    if key.startswith("PHASE"):
        return PHASE_COMPLEXITY.get(key, PHASE_COMPLEXITY_DEFAULT)
    return PHASE_COMPLEXITY.get("PHASE" + key, PHASE_COMPLEXITY_DEFAULT)


# ── Enrollment scale (ops workload) ───────────────────────────────────────
# Multiplier based on trial size.  A 5,000-patient Phase 3 is much more
# operational work than a 30-patient Phase 3.
# Used by: ops_sq1 (sq10 workload forecast)
#
# Buckets derived from actual enrollment distribution in master DB:
#   <=50   → 38.8% of trials, only 2.4% of patient volume  (tiny)
#   51-200 → 38.6% of trials, 8.7% of patient volume       (baseline)
#   201-500→ 13.8% of trials, 9.5% of patient volume       (medium)
#   501-2k → 7.1% of trials, 13.6% of patient volume       (large)
#   >2000  → 1.7% of trials, 65.9% of patient volume       (mega)

ENROLLMENT_SCALE: list[tuple[int, float]] = [
    (50,    0.5),    # tiny study, minimal ops burden
    (200,   1.0),    # baseline — typical Phase 1/2
    (500,   1.5),    # medium — needs dedicated resources
    (2000,  2.0),    # large — multi-site coordination
]
ENROLLMENT_SCALE_MAX = 2.5   # mega-trial — full team allocation


def enrollment_scale(enrollment: int | None) -> float:
    """
    Return the workload scale multiplier for a trial enrollment count.
    Larger trials get higher multipliers.
    Returns 1.0 (baseline) if enrollment is missing or zero.
    """
    if not enrollment or enrollment <= 0:
        return 1.0
    for threshold, scale in ENROLLMENT_SCALE:
        if enrollment <= threshold:
            return scale
    return ENROLLMENT_SCALE_MAX


# ── Misc helpers ───────────────────────────────────────────────────────────

def human_mod(s: str | None) -> str:
    """'small_molecule' -> 'Small Molecule'  (mirrors the JS humanMod helper)"""
    return (s or "Unknown").replace("_", " ").title()


# ── Assay platform mapping (ops workload) ─────────────────────────────────
# Derived from modality — determines which lab bench / analyst pool handles
# the trial.  Used by: ops_sq1 (sq10 workload forecast)
#
# LCMS  = Liquid Chromatography-Mass Spectrometry  (small molecules)
# LBA   = Ligand Binding Assay  (large molecules: mAbs, biologics, vaccines)

PLATFORM_MAP: list[tuple[str, str]] = [
    ("small_molecule",        "LCMS"),
    ("radio",                 "LCMS"),
    ("gene",                  "LBA"),
    ("cell",                  "LBA"),
    ("monoclonal",            "LBA"),
    ("mab",                   "LBA"),
    ("biolog",                "LBA"),
    ("vaccin",                "LBA"),
    ("oligo",                 "Hybrid"),
]
PLATFORM_DEFAULT = "LCMS"


def assay_platform(modality: str | None) -> str:
    """
    Return the likely assay platform for a modality string.
    Matched case-insensitively as substrings (same pattern as modality_weight).
    Returns 'LCMS' by default (small molecule is the most common).
    """
    if not modality:
        return PLATFORM_DEFAULT
    m = modality.lower()
    for substring, platform in PLATFORM_MAP:
        if substring in m:
            return platform
    return PLATFORM_DEFAULT
