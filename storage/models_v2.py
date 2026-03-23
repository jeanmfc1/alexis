from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Union

# These type aliases are semantic (no runtime enforcement)
# They match ClinicalTrials.gov semantic date formats.

# Date fully specified: yyyy-MM-dd
NormalizedDate = str

# Partial date: yyyy, yyyy-MM, or yyyy-MM-dd
PartialDate = str

# DateTime minutes: yyyy-MM-dd'T'HH:mm
DateTimeMinutes = str

# Normalized time string (if needed)
NormalizedTime = str


@dataclass
class DesignOutcomeV2:
    """
    A primary or secondary outcome measure from the study protocol.
    Maps to CT.gov outcomesModule / AACT design_outcomes table.
    """
    type: str                        # PRIMARY, SECONDARY, OTHER
    measure: str                     # e.g. "Overall Survival"
    time_frame: Optional[str] = None # e.g. "From randomization to 24 months"
    description: Optional[str] = None


@dataclass
class FacilityV2:
    """
    A study site / facility.
    Maps to CT.gov locationsModule / AACT facilities table.
    """
    name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    status: Optional[str] = None     # RECRUITING, COMPLETED, etc.


@dataclass
class UpdateCategoryV2:
    """
    A single categorized change detected by the update categorizer.
    One trial can have multiple UpdateCategoryV2 entries.
    """
    category: str                           # e.g. "status_to_recruiting", "enrollment_change"
    tier: int                               # 1 = high impact, 2 = medium, 3 = system
    direction: Optional[str] = None         # e.g. "enrollment_up", "from_not_yet"
    field_name: Optional[str] = None        # CT.gov field that changed
    old_value: Optional[object] = None
    new_value: Optional[object] = None
    delta: Optional[object] = None          # numeric delta if applicable
    delta_pct: Optional[str] = None         # e.g. "+133%"
    note: Optional[str] = None              # human-readable annotation


@dataclass
class LinkedTrialV2:
    """
    A linked trial detected by the phase linkage engine.
    Represents a probable phase advance across NCT IDs.
    """
    nct_id: str                             # the other NCT ID in the pair
    phase: Optional[str] = None             # phase of the linked trial
    link_confidence: Optional[float] = None # 0.0–1.0
    link_type: Optional[str] = None         # "phase_advance", "reformulation", etc.


@dataclass
class OutcomeAssessmentV2:
    """
    Pass/fail assessment for a completed trial.
    """
    assessment: str                         # "passed", "failed", "unknown"
    confidence: Optional[str] = None        # "high", "medium", "low"
    signals: List[str] = field(default_factory=list)  # evidence strings
    assessed_at: Optional[str] = None       # ISO date of assessment


@dataclass
class MeshTermV2:
    """
    Controlled vocabulary term from a browse module.
    Used for MeSH on conditions or interventions.
    """
    id: Optional[str]
    term: str


@dataclass
class InterventionV2:
    """
    A normalized intervention with role information.
    Only 'new experimental drugs' are kept in the final list.
    """
    name: str
    type: Optional[str] = None
    description: Optional[str] = None
    arm_group_labels: List[str] = field(default_factory=list)
    other_names: List[str] = field(default_factory=list)

    # Derived role (from arm type, e.g., Experimental, Active Comparator, Placebo)
    role: Optional[str] = None


@dataclass
class ClinicalTrialSignalV2:
    """
    A normalized representation of a clinical trial for ALEXIS V2.
    Interventions list contains only experimental new drugs.
    """

    # Core identity
    nct_id: str
    title: str

    # Narrative text fields (from AACT brief_summaries / detailed_descriptions
    # or CT.gov descriptionModule). Empty string if not available.
    brief_summary: str = ""
    detailed_description: str = ""

    # Conditions — raw list of strings
    conditions: List[str] = field(default_factory=list)

    # Study metadata
    study_type: Optional[str] = None
    phase: Optional[str] = None
    sponsor_class: Optional[str] = None

    # ── NEW: Status & enrollment ──────────────────────────
    # Maps to CT.gov statusModule.overallStatus / AACT studies.overall_status
    overall_status: Optional[str] = None  # RECRUITING, COMPLETED, TERMINATED, etc.

    # Maps to CT.gov designModule.enrollmentInfo / AACT studies.enrollment
    enrollment: Optional[int] = None
    enrollment_type: Optional[str] = None  # ACTUAL or ESTIMATED

    # Maps to CT.gov statusModule.whyStopped / AACT studies.why_stopped
    why_stopped: Optional[str] = None

    # ── NEW: Sponsor identity ─────────────────────────────
    # Maps to CT.gov sponsorCollaboratorsModule.leadSponsor.name / AACT sponsors.name
    sponsor_name: Optional[str] = None

    # ── NEW: Outcomes ─────────────────────────────────────
    # Maps to CT.gov outcomesModule / AACT design_outcomes table
    primary_outcomes: List[DesignOutcomeV2] = field(default_factory=list)
    secondary_outcomes: List[DesignOutcomeV2] = field(default_factory=list)

    # ── NEW: Facilities / study sites ─────────────────────
    # Maps to CT.gov locationsModule / AACT facilities table
    facilities: List[FacilityV2] = field(default_factory=list)
    facility_count: Optional[int] = None  # convenience: len(facilities)

    # ── NEW: Key protocol dates ───────────────────────────
    # Maps to CT.gov statusModule / AACT studies table
    start_date: Optional[PartialDate] = None
    completion_date: Optional[PartialDate] = None
    primary_completion_date: Optional[PartialDate] = None

    # Dates (posting dates — already existed)
    first_posted_date: Union[date, str, None] = None
    last_update_posted_date: Union[date, str, None] = None

    # Interventions
    interventions_all: List[InterventionV2] = field(default_factory=list)
    # Only new experimental drugs (filtered in normalization)
    interventions: List[InterventionV2] = field(default_factory=list)

    # Legacy intervention text (optional diagnostic use)
    interventions_text: List[str] = field(default_factory=list)

    # Arm map: label → arm type
    # e.g., {"Arm A": "Experimental", "Arm B": "Active Comparator"}
    arm_group_map: dict[str, str] = field(default_factory=dict)

    # MeSH derived for conditions
    condition_meshes: List[MeshTermV2] = field(default_factory=list)
    condition_mesh_ancestors: List[MeshTermV2] = field(default_factory=list)

    # MeSH derived for interventions
    # (optional semantic enrichment — not required for new drug detection)
    intervention_meshes: List[MeshTermV2] = field(default_factory=list)
    intervention_mesh_ancestors: List[MeshTermV2] = field(default_factory=list)

    # INFO flags
    info_flags: List[str] = field(default_factory=list)

    # classification outputs (persisted)
    therapeutic_area: Optional[str] = None
    is_drug_trial: Optional[bool] = None
    modality: Optional[str] = None

    # optional, future-proof
    modality_source: Optional[str] = None

    # intent output (computed in pipeline)
    study_intent: Optional[str] = None

    # data completeness flag (computed in pipeline)
    mesh_missing_condition: Optional[bool] = None

    # multi-TA detection provenance (computed in pipeline)
    therapeutic_areas_detected: List[str] = field(default_factory=list)

    # NEW: non-disease study categorization (computed in pipeline)
    study_category: Optional[str] = None
    study_category_evidence: List[str] = field(default_factory=list)

    # ── NEW: Update categorization outputs ────────────────
    # Populated by analytics/update_categorizer.py when diffing pulse vs. master

    # "new" if first seen in this pulse, "existing" if in master DB, None if not yet categorized
    update_type: Optional[str] = None

    # All detected changes, multiple allowed per trial
    update_categories: List[UpdateCategoryV2] = field(default_factory=list)

    # Phase linkage: link to related trial at different phase (cross-NCT)
    linked_from: Optional[LinkedTrialV2] = None

    # Outcome assessment for completed trials
    outcome: Optional[OutcomeAssessmentV2] = None


