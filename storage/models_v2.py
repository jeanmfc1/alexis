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

    # Conditions — raw list of strings
    conditions: List[str] = field(default_factory=list)

    # Study metadata
    study_type: Optional[str] = None
    phase: Optional[str] = None
    sponsor_class: Optional[str] = None

    # Dates
    first_posted_date: Union[date, str, None] = None
    last_update_posted_date: Union[date, str, None] = None

    # Interventions
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

