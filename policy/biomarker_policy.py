"""
policy/biomarker_policy.py
──────────────────────────
Biomarker category classification from trial outcome text.

Categories:
    PK/PD              — pharmacokinetics / pharmacodynamics endpoints
    Immunogenicity     — anti-drug antibody and related assays
    Efficacy Biomarker — tumor markers, ctDNA, response biomarkers
    Safety Biomarker   — organ toxicity markers (liver, cardiac, renal)
    Companion Dx       — companion diagnostics and predictive biomarkers

Each category uses compiled regex patterns with word boundaries and
context guards to avoid false positives (e.g. "PD" alone could mean
Parkinson's Disease, "AUC" could be a statistical measure).
"""

import re
from typing import List


# ── PK/PD patterns ───────────────────────────────────────────────────────
# High-confidence multi-word terms first, then guarded abbreviations.
_PKPD_PATTERNS = [
    re.compile(r"\bpharmacokinetic", re.I),
    re.compile(r"\bpharmacodynamic", re.I),
    re.compile(r"\bpk[\s/]pd\b", re.I),
    re.compile(r"\bbioavailability\b", re.I),
    re.compile(r"\bhalf[\s-]life\b", re.I),
    re.compile(r"\bclearance\b", re.I),
    re.compile(r"\bvolume\s+of\s+distribution\b", re.I),
    # Guarded abbreviations: require nearby PK context
    re.compile(r"\b(?:plasma|serum|blood)\s+concentration", re.I),
    re.compile(r"\bC\s*max\b"),                       # case-sensitive (Cmax)
    re.compile(r"\bT\s*max\b"),                       # case-sensitive (Tmax)
    re.compile(r"\bAUC\s*(?:0|inf|\()", re.I),        # AUC0-inf, AUC(0-t) etc.
    re.compile(r"\bAUC\b(?=.*(?:concentration|exposure|pharmacokinetic|plasma))", re.I),
    re.compile(r"\btrough\s+(?:level|concentration)\b", re.I),
    re.compile(r"\bsteady[\s-]state\s+(?:concentration|level|exposure)\b", re.I),
    re.compile(r"\babsorption\s+rate\b", re.I),
    re.compile(r"\bdose[\s-]?proportionality\b", re.I),
]

# ── Immunogenicity patterns ──────────────────────────────────────────────
_IMMUNO_PATTERNS = [
    re.compile(r"\bimmunogenicity\b", re.I),
    re.compile(r"\banti[\s-]drug\s+antibod", re.I),
    re.compile(r"\bADA\b(?=.*(?:antibod|immunogenicity|titer|positive|incidence))", re.I),
    re.compile(r"\bneutralizing\s+antibod", re.I),
    re.compile(r"\bNAb\b(?=.*(?:antibod|neutraliz|titer|assay))", re.I),
    re.compile(r"\bbinding\s+antibod(?:y|ies)\b", re.I),
    re.compile(r"\btiter\b(?=.*(?:antibod|anti[\s-]drug|immunogenicity))", re.I),
]

# ── Efficacy Biomarker patterns ──────────────────────────────────────────
_EFFICACY_BM_PATTERNS = [
    re.compile(r"\befficacy\s+biomarker", re.I),
    re.compile(r"\btumor\s+marker", re.I),
    re.compile(r"\bcirculating\s+tumor\s+(?:DNA|cell)", re.I),
    re.compile(r"\bctDNA\b", re.I),
    re.compile(r"\bliquid\s+biopsy\b", re.I),
    re.compile(r"\bbiomarker[\s-]+(?:endpoint|response|driven|guided)\b", re.I),
    re.compile(r"\bpredictive\s+(?:biomarker|marker)\b", re.I),
    re.compile(r"\bminimal\s+residual\s+disease\b", re.I),
    re.compile(r"\bMRD\b(?=.*(?:negative|positive|response|disease))", re.I),
    re.compile(r"\bpathological\s+complete\s+response\b", re.I),
    re.compile(r"\bpCR\b(?=.*(?:rate|response|patholog))", re.I),
    re.compile(r"\bPSA\b(?=.*(?:response|decline|level|prostate))", re.I),
    re.compile(r"\bCA[\s-]?125\b", re.I),
    re.compile(r"\bCEA\b(?=.*(?:level|marker|antigen|tumor|colorectal))", re.I),
    re.compile(r"\bAFP\b(?=.*(?:level|marker|alpha[\s-]?feto|hepato))", re.I),
]

# ── Safety Biomarker patterns ────────────────────────────────────────────
_SAFETY_BM_PATTERNS = [
    re.compile(r"\bsafety\s+biomarker", re.I),
    re.compile(r"\bliver\s+function\s+test", re.I),
    re.compile(r"\bhepat(?:ic|o)\s*toxicity\b", re.I),
    re.compile(r"\bcardiotoxicity\b", re.I),
    re.compile(r"\bnephrotoxicity\b", re.I),
    re.compile(r"\bneurotoxicity\b", re.I),
    re.compile(r"\bQTc\b(?=.*(?:prolong|interval|change|correct))", re.I),
    re.compile(r"\btroponin\b", re.I),
    re.compile(r"\bBNP\b(?=.*(?:cardiac|heart|natriuretic|level))", re.I),
    re.compile(r"\bNT[\s-]?proBNP\b", re.I),
    re.compile(r"\bcreatinine\s+clearance\b", re.I),
    re.compile(r"\beGFR\b", re.I),
    re.compile(r"\bALT\b(?=.*(?:elevation|increase|liver|hepat|transaminase|ULN))", re.I),
    re.compile(r"\bAST\b(?=.*(?:elevation|increase|liver|hepat|transaminase|ULN))", re.I),
    re.compile(r"\bbilirubin\b(?=.*(?:elevation|increase|liver|total|direct))", re.I),
    re.compile(r"\bcytokine\s+release\s+syndrome\b", re.I),
    re.compile(r"\bCRS\b(?=.*(?:grade|cytokine|syndrome|incidence))", re.I),
    re.compile(r"\bdose[\s-]?limiting\s+toxicit", re.I),
    re.compile(r"\bDLT\b(?=.*(?:toxicit|dose|evaluat|incidence))", re.I),
]

# ── Companion Diagnostics patterns ───────────────────────────────────────
_COMPANION_DX_PATTERNS = [
    re.compile(r"\bcompanion\s+diagnostic", re.I),
    re.compile(r"\bCDx\b", re.I),
    re.compile(r"\bHER[\s-]?2\b(?=.*(?:positive|negative|status|express|amplif|test))", re.I),
    re.compile(r"\bPD[\s-]?L1\b(?=.*(?:express|positive|score|status|stain|test))", re.I),
    re.compile(r"\bEGFR\b(?=.*(?:mutation|positive|exon|del|status|test))", re.I),
    re.compile(r"\bALK\b(?=.*(?:positive|rearrange|fusion|transloc|status|test))", re.I),
    re.compile(r"\bBRCA\b(?=.*(?:mutation|positive|carrier|status|test|deficien))", re.I),
    re.compile(r"\bROS[\s-]?1\b(?=.*(?:positive|rearrange|fusion|test))", re.I),
    re.compile(r"\bBRAF\b(?=.*(?:V600|mutation|positive|status|test))", re.I),
    re.compile(r"\bKRAS\b(?=.*(?:mutation|G12C|positive|status|test))", re.I),
    re.compile(r"\bMSI[\s-]?(?:H|high)\b", re.I),
    re.compile(r"\bmismatch\s+repair\s+deficien", re.I),
    re.compile(r"\bdMMR\b", re.I),
    re.compile(r"\btumor\s+mutational\s+burden\b", re.I),
    re.compile(r"\bTMB\b(?=.*(?:high|score|tumor|mutational))", re.I),
    re.compile(r"\bbiomarker[\s-]+select(?:ed|ion)\b", re.I),
]


# Category name → pattern list
BIOMARKER_CATEGORIES: dict[str, list[re.Pattern]] = {
    "PK/PD":             _PKPD_PATTERNS,
    "Immunogenicity":    _IMMUNO_PATTERNS,
    "Efficacy Biomarker": _EFFICACY_BM_PATTERNS,
    "Safety Biomarker":  _SAFETY_BM_PATTERNS,
    "Companion Dx":      _COMPANION_DX_PATTERNS,
}


def classify_biomarkers(text: str) -> List[str]:
    """
    Classify text into biomarker categories.

    Args:
        text: concatenated trial text (title + outcome measures + descriptions)

    Returns:
        Sorted list of matched category names (may be empty).
    """
    if not text:
        return []

    matched = []
    for category, patterns in BIOMARKER_CATEGORIES.items():
        for pat in patterns:
            if pat.search(text):
                matched.append(category)
                break  # one match per category is enough

    return sorted(matched)

def classify_biomarkers_with_evidence(text: str) -> dict[str, str]:
    """
    Classify text into biomarker categories and return the matched evidence.

    Like classify_biomarkers(), but returns a dict mapping each matched
    category name to the actual text snippet that triggered the match.
    Only the FIRST matching pattern per category is used.

    Args:
        text: concatenated trial text (title + outcome measures + descriptions)

    Returns:
        Dict of {category_name: matched_snippet}.
        Example: {"PK/PD": "pharmacokinetic", "Safety Biomarker": "liver function test"}
    """
    if not text:
        return {}

    evidence = {}
    for category, patterns in BIOMARKER_CATEGORIES.items():
        for pat in patterns:
            m = pat.search(text)
            if m:
                evidence[category] = m.group()
                break  # first match per category is enough

    return evidence


def classify_trial_biomarkers(trial: dict) -> dict:
    """
    Classify a trial into biomarker categories with rich evidence context.

    Instead of searching a flat concatenated string, this inspects each trial
    field separately so the evidence records *where* in the trial the match
    was found and provides surrounding context.

    Args:
        trial: dict with keys title, primary_outcomes, secondary_outcomes.

    Returns:
        Dict mapping matched category name to an evidence dict:
        {"trigger": <matched text>, "source": <field label>, "context": <snippet>}
    """
    if not trial:
        return {}

    # -- Build labelled segments -----------------------------------------
    segments: list[tuple[str, str]] = []

    title = trial.get("title") or ""
    if title:
        segments.append(("Title", title))

    for key, label in (("primary_outcomes", "Primary Outcome"),
                       ("secondary_outcomes", "Secondary Outcome")):
        outcomes = trial.get(key) or []
        for o in outcomes:
            if isinstance(o, dict):
                measure = o.get("measure") or ""
                description = o.get("description") or ""
            else:
                measure = getattr(o, "measure", "") or ""
                description = getattr(o, "description", "") or ""
            if measure:
                segments.append((label, measure))
            if description:
                segments.append((label, description))

    if not segments:
        return {}

    # -- Search each category --------------------------------------------
    evidence: dict[str, dict] = {}

    for category, patterns in BIOMARKER_CATEGORIES.items():
        found = False
        for pat in patterns:
            if found:
                break
            for source_label, text in segments:
                m = pat.search(text)
                if m:
                    start = max(0, m.start() - 50)
                    end = min(len(text), m.end() + 50)
                    ctx = text[start:end]
                    if start > 0:
                        ctx = "…" + ctx
                    if end < len(text):
                        ctx = ctx + "…"
                    evidence[category] = {
                        "trigger": m.group(),
                        "source": source_label,
                        "context": ctx,
                    }
                    found = True
                    break

    return evidence


def trial_biomarker_text(trial: dict) -> str:
    """
    Build searchable text from a trial dict by concatenating title and
    all primary/secondary outcome measure names and descriptions.

    Handles both dict and dataclass representations (master DB stores
    outcomes as lists of dicts with keys: type, measure, description,
    time_frame).
    """
    parts = [trial.get("title") or ""]

    for key in ("primary_outcomes", "secondary_outcomes"):
        outcomes = trial.get(key) or []
        for o in outcomes:
            if isinstance(o, dict):
                parts.append(o.get("measure") or "")
                parts.append(o.get("description") or "")
            else:
                # dataclass fallback
                parts.append(getattr(o, "measure", "") or "")
                parts.append(getattr(o, "description", "") or "")

    return " ".join(parts)
