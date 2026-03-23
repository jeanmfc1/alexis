"""
policy/biomarker_policy.py
──────────────────────────
Biomarker classification for ALEXIS.

Step 1 — is_biomarker_relevant()
    Determines whether a trial involves biomarker measurement relevant to
    bioanalytical laboratory work. Returns (relevant, confidence, reason).

Step 2 — extract_biomarker_targets()
    Identifies specific known targets, their role (inclusion/exclusion/
    measurement), and result_use (clinical/bioanalytical). Only run on
    trials that passed Step 1.

Changes from v1 (based on 1000-trial LLM evaluation):
    - Moved pharmacokinetic/pharmacodynamic to CONTEXT_UPGRADEABLE
      (pure PK without biomarker co-signal is not relevant)
    - Added ~20 new targets: NT-proBNP, BNP, Troponin, HbA1c, PSA, CRP,
      Insulin, GLP-1, HbF, Platelet, ANA, anti-dsDNA, Complement, IgE,
      Eosinophil, UACR, eGFR, DSA, CD30, CD123, CD34, HLA, Alzheimer's
      biomarkers, coagulation factors
    - Expanded existing patterns: ESR1, EGFR, MRD, KRAS/NRAS, BRCA/HRD, HER2
    - Tightened exclusion patterns for immunolog, marker, assay
    - Added imaging/physiological exclusion patterns
    - Added safety_lab and pathology_confirmation flags to TARGET_METADATA

Changes from v2 (based on 14,000-trial LLM evaluation — Q4 2025):
    - Added brief_summary and detailed_description to segments searched by
      is_biomarker_relevant() — these fields contain dense biomarker language
      that was previously invisible to the classifier
    - Added brief_summary and detailed_description to Pass 2 of
      extract_biomarker_targets() so targets mentioned in narrative text are
      captured with role=measurement
    - master_DB patched to include these fields (master_DB_2025_Q4_patched_v2.json)
"""

import re
from typing import List


# ── Step 1 patterns ───────────────────────────────────────────────────────────

# High confidence — term alone is sufficient, negation check applied
HIGH_CONFIDENCE_PATTERNS = [
    re.compile(r"\bbiomarker\b", re.I),
    re.compile(r"\bimmunogenicity\b", re.I),
    re.compile(r"\banti[\s-]drug\s+antibod", re.I),
    re.compile(r"\bcompanion\s+diagnostic", re.I),
    re.compile(r"\bELISpot\b", re.I),
    re.compile(r"\bminimal\s+residual\s+disease\b", re.I),
    re.compile(r"\bmeasurable\s+residual\s+disease\b", re.I),
    re.compile(r"\bliquid\s+biopsy\b", re.I),
    re.compile(r"\bctDNA\b", re.I),
    re.compile(r"\bcirculating\s+tumor\s+DNA\b", re.I),
]

# Context upgradeable — each tuple:
# (term_pat, [context_pats], [exclusion_pats], require_context)
# require_context=True → no context match returns False (not medium)
# require_context=False → no context match returns medium confidence
CONTEXT_UPGRADEABLE = [

    # ── Pharmacokinetic — require_context=True ───────────────────────────────
    # Pure PK (drug concentration only) is NOT relevant.
    # Only relevant when co-occurring with a biomarker signal.
    (
        re.compile(r"\bpharmacokinetic", re.I),
        [re.compile(r"\bbiomarker\b", re.I),
         re.compile(r"\bimmunogenicity\b", re.I),
         re.compile(r"\banti[\s-]drug\s+antibod", re.I),
         re.compile(r"\bADA\b", re.I),
         re.compile(r"\bELISA\b", re.I),
         re.compile(r"\bLBA\b", re.I),
         re.compile(r"\bLC[\s-]?MS\b", re.I),
         re.compile(r"\bflow\s+cytometry\b", re.I),
         re.compile(r"\banalyte\b", re.I),
         re.compile(r"\bbioanalytical\b", re.I)],
        [],
        True,   # require_context — no match = not relevant
    ),

    # ── Pharmacodynamic — require_context=True ───────────────────────────────
    (
        re.compile(r"\bpharmacodynamic", re.I),
        [re.compile(r"\bbiomarker\b", re.I),
         re.compile(r"\bimmunogenicity\b", re.I),
         re.compile(r"\banalyte\b", re.I),
         re.compile(r"\banti[\s-]drug\s+antibod", re.I),
         re.compile(r"\bELISA\b", re.I),
         re.compile(r"\bLBA\b", re.I),
         re.compile(r"\bflow\s+cytometry\b", re.I),
         re.compile(r"\bprotein\b", re.I),
         re.compile(r"\bcytokine\b", re.I)],
        [re.compile(r"\bspirometry\b|\bFEV1\b|\bFVC\b", re.I),
         re.compile(r"\bhemodynamic\b", re.I)],
        True,   # require_context
    ),

    # ── Immunolog ────────────────────────────────────────────────────────────
    (
        re.compile(r"\bimmunolog", re.I),
        # require_context=False below — unconfirmed = medium (not False)
        [re.compile(r"\bassay\b", re.I),
         re.compile(r"\bmeasure", re.I),
         re.compile(r"\bblood\b|\bserum\b|\bplasma\b", re.I),
         re.compile(r"\bcell\s+(?:count|response|activity)\b", re.I),
         re.compile(r"\bELISpot\b", re.I),
         re.compile(r"\bflow\s+cytometry\b", re.I),
         re.compile(r"\bcytokine\b", re.I),
         re.compile(r"\bantibod", re.I),
         re.compile(r"\btiter\b", re.I),
         re.compile(r"\bresponse\s+(?:rate|level|titer)\b", re.I)],
        # Exclusions: immunologic as disease category, not measurement
        [re.compile(r"\bimmunolog(?:ic|ical)\s+(?:disorder|disease|condition|dysfunction)\b", re.I),
         re.compile(r"\bhistory\s+of.*immunolog", re.I),
         re.compile(r"\bno\s+(?:known\s+)?immunolog", re.I),
         # Exclude immunotherapy clinical outcome trials
         re.compile(r"\bimmunotherapy\b(?!.*(?:assay|titer|antibod|cytokine|flow))", re.I)],
    ),

    # ── Serum/plasma level/concentration ────────────────────────────────────
    (
        re.compile(r"\b(?:serum|plasma)\s+(?:level|concentration)\b", re.I),
        [re.compile(r"\bbaseline\b", re.I),
         re.compile(r"\bpre[\s-]?dose\b", re.I),
         re.compile(r"\bpost[\s-]?dose\b", re.I),
         re.compile(r"\btrough\b", re.I),
         re.compile(r"\btime[\s-]?point", re.I),
         re.compile(r"\bof\s+\w+", re.I)],
        # Exclude safety chemistry
        [re.compile(r"\bcreatinine\b", re.I),
         re.compile(r"\belectrolyte", re.I),
         re.compile(r"\brenal\s+function", re.I),
         re.compile(r"\bliver\s+function", re.I),
         re.compile(r"\bsodium\b|\bpotassium\b|\bchloride\b", re.I)],
    ),

    # ── Expression level/status/of ───────────────────────────────────────────
    (
        re.compile(r"\bexpression\s+(?:level|status|of)\b", re.I),
        [re.compile(r"\bprotein\b", re.I),
         re.compile(r"\bgene\b", re.I),
         re.compile(r"\bmRNA\b", re.I),
         re.compile(r"\breceptor\b", re.I),
         re.compile(r"\btumor\b", re.I),
         re.compile(r"\bIHC\b", re.I),
         re.compile(r"\bflow\s+cytometry\b", re.I),
         re.compile(r"\bantigen\b", re.I),
         re.compile(r"\bCD\d+\b", re.I),
         re.compile(r"\bpositive\b|\bnegative\b", re.I),
         re.compile(r"\b(?:absence|presence)\s+of\b", re.I)],
        # Exclude symptom/clinical expression
        [re.compile(r"\bsymptom\b|\bclinical\s+expression\b", re.I)],
    ),

    # ── Analyte ──────────────────────────────────────────────────────────────
    (
        re.compile(r"\banalyte\b", re.I),
        [re.compile(r"\bmeasure", re.I),
         re.compile(r"\bquantif", re.I),
         re.compile(r"\bdetect", re.I),
         re.compile(r"\bsample\b", re.I),
         re.compile(r"\bconcentration\b", re.I)],
        [],
    ),

    # ── Assay ────────────────────────────────────────────────────────────────
    (
        re.compile(r"\bassay\b", re.I),
        [re.compile(r"\bligand[\s-]?binding\b", re.I),
         re.compile(r"\bELISA\b", re.I),
         re.compile(r"\bLC[\s-]?MS\b", re.I),
         re.compile(r"\bflow\s+cytometry\b", re.I),
         re.compile(r"\bvalidat", re.I),
         re.compile(r"\bquantit", re.I),
         re.compile(r"\bELISpot\b", re.I),
         re.compile(r"\bclonoSEQ\b", re.I),
         re.compile(r"\bRT[\s-]?PCR\b", re.I),
         re.compile(r"\bqPCR\b|\bddPCR\b", re.I),
         re.compile(r"\bhemagglutination\s+inhibition\b", re.I),
         re.compile(r"\bopsonophagocytic\b", re.I),
         re.compile(r"\bneutralization\b", re.I),
         re.compile(r"\bMSD\b|\bGyros\b|\bSIMOA\b", re.I),
         re.compile(r"\bnext[\s-]?generation\s+sequencing\b", re.I),
         re.compile(r"\bNGS\b", re.I),
         re.compile(r"\bmeasured\s+by\b", re.I),
         re.compile(r"\bquantified\s+(?:by|using|in)\b", re.I),
         re.compile(r"\bdetected\s+(?:by|using)\b", re.I),
         re.compile(r"\busing\s+a\b", re.I),
         re.compile(r"\btiter\b", re.I),
         re.compile(r"\bantibod", re.I),
         re.compile(r"\bviral\s+load\b", re.I),
         re.compile(r"\bsample\s+(?:collection|processing)\b", re.I)],
        # Exclude non-bioanalytical assay contexts
        [re.compile(r"\bcognitive\s+assay\b", re.I),
         re.compile(r"\bneuropsychological\b", re.I),
         # Exclude microbial culture/diagnostic assays
         re.compile(r"\bculture\s+assay\b|\bmicrobial\s+assay\b", re.I),
         re.compile(r"\bC\.\s+difficile\s+assay\b", re.I),
         re.compile(r"\burine\s+culture\b", re.I)],
    ),

    # ── Marker ───────────────────────────────────────────────────────────────
    (
        re.compile(r"\bmarker\b", re.I),
        [re.compile(r"\btumor\s+marker\b", re.I),
         re.compile(r"\bsurrogate\s+(?:marker|endpoint)\b", re.I),
         re.compile(r"\binflammatory\s+marker\b", re.I),
         re.compile(r"\bprognostic\s+marker\b", re.I),
         re.compile(r"\bpredictive\s+marker\b", re.I),
         re.compile(r"\bgenetic\s+marker\b", re.I),
         re.compile(r"\bserum\b|\bplasma\b|\bblood\b|\btissue\b", re.I)],
        # Exclude imaging/radiographic markers
        [re.compile(r"\bfiducial\s+marker\b", re.I),
         re.compile(r"\blesion\s+marker\b", re.I),
         re.compile(r"\bimaging\s+marker\b|\bradiograph", re.I),
         re.compile(r"\bRECIST\b|\bRANO\b|\bMacdonald\b", re.I),
         # Exclude clinical rating scale markers
         re.compile(r"\bclinical\s+marker\b|\bsymptom\s+marker\b", re.I)],
    ),
]

# ── Negation ──────────────────────────────────────────────────────────────────

NEGATION_PATTERNS = [
    re.compile(r"\bnot\b", re.I),
    re.compile(r"\bno\b", re.I),
    re.compile(r"\bwithout\b", re.I),
    re.compile(r"\bnone\b", re.I),
    re.compile(r"\bwas\s+not\b", re.I),
    re.compile(r"\bwere\s+not\b", re.I),
    re.compile(r"\bdid\s+not\b", re.I),
    re.compile(r"\bwill\s+not\b", re.I),
    re.compile(r"\bnot\s+assessed\b", re.I),
    re.compile(r"\bnot\s+collected\b", re.I),
    re.compile(r"\bnot\s+included\b", re.I),
    re.compile(r"\bnot\s+performed\b", re.I),
    re.compile(r"\bnot\s+required\b", re.I),
    re.compile(r"\bexcluding\b", re.I),
    re.compile(r"\bexcludes\b", re.I),
]
NEGATION_WINDOW = 60


def is_negated(text: str, match: re.Match) -> bool:
    window_start  = max(0, match.start() - NEGATION_WINDOW)
    window_before = text[window_start:match.start()]
    window_end    = min(len(text), match.end() + NEGATION_WINDOW)
    window_after  = text[match.end():window_end]
    sent_start = max(
        text.rfind('.', 0, match.start()),
        text.rfind(';', 0, match.start()),
        text.rfind('\n', 0, match.start()),
        0
    )
    sent_end_candidates = [
        text.find('.', match.end()),
        text.find(';', match.end()),
        text.find('\n', match.end()),
    ]
    sent_end   = min((i for i in sent_end_candidates if i != -1), default=len(text))
    sentence   = text[sent_start:sent_end]
    check_text = window_before + " " + window_after + " " + sentence
    return any(neg.search(check_text) for neg in NEGATION_PATTERNS)


def same_sentence(text: str, pat1: re.Pattern, pat2: re.Pattern) -> bool:
    for sentence in re.split(r'[.;]\s*', text):
        if pat1.search(sentence) and pat2.search(sentence):
            return True
    return False


def is_biomarker_relevant(trial: dict) -> tuple[bool, str, str]:
    """
    Returns (is_relevant, confidence, reason).
    confidence: 'high' | 'medium'
    reason: human-readable evidence string
    """
    segments = {
        "title":                trial.get("title", "") or "",
        "brief_summary":        trial.get("brief_summary", "") or "",
        "detailed_description": trial.get("detailed_description", "") or "",
        "primary_outcome":      " ".join(
            f"{o.get('measure','')} {o.get('description','')}"
            for o in trial.get("primary_outcomes", [])
        ),
        "secondary_outcome":    " ".join(
            f"{o.get('measure','')} {o.get('description','')}"
            for o in trial.get("secondary_outcomes", [])
        ),
        "eligibility":          trial.get("eligibility_criteria", "") or "",
    }

    full_text = " ".join(segments.values())

    # High confidence — term alone is sufficient
    for source, text in segments.items():
        for pat in HIGH_CONFIDENCE_PATTERNS:
            m = pat.search(text)
            if m and not is_negated(text, m):
                return True, "high", f'"{m.group()}" in {source}'

    # Known target check — if any BIOMARKER_TARGETS pattern fires anywhere,
    # the trial is high confidence relevant. This catches HER2/EGFR/etc in
    # eligibility text that don't match language patterns.
    for target, patterns in BIOMARKER_TARGETS.items():
        for source, text in segments.items():
            if not text:
                continue
            for pat in patterns:
                m = pat.search(text)
                if m and not is_negated(text, m):
                    return True, "high", f'"{m.group()}" ({target}) in {source}'

    # Context upgradeable — 4-element tuples include require_context flag
    for source, text in segments.items():
        for entry in CONTEXT_UPGRADEABLE:
            term_pat      = entry[0]
            context_pats  = entry[1]
            exclusion_pats = entry[2]
            require_context = entry[3] if len(entry) == 4 else False

            m = term_pat.search(text)
            if not m:
                continue
            if is_negated(text, m):
                continue
            excluded = any(ep.search(text) for ep in exclusion_pats)
            if excluded:
                continue
            confirmed = any(same_sentence(text, term_pat, cp) for cp in context_pats)
            if confirmed:
                ctx_match = next(
                    cp.search(text) for cp in context_pats
                    if same_sentence(text, term_pat, cp)
                )
                return (True, "high",
                        f'"{m.group()}" + "{ctx_match.group()}" in {source}')
            elif require_context:
                # No context found and context is required — skip, not relevant
                continue
            else:
                return (True, "medium",
                        f'"{m.group()}" in {source} (no context confirmed)')

    return False, "", ""


# ── Eligibility splitting ─────────────────────────────────────────────────────

def split_eligibility(text: str) -> tuple[str, str]:
    """Split eligibility text into inclusion and exclusion sections."""
    lower = text.lower()
    split_idx = lower.find("exclusion criteria")
    if split_idx == -1:
        return text, ""
    return text[:split_idx], text[split_idx:]


# ── Step 2 — biomarker target dictionary ─────────────────────────────────────

BIOMARKER_TARGETS: dict[str, list[re.Pattern]] = {

    # ── Immuno-oncology checkpoints ──────────────────────────────────────────
    "PD-L1":     [re.compile(r"\bPD[\s-]?L1\b", re.I)],
    "PD-1":      [re.compile(r"\bPD[\s-]?1\b", re.I)],
    "CTLA-4":    [re.compile(r"\bCTLA[\s-]?4\b", re.I)],
    "LAG-3":     [re.compile(r"\bLAG[\s-]?3\b", re.I)],
    "TIM-3":     [re.compile(r"\bTIM[\s-]?3\b", re.I)],

    # ── Solid tumor genes/targets ────────────────────────────────────────────
    "HER2":      [re.compile(r"\bHER[\s-]?2\b|\bERBB2\b", re.I)],
    "EGFR":      [re.compile(r"\bEGFR\b", re.I),
                  # Specific mutation notations
                  re.compile(r"\bexon\s*19\s*del(?:etion)?\b", re.I),
                  re.compile(r"\bL858R\b", re.I),
                  re.compile(r"\bT790M\b", re.I),
                  re.compile(r"\bC797S\b", re.I)],
    "KRAS":      [re.compile(r"\bKRAS\b", re.I),
                  re.compile(r"\bG12C\b(?=.*(?:KRAS|mutation|inhibit))", re.I)],
    "NRAS":      [re.compile(r"\bNRAS\b", re.I)],
    "BRAF":      [re.compile(r"\bBRAF\b", re.I),
                  re.compile(r"\bV600E\b", re.I),
                  re.compile(r"\bV600K\b", re.I)],
    "ALK":       [re.compile(r"\bALK\b(?=.*(?:rearrange|fusion|positive|inhibit|test|mutation|alteration))", re.I)],
    "ROS1":      [re.compile(r"\bROS[\s-]?1\b", re.I)],
    "MET":       [re.compile(r"\bMET\b(?=.*(?:amplif|exon|mutation|inhibit|overexpress|skip))", re.I),
                  re.compile(r"\bMET\s+exon\s*14\b", re.I)],
    "FGFR":      [re.compile(r"\bFGFR[\s-]?[1-4]?\b", re.I)],
    "NTRK":      [re.compile(r"\bNTRK[\s-]?[1-3]?\b", re.I)],
    "RET":       [re.compile(r"\bRET\b(?=.*(?:fusion|rearrange|mutation|inhibit|alteration))", re.I)],

    # ── Breast/gynecologic ───────────────────────────────────────────────────
    "BRCA":      [re.compile(r"\bBRCA[\s-]?[12]?\b", re.I),
                  re.compile(r"\bhomologous\s+recombination\s+deficien", re.I),
                  re.compile(r"\bHRD\b(?=.*(?:deficien|positive|status|score|test))", re.I)],
    "ESR1":      [re.compile(r"\bESR[\s-]?1\b", re.I),
                  re.compile(r"\bestrogen\s+receptor\b", re.I),
                  re.compile(r"\bER[\s-]?positive\b|\bER\+\b", re.I),
                  re.compile(r"\bhormone\s+receptor[\s-]?positive\b", re.I)],
    "PR":        [re.compile(r"\bprogesterone\s+receptor\b", re.I),
                  re.compile(r"\bPR[\s-]?positive\b|\bPR\+\b", re.I)],
    "PIK3CA":    [re.compile(r"\bPIK3CA\b", re.I)],

    # ── Genomic instability/MRD ──────────────────────────────────────────────
    "TMB":       [re.compile(r"\btumor\s+mutational\s+burden\b", re.I),
                  re.compile(r"\bTMB\b(?=.*(?:high|score|mutational))", re.I)],
    "MSI-H":     [re.compile(r"\bMSI[\s-]?H\b", re.I),
                  re.compile(r"\bmismatch\s+repair\s+deficien", re.I),
                  re.compile(r"\bdMMR\b", re.I),
                  re.compile(r"\bpMMR\b|\bMSS\b(?=.*(?:mismatch|microsatellite|status))", re.I)],
    "MRD":       [re.compile(r"\bminimal\s+residual\s+disease\b", re.I),
                  re.compile(r"\bmeasurable\s+residual\s+disease\b", re.I),
                  re.compile(r"\bMRD\b(?=.*(?:negative|positive|response|undetectable|assess|monitor))", re.I),
                  re.compile(r"\bNGS[\s-]?MRD\b", re.I),
                  re.compile(r"\bclonoSEQ\b", re.I),
                  re.compile(r"\bBCR[\s-]?ABL1\b(?=.*(?:transcript|MRD|response|reduction))", re.I)],

    # ── Liquid biopsy ────────────────────────────────────────────────────────
    "ctDNA":     [re.compile(r"\bctDNA\b", re.I),
                  re.compile(r"\bcirculating\s+tumor\s+DNA\b", re.I),
                  re.compile(r"\bliquid\s+biopsy\b", re.I),
                  re.compile(r"\bcirculating\s+tumor[\s-]?derived\s+DNA\b", re.I)],
    "CTC":       [re.compile(r"\bcirculating\s+tumor\s+cells?\b", re.I),
                  re.compile(r"\bCTC\b(?=.*(?:count|detect|tumor|circulating))", re.I)],

    # ── Hematologic surface markers ──────────────────────────────────────────
    "CD19":      [re.compile(r"\bCD19\b", re.I)],
    "CD20":      [re.compile(r"\bCD20\b", re.I)],
    "CD22":      [re.compile(r"\bCD22\b", re.I)],
    "CD38":      [re.compile(r"\bCD38\b", re.I)],
    "CD79b":     [re.compile(r"\bCD79b\b", re.I)],
    "CD3":       [re.compile(r"\bCD3\b", re.I)],
    "CD33":      [re.compile(r"\bCD33\b", re.I)],
    "CD47":      [re.compile(r"\bCD47\b", re.I)],
    "CD30":      [re.compile(r"\bCD30\b", re.I)],
    "CD123":     [re.compile(r"\bCD123\b", re.I)],
    "CD34":      [re.compile(r"\bCD34\b(?=.*(?:cell|count|positive|stem|CD34\+))", re.I)],
    "BCMA":      [re.compile(r"\bBCMA\b|\bB[\s-]?cell\s+maturation\s+antigen\b", re.I)],

    # ── Hematologic gene targets ─────────────────────────────────────────────
    "BCL-2":     [re.compile(r"\bBCL[\s-]?2\b", re.I)],
    "FLT3":      [re.compile(r"\bFLT[\s-]?3\b", re.I),
                  re.compile(r"\bFLT3[\s-]?ITD\b", re.I),
                  re.compile(r"\bFLT3[\s-]?TKD\b", re.I)],
    "IDH1":      [re.compile(r"\bIDH[\s-]?1\b", re.I)],
    "IDH2":      [re.compile(r"\bIDH[\s-]?2\b", re.I)],
    "JAK2":      [re.compile(r"\bJAK[\s-]?2\b", re.I)],
    "JAK1":      [re.compile(r"\bJAK[\s-]?1\b", re.I)],

    # ── Immunogenicity / PK ──────────────────────────────────────────────────
    "ADA":       [re.compile(r"\banti[\s-]drug\s+antibod", re.I),
                  re.compile(r"\bADA\b(?=.*(?:antibod|immunogenicity|titer|incidence|positive|test|assess))", re.I),
                  re.compile(r"\bneutralizing\s+antibod", re.I),
                  re.compile(r"\banti[\s-]drug\s+antibod", re.I),
                  re.compile(r"\bimmunogenicity\s+(?:test|assess|analys|detect)", re.I)],

    # ── Companion diagnostics ────────────────────────────────────────────────
    "PD-L1 CDx": [re.compile(r"\bPD[\s-]?L1\b(?=.*(?:IHC|22C3|28-8|SP142|CDx|score|TPS|CPS))", re.I)],
    "HER2 CDx":  [re.compile(r"\bHER[\s-]?2\b(?=.*(?:IHC|FISH|amplif|CDx|3\+|2\+|ISH|SISH|CISH))", re.I)],

    # ── Cytokines (confirmed Biosciences) ────────────────────────────────────
    "IL-6":      [re.compile(r"\bIL[\s-]?6\b|\binterleukin[\s-]?6\b", re.I)],
    "IL-17":     [re.compile(r"\bIL[\s-]?17\b|\binterleukin[\s-]?17\b", re.I)],
    "TNF":       [re.compile(r"\bTNF\b|\btumor\s+necrosis\s+factor\b|\bTNF[\s-]?alpha\b", re.I)],
    "VEGF":      [re.compile(r"\bVEGF\b|\bvascular\s+endothelial\s+growth\s+factor\b", re.I)],
    "VEGFR":     [re.compile(r"\bVEGFR[\s-]?[123]?\b", re.I)],

    # ── Other targeted therapies ─────────────────────────────────────────────
    "mTOR":      [re.compile(r"\bmTOR\b", re.I)],
    "CDK4/6":    [re.compile(r"\bCDK[\s-]?4\b|\bCDK[\s-]?6\b|\bCDK4/6\b", re.I)],
    "PARP":      [re.compile(r"\bPARP\b|\bpoly\s+ADP[\s-]?ribose\b", re.I)],
    "AR":        [re.compile(r"\bandrogen\s+receptor\b", re.I),
                  re.compile(r"\bAR\b(?=.*(?:positive|express|signaling|pathway|splice\s+variant))", re.I)],

    # ── Inflammatory/autoimmune ──────────────────────────────────────────────
    "CRP":       [re.compile(r"\bC[\s-]?reactive\s+protein\b", re.I),
                  re.compile(r"\bCRP\b(?=.*(?:level|mg|inflammation|serum|plasma|high[\s-]?sensitivity|hsCRP|hs[\s-]CRP))", re.I),
                  re.compile(r"\bhs[\s-]?CRP\b|\bhsCRP\b", re.I)],
    "ANA":       [re.compile(r"\bantinuclear\s+antibod", re.I),
                  re.compile(r"\bANA\b(?=.*(?:titer|positive|lupus|autoantibod|test))", re.I)],
    "anti-dsDNA":[re.compile(r"\banti[\s-]?ds[\s-]?DNA\b", re.I),
                  re.compile(r"\banti[\s-]?double\s+stranded\s+DNA\b", re.I)],
    "Complement":[re.compile(r"\bcomplement\s+[C34]\d?\b", re.I),
                  re.compile(r"\b[C34]\d?\s+(?:level|complement|deficien)\b", re.I)],
    "IgE":       [re.compile(r"\btotal\s+IgE\b|\bimmunoglobulin\s+E\b", re.I),
                  re.compile(r"\bsIgE\b|\bspecific\s+IgE\b|\bserum[\s-]?specific\s+IgE\b", re.I)],
    "Eosinophil":[re.compile(r"\beosinophil\s+count\b|\bblood\s+eosinophil\b", re.I),
                  re.compile(r"\beosinophil\s+(?:depletion|level|threshold)\b", re.I)],

    # ── Metabolic/endocrine ──────────────────────────────────────────────────
    "HbA1c":     [re.compile(r"\bHbA1c\b|\bHbA[\s-]1c\b", re.I),
                  re.compile(r"\bhemoglobin\s+A1c\b|\bglycated\s+h[ae]moglobin\b", re.I),
                  re.compile(r"\bglycated\s+albumin\b|\bGA\b(?=.*(?:glycat|albumin|diabetes))", re.I)],
    "PSA":       [re.compile(r"\bprostate[\s-]?specific\s+antigen\b", re.I),
                  re.compile(r"\bPSA\b(?=.*(?:prostate|level|response|ng|doubling|progression|biochem))", re.I)],
    "Insulin":   [re.compile(r"\bplasma\s+insulin\b|\bserum\s+insulin\b", re.I),
                  re.compile(r"\binsulin\s+(?:secretion|sensitivity|resistance|level|response)\b", re.I),
                  re.compile(r"\bHOMA[\s-]?(?:IR|beta)\b", re.I)],
    "GLP-1":     [re.compile(r"\bGLP[\s-]?1\b|\bglucagon[\s-]?like\s+peptide[\s-]?1\b", re.I)],
    "Glucagon":  [re.compile(r"\bplasma\s+glucagon\b|\bserum\s+glucagon\b", re.I),
                  re.compile(r"\bglucagon\s+(?:level|secretion|response|concentration)\b", re.I)],

    # ── Cardiac biomarkers ───────────────────────────────────────────────────
    "NT-proBNP": [re.compile(r"\bNT[\s-]?proBNP\b", re.I),
                  re.compile(r"\bN[\s-]?terminal\s+pro[\s-]?B[\s-]?type\s+natriuretic\b", re.I),
                  re.compile(r"\bNT[\s-]?pro[\s-]?B[\s-]?type\s+natriuretic\b", re.I)],
    "BNP":       [re.compile(r"\bBNP\b(?=.*(?:natriuretic|cardiac|heart|level|peptide))", re.I),
                  re.compile(r"\bB[\s-]?type\s+natriuretic\s+peptide\b", re.I)],
    "Troponin":  [re.compile(r"\btroponin\s+[TI]\b|\bcardiac\s+troponin\b|\bcTn[TI]\b", re.I),
                  re.compile(r"\bhs[\s-]?troponin\b|\bhigh[\s-]?sensitivity\s+troponin\b", re.I)],
    "TTR":       [re.compile(r"\bserum\s+transthyretin\b|\bserum\s+TTR\b", re.I),
                  re.compile(r"\bTTR\b(?=.*(?:transthyretin|ATTR|amyloid))", re.I)],

    # ── Hematology ───────────────────────────────────────────────────────────
    "HbF":       [re.compile(r"\bfetal\s+h[ae]moglobin\b|\bHbF\b", re.I)],
    "Platelet":  [re.compile(r"\bplatelet\s+count\b", re.I),
                  re.compile(r"\bthrombocytopenia\b(?=.*(?:response|complete|partial|criteria))", re.I)],

    # ── Renal biomarkers ─────────────────────────────────────────────────────
    "UACR":      [re.compile(r"\burine\s+albumin[\s-]?to[\s-]?creatinine\b", re.I),
                  re.compile(r"\bUACR\b", re.I),
                  re.compile(r"\burinary\s+albumin[\s-]?creatinine\s+ratio\b", re.I)],
    "eGFR":      [re.compile(r"\beGFR\b(?=.*(?:renal|kidney|filtration|function|decline|change))", re.I),
                  re.compile(r"\bestimated\s+glomerular\s+filtration\s+rate\b", re.I)],

    # ── Transplant/immune ────────────────────────────────────────────────────
    "DSA":       [re.compile(r"\bdonor[\s-]?specific\s+anti[\s-]?HLA\b", re.I),
                  re.compile(r"\bDSA\b(?=.*(?:antibod|Luminex|HLA|transplant))", re.I)],
    "HLA":       [re.compile(r"\bHLA[\s-]?[AB][*\s]?\d+\b", re.I),
                  re.compile(r"\bHLA\s+typ(?:ing|e)\b", re.I),
                  re.compile(r"\bHLA[\s-]?A\*\d+\b", re.I)],

    # ── Alzheimer's/neurodegeneration ────────────────────────────────────────
    "p-tau":     [re.compile(r"\bphospho(?:rylated)?[\s-]?tau\b", re.I),
                  re.compile(r"\bp[\s-]?tau[\s-]?\d+\b", re.I),
                  re.compile(r"\bCSF\s+(?:phospho|p[\s-]?)tau\b", re.I)],
    "Amyloid-b": [re.compile(r"\bamyloid[\s-]?(?:beta|β)[\s-]?(?:42|40|38)?\b", re.I),
                  re.compile(r"\bAβ[\s-]?\d+\b", re.I),
                  re.compile(r"\bCSF\s+amyloid\b", re.I)],

    # ── Viral markers ────────────────────────────────────────────────────────
    "HBsAg":     [re.compile(r"\bHBsAg\b|\bhepatitis\s+B\s+surface\s+antigen\b", re.I)],
    "HCV RNA":   [re.compile(r"\bHCV[\s-]?RNA\b", re.I),
                  re.compile(r"\bhepatitis\s+C.*viral\s+load\b", re.I),
                  re.compile(r"\bSVR\d*\b(?=.*(?:HCV|hepatitis|virolog))", re.I)],
    "HIV RNA":   [re.compile(r"\bHIV[\s-](?:RNA|viral\s+load)\b", re.I),
                  re.compile(r"\bHIV[\s-]?1\s+RNA\b", re.I)],
    "HBV DNA":   [re.compile(r"\bHBV\s+DNA\b|\bhepatitis\s+B\s+virus\s+DNA\b", re.I)],
}


# ── Target metadata ───────────────────────────────────────────────────────────

TARGET_METADATA: dict[str, dict] = {
    # Confirmed Biosciences
    "ADA":        {"type": "immunogenicity",   "bs_relevant": True,  "safety_lab": False},
    "IL-6":       {"type": "cytokine",          "bs_relevant": True,  "safety_lab": False},
    "IL-17":      {"type": "cytokine",          "bs_relevant": True,  "safety_lab": False},
    "TNF":        {"type": "cytokine",          "bs_relevant": True,  "safety_lab": False},
    "VEGF":       {"type": "cytokine",          "bs_relevant": True,  "safety_lab": False},
    "ctDNA":      {"type": "liquid_biopsy",     "bs_relevant": True,  "safety_lab": False},
    "CTC":        {"type": "liquid_biopsy",     "bs_relevant": True,  "safety_lab": False},
    "MRD":        {"type": "functional",        "bs_relevant": True,  "safety_lab": False},
    "GLP-1":      {"type": "cytokine",          "bs_relevant": True,  "safety_lab": False},
    "Glucagon":   {"type": "hormone",           "bs_relevant": True,  "safety_lab": False},
    "Insulin":    {"type": "hormone",           "bs_relevant": True,  "safety_lab": False},

    # Confirmed NOT Biosciences (safety screens or CDx/Central Labs)
    "HBsAg":      {"type": "viral_marker",      "bs_relevant": False, "safety_lab": True},
    "HCV RNA":    {"type": "viral_marker",       "bs_relevant": False, "safety_lab": True},
    "HIV RNA":    {"type": "viral_marker",       "bs_relevant": False, "safety_lab": True},
    "HBV DNA":    {"type": "viral_marker",       "bs_relevant": False, "safety_lab": False},
    "HER2 CDx":   {"type": "companion_dx",       "bs_relevant": False, "safety_lab": False},
    "PD-L1 CDx":  {"type": "companion_dx",       "bs_relevant": False, "safety_lab": False},

    # Needs Bo confirmation — cell surface proteins
    "PD-L1":      {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "PD-1":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "CTLA-4":     {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "LAG-3":      {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "TIM-3":      {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "HER2":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "VEGFR":      {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "AR":         {"type": "receptor",          "bs_relevant": None,  "safety_lab": False},
    "CD19":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "CD20":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "CD22":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "CD38":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "CD47":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "CD3":        {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "CD33":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "CD79b":      {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "CD30":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "CD123":      {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "CD34":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "BCMA":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},

    # Needs Bo confirmation — genes
    "EGFR":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "KRAS":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "NRAS":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "BRAF":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "ALK":        {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "ROS1":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "RET":        {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "MET":        {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "FGFR":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "NTRK":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "BRCA":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "ESR1":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "PR":         {"type": "receptor",          "bs_relevant": None,  "safety_lab": False},
    "PIK3CA":     {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "IDH1":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "IDH2":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "FLT3":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "JAK1":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "JAK2":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "BCL-2":      {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "CDK4/6":     {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "PARP":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "mTOR":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "TMB":        {"type": "functional",        "bs_relevant": None,  "safety_lab": False},
    "MSI-H":      {"type": "functional",        "bs_relevant": None,  "safety_lab": False},

    # Needs Bo confirmation — new additions
    "CRP":        {"type": "cytokine",          "bs_relevant": None,  "safety_lab": False},
    "ANA":        {"type": "autoantibody",      "bs_relevant": None,  "safety_lab": False},
    "anti-dsDNA": {"type": "autoantibody",      "bs_relevant": None,  "safety_lab": False},
    "Complement": {"type": "protein",           "bs_relevant": None,  "safety_lab": False},
    "IgE":        {"type": "immunoglobulin",    "bs_relevant": None,  "safety_lab": False},
    "Eosinophil": {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "NT-proBNP":  {"type": "cardiac_biomarker", "bs_relevant": None,  "safety_lab": False},
    "BNP":        {"type": "cardiac_biomarker", "bs_relevant": None,  "safety_lab": False},
    "Troponin":   {"type": "cardiac_biomarker", "bs_relevant": None,  "safety_lab": False},
    "TTR":        {"type": "protein",           "bs_relevant": None,  "safety_lab": False},
    "HbA1c":      {"type": "metabolic",         "bs_relevant": None,  "safety_lab": False},
    "PSA":        {"type": "tumor_marker",      "bs_relevant": None,  "safety_lab": False},
    "Insulin":    {"type": "hormone",           "bs_relevant": True,  "safety_lab": False},
    "HbF":        {"type": "hematology",        "bs_relevant": None,  "safety_lab": False},
    "Platelet":   {"type": "hematology",        "bs_relevant": None,  "safety_lab": False},
    "UACR":       {"type": "renal_biomarker",   "bs_relevant": None,  "safety_lab": False},
    "eGFR":       {"type": "renal_biomarker",   "bs_relevant": None,  "safety_lab": True},
    "DSA":        {"type": "autoantibody",      "bs_relevant": None,  "safety_lab": False},
    "HLA":        {"type": "genetic",           "bs_relevant": None,  "safety_lab": False},
    "p-tau":      {"type": "neurodegeneration", "bs_relevant": None,  "safety_lab": False},
    "Amyloid-b":  {"type": "neurodegeneration", "bs_relevant": None,  "safety_lab": False},
    "HBV DNA":    {"type": "viral_marker",      "bs_relevant": None,  "safety_lab": False},
}


# ── Step 2 — target extraction ────────────────────────────────────────────────

def extract_biomarker_targets(trial: dict) -> list[dict]:
    """
    Identify specific known biomarker targets in a trial.
    Only run on trials that passed is_biomarker_relevant().

    Returns list of dicts:
    {
        "target":      str,
        "type":        str,
        "bs_relevant": bool | None,
        "safety_lab":  bool,
        "source":      str,
        "role":        "inclusion" | "exclusion" | "measurement",
        "result_use":  "clinical" | "bioanalytical",
        "trigger":     str,
    }
    """
    results   = []
    found     = set()

    eligibility = trial.get("eligibility_criteria", "") or ""
    inclusion, exclusion = split_eligibility(eligibility)

    # Pass 1 — eligibility (role = inclusion or exclusion)
    for target, patterns in BIOMARKER_TARGETS.items():
        meta = TARGET_METADATA.get(target, {})
        for pat in patterns:
            m = pat.search(inclusion)
            if m and not is_negated(inclusion, m):
                results.append({
                    "target":      target,
                    "type":        meta.get("type"),
                    "bs_relevant": meta.get("bs_relevant"),
                    "safety_lab":  meta.get("safety_lab", False),
                    "source":      "eligibility_criteria",
                    "role":        "inclusion",
                    "result_use":  "clinical",
                    "trigger":     m.group(),
                })
                found.add(target)
                break

            m = pat.search(exclusion)
            if m and not is_negated(exclusion, m):
                results.append({
                    "target":      target,
                    "type":        meta.get("type"),
                    "bs_relevant": meta.get("bs_relevant"),
                    "safety_lab":  meta.get("safety_lab", False),
                    "source":      "eligibility_criteria",
                    "role":        "exclusion",
                    "result_use":  "clinical",
                    "trigger":     m.group(),
                })
                found.add(target)
                break

    # Pass 2 — outcome measures + narrative text (role = measurement)
    for outcome_type, key in [("primary_endpoint",    "primary_outcomes"),
                               ("secondary_endpoint",  "secondary_outcomes"),
                               ("brief_summary",       None),
                               ("detailed_description", None)]:
        if key is not None:
            outcome_text = " ".join(
                f"{o.get('measure', '')} {o.get('description', '')}"
                for o in trial.get(key, [])
            )
        else:
            outcome_text = trial.get(outcome_type, "") or ""

        for target, patterns in BIOMARKER_TARGETS.items():
            if target in found:
                continue
            meta = TARGET_METADATA.get(target, {})
            for pat in patterns:
                m = pat.search(outcome_text)
                if m and not is_negated(outcome_text, m):
                    results.append({
                        "target":      target,
                        "type":        meta.get("type"),
                        "bs_relevant": meta.get("bs_relevant"),
                        "safety_lab":  meta.get("safety_lab", False),
                        "source":      outcome_type,
                        "role":        "measurement",
                        "result_use":  "bioanalytical",
                        "trigger":     m.group(),
                    })
                    found.add(target)
                    break

    return results
