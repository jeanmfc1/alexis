from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


@dataclass
class ClinicalTrialSignal:
    # key fields to be updated as needed
    nct_id: str           # e.g. "NCT01234567", required
    title: str            # brief title, required

    phase: Optional[str] = None
    conditions: List[str] = field(default_factory=list)

    interventions: List[str] = field(default_factory=list)

    start_date: Optional[date] = None
    last_update_date: Optional[date] = None
    status: Optional[str] = None
    study_type: Optional[str] = None

    # To be filled using classifiers:
    therapeutic_area: Optional[str] = None
    modality: Optional[str] = None

    sponsor_type: Optional[str] = None  # e.g. "INDUSTRY", "NIH", "OTHER"
