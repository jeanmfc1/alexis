from collections import Counter
from typing import Dict, List

from storage.models import ClinicalTrialSignal


def ta_modality_counts(trials: List[ClinicalTrialSignal]) -> Dict[str, Dict[str, int]]:
    """
    Returns nested dict:
      { TA: { Modality: count } }
    """
    out: Dict[str, Counter] = {}

    for t in trials:
        ta = t.therapeutic_area or "Unknown"
        mod = t.modality or "Unknown"
        out.setdefault(ta, Counter())[mod] += 1

    # convert Counter -> normal dict (JSON-friendly)
    return {ta: dict(counter) for ta, counter in out.items()}
