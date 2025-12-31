# classifiers/drug_non_drug.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from policy.modality_policy import (
    DRUG_IDENTITY_REGEXES,
    DOSE_UNITS,
    DRUG_ROUTE_TERMS,
    NON_DRUG_EXCLUSION_TERMS,
)

# Compile identity regexes once.
_IDENTITY_RES = [re.compile(pat, re.IGNORECASE) for pat in DRUG_IDENTITY_REGEXES]

def _dose_regex_for_unit(unit: str) -> re.Pattern:
    """
    Match patterns like:
      - "500 mg",
      - "0.5 mg"
      - "2 mg/kg"
      - "10 mCi"
      - "370 MBq"
    Conservative: only numeric + unit + optional "/kg".
    """
    u = re.escape(unit)
    return re.compile(
        rf"\b\d+(\.\d+)?\s*{u}(\s*/\s*kg)?\b",
        re.IGNORECASE
    )

@dataclass(frozen=True)
class DrugEvidence:
    is_drug: bool
    reasons: List[str]
    matches: Dict[str, List[str]]


def _norm_join(interventions: List[str]) -> str:
    return " ".join([s for s in (interventions or []) if isinstance(s, str)]).strip()


def _find_identity_matches(text: str) -> List[str]:
    """
    Find strong drug identity signals.
    Regexes are treated as case-insensitive and applied to normalized text.
    """
    if not text:
        return []

    hits: List[str] = []
    for pattern in DRUG_IDENTITY_REGEXES:
        if re.search(pattern, text, flags=re.IGNORECASE):
            hits.append(pattern)
    return hits

# Compile dose regexes once at import time
_DOSE_RES = [_dose_regex_for_unit(u) for u in DOSE_UNITS]


def _find_dose_matches(text: str) -> List[str]:
    hits: List[str] = []
    for rx in _DOSE_RES:
        m = rx.search(text)
        if m:
            hits.append(m.group(0))
    return hits


def _has_any_token(text: str, tokens: List[str]) -> Tuple[bool, List[str]]:
    found: List[str] = []
    for t in tokens:
        if not t:
            continue
        if t.lower() in text:
            found.append(t)
    return (len(found) > 0, found)

def _all_interventions_are_exclusions(interventions: List[str], exclusions: List[str]) -> bool:
    """
    True if every non-empty intervention string contains only exclusion concepts
    and does not contain strong drug identity patterns.
    Conservative: used only to strengthen non-drug calls.
    """
    cleaned = [s.strip() for s in (interventions or []) if isinstance(s, str) and s.strip()]
    if not cleaned:
        return False

    for s in cleaned:
        low = s.lower()
        # If any intervention has identity signal, it's not "placebo-only"
        if _find_identity_matches(s):
            return False
        # If any intervention lacks exclusion tokens entirely, it's not placebo-only
        has_excl, _ = _has_any_token(low, exclusions)
        if not has_excl:
            return False
    return True

def drug_evidence(trial: Any) -> DrugEvidence:
    """
    Conservative drug vs non-drug evidence extractor.

    Decision rule:
      Drug = Identity OR (Dose AND Route/Form)

    Raw LaTeX:
    ```latex
    \text{Drug} = \text{Identity} \lor (\text{Dose} \land \text{Route})
    ```
    """
    interventions = getattr(trial, "interventions", None) or []
    raw = _norm_join(interventions)
    title = getattr(trial, "title", "") or ""

    raw_l = raw.lower()
    title_l = title.lower()

    identity_hits = _find_identity_matches(raw_l) or _find_identity_matches(title_l)

    if not raw_l and not title_l:
        return DrugEvidence(is_drug=False, reasons=["no_text"], matches={})

    text = raw_l  # keep rest of logic on normalized interventions text

    # Exclusion terms (for placebo-only or other explicitly non-drug tokens).
    has_excl, excl_hits = _has_any_token(text, NON_DRUG_EXCLUSION_TERMS)

# If exclusions appear but there's no strong evidence, only force non-drug
# when interventions are truly placebo/sham/vehicle-only.
    if has_excl and _all_interventions_are_exclusions(interventions, NON_DRUG_EXCLUSION_TERMS):
        return DrugEvidence(
            is_drug=False,
            reasons=["placebo_sham_vehicle_only"],
            matches={"exclusion": excl_hits},
        )

    dose_hits = _find_dose_matches(text)
    has_route, route_hits = _has_any_token(text, DRUG_ROUTE_TERMS)

    if dose_hits and has_route:
        return DrugEvidence(
            is_drug=True,
            reasons=["dose_and_route"],
            matches={"dose": dose_hits, "route": route_hits},
        )

    # If we got here, we did not find strong drug evidence.
    # If "placebo" (or other exclusions) appears without strong evidence, force non-drug.
    if has_excl:
        return DrugEvidence(
            is_drug=False,
            reasons=["exclusion_without_strong_evidence"],
            matches={"exclusion": excl_hits, "dose": dose_hits, "route": route_hits},
        )

    return DrugEvidence(
        is_drug=False,
        reasons=["no_strong_drug_evidence"],
        matches={"dose": dose_hits, "route": route_hits},
    )


def is_drug_trial(trial: Any) -> bool:
    """
    Convenience wrapper. Returns a boolean only.
    """
    return drug_evidence(trial).is_drug
