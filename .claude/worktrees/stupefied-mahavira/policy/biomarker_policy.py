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

import logging
import re

logger = logging.getLogger(__name__)


# ── PK/PD patterns ───────────────────────────────────────────────────────
# High-confidence multi-word terms first, then guarded abbreviations.
_PKPD_PATTERNS = [
    re.compile(r"\bpharmacokinetic", re.I),
    re.compile(r"\bpharmacodynamic", re.I),
    re.compile(r"\bpk[\s/]pd\b", re.I),
    re.compile(r"\bbioavailability\b", re.I),
    re.compile(r"\bhalf[\s-]life\b", re.I),
    # "clearance" guarded — require PK context within 120 chars
    re.compile(r"\bclearance\b(?=.{0,120}(?:renal|creatinine|drug|plasma|hepatic|systemic|apparent|oral|metaboli))", re.I),
    re.compile(r"(?:renal|creatinine|drug|plasma|hepatic|systemic|apparent|oral|metaboli).{0,120}\bclearance\b", re.I),
    re.compile(r"\bvolume\s+of\s+distribution\b", re.I),
    # Guarded abbreviations: require nearby PK context
    re.compile(r"\b(?:plasma|serum|blood)\s+concentration", re.I),
    re.compile(r"\bC\s*max\b"),                       # case-sensitive (Cmax)
    re.compile(r"\bT\s*max\b"),                       # case-sensitive (Tmax)
    re.compile(r"\bAUC\s*(?:0|inf|\()", re.I),        # AUC0-inf, AUC(0-t) etc.
    # AUC with guard — bounded to 200 chars to avoid distant false positives
    re.compile(r"\bAUC\b(?=.{0,200}(?:concentration|exposure|pharmacokinetic|plasma))", re.I),
    re.compile(r"\btrough\s+(?:level|concentration)\b", re.I),
    re.compile(r"\bsteady[\s-]state\s+(?:concentration|level|exposure)\b", re.I),
    re.compile(r"\babsorption\s+rate\b", re.I),
    re.compile(r"\bdose[\s-]?proportionality\b", re.I),
]

# ── Immunogenicity patterns ──────────────────────────────────────────────
_IMMUNO_PATTERNS = [
    re.compile(r"\bimmunogenicity\b", re.I),
    re.compile(r"\banti[\s-]drug\s+antibod", re.I),
    re.compile(r"\bADA\b(?=.{0,200}(?:antibod|immunogenicity|titer|positive|incidence))", re.I),
    re.compile(r"\bneutralizing\s+antibod", re.I),
    re.compile(r"\bNAb\b(?=.{0,200}(?:antibod|neutraliz|titer|assay))", re.I),
    re.compile(r"\bbinding\s+antibod(?:y|ies)\b", re.I),
    re.compile(r"\btiter\b(?=.{0,200}(?:antibod|anti[\s-]drug|immunogenicity))", re.I),
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
    re.compile(r"\bMRD\b(?=.{0,200}(?:negative|positive|response|disease))", re.I),
    re.compile(r"\bpathological\s+complete\s+response\b", re.I),
    re.compile(r"\bpCR\b(?=.{0,200}(?:rate|response|patholog))", re.I),
    re.compile(r"\bPSA\b(?=.{0,200}(?:response|decline|level|prostate))", re.I),
    re.compile(r"\bCA[\s-]?125\b", re.I),
    re.compile(r"\bCEA\b(?=.{0,200}(?:level|marker|antigen|tumor|colorectal))", re.I),
    re.compile(r"\bAFP\b(?=.{0,200}(?:level|marker|alpha[\s-]?feto|hepato))", re.I),
]

# ── Safety Biomarker patterns ────────────────────────────────────────────
_SAFETY_BM_PATTERNS = [
    re.compile(r"\bsafety\s+biomarker", re.I),
    re.compile(r"\bliver\s+function\s+test", re.I),
    re.compile(r"\bhepat(?:ic|o)\s*toxicity\b", re.I),
    re.compile(r"\bcardiotoxicity\b", re.I),
    re.compile(r"\bnephrotoxicity\b", re.I),
    re.compile(r"\bneurotoxicity\b", re.I),
    re.compile(r"\bQTc\b(?=.{0,200}(?:prolong|interval|change|correct))", re.I),
    re.compile(r"\btroponin\b", re.I),
    re.compile(r"\bBNP\b(?=.{0,200}(?:cardiac|heart|natriuretic|level))", re.I),
    re.compile(r"\bNT[\s-]?proBNP\b", re.I),
    re.compile(r"\bcreatinine\s+clearance\b", re.I),
    re.compile(r"\beGFR\b", re.I),
    re.compile(r"\bALT\b(?=.{0,200}(?:elevation|increase|liver|hepat|transaminase|ULN))", re.I),
    re.compile(r"\bAST\b(?=.{0,200}(?:elevation|increase|liver|hepat|transaminase|ULN))", re.I),
    re.compile(r"\bbilirubin\b(?=.{0,200}(?:elevation|increase|liver|total|direct))", re.I),
    re.compile(r"\bcytokine\s+release\s+syndrome\b", re.I),
    re.compile(r"\bCRS\b(?=.{0,200}(?:grade|cytokine|syndrome|incidence))", re.I),
    re.compile(r"\bdose[\s-]?limiting\s+toxicit", re.I),
    re.compile(r"\bDLT\b(?=.{0,200}(?:toxicit|dose|evaluat|incidence))", re.I),
]

# ── Companion Diagnostics patterns ───────────────────────────────────────
_COMPANION_DX_PATTERNS = [
    re.compile(r"\bcompanion\s+diagnostic", re.I),
    re.compile(r"\bCDx\b", re.I),
    re.compile(r"\bHER[\s-]?2\b(?=.{0,200}(?:positive|negative|status|express|amplif|test))", re.I),
    re.compile(r"\bPD[\s-]?L1\b(?=.{0,200}(?:express|positive|score|status|stain|test))", re.I),
    re.compile(r"\bEGFR\b(?=.{0,200}(?:mutation|positive|exon|del|status|test))", re.I),
    re.compile(r"\bALK\b(?=.{0,200}(?:positive|rearrange|fusion|transloc|status|test))", re.I),
    re.compile(r"\bBRCA\b(?=.{0,200}(?:mutation|positive|carrier|status|test|deficien))", re.I),
    re.compile(r"\bROS[\s-]?1\b(?=.{0,200}(?:positive|rearrange|fusion|test))", re.I),
    re.compile(r"\bBRAF\b(?=.{0,200}(?:V600|mutation|positive|status|test))", re.I),
    re.compile(r"\bKRAS\b(?=.{0,200}(?:mutation|G12C|positive|status|test))", re.I),
    re.compile(r"\bMSI[\s-]?(?:H|high)\b", re.I),
    re.compile(r"\bmismatch\s+repair\s+deficien", re.I),
    re.compile(r"\bdMMR\b", re.I),
    re.compile(r"\btumor\s+mutational\s+burden\b", re.I),
    re.compile(r"\bTMB\b(?=.{0,200}(?:high|score|tumor|mutational))", re.I),
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


def classify_biomarkers(text: str) -> list[str]:
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



def classify_trial_biomarkers(trial: dict) -> dict[str, dict]:
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
        logger.debug(
            "classify_trial_biomarkers: no searchable segments for trial %s",
            trial.get("nct_id", "?"),
        )

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
                    # Extract the enclosing sentence (period to period)
                    # Fall back to ;\ or the whole segment if no periods
                    pos = m.start()
                    # Find sentence start: last period/semicolon before match
                    sent_start = 0
                    for delim in '.;':
                        idx = text.rfind(delim, 0, pos)
                        if idx != -1 and idx + 1 > sent_start:
                            sent_start = idx + 1
                    # Find sentence end: first period/semicolon after match
                    sent_end = len(text)
                    for delim in '.;':
                        idx = text.find(delim, m.end())
                        if idx != -1 and idx + 1 < sent_end:
                            sent_end = idx + 1
                    ctx = text[sent_start:sent_end].strip()
                    # Cap at 200 chars to keep payload reasonable
                    if len(ctx) > 200:
                        # Re-center on match within 200 chars
                        half = 100
                        c_start = max(sent_start, pos - half)
                        c_end = min(sent_end, pos + half)
                        ctx = text[c_start:c_end].strip()
                        if c_start > sent_start:
                            ctx = "…" + ctx
                        if c_end < sent_end:
                            ctx = ctx + "…"
                    evidence[category] = {
                        "trigger": m.group(),
                        "source": source_label,
                        "context": ctx,
                    }
                    found = True
                    break

    return evidence


