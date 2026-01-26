from collections import Counter
from typing import Iterable

def audit_modality_info_flags(trials: Iterable) -> dict[str, int]:
    """
    Aggregate INFO flags across trials and return counts.
    """
    counter = Counter()

    for trial in trials:
        for flag in getattr(trial, "info_flags", []):
            counter[flag] += 1

    return dict(counter)
