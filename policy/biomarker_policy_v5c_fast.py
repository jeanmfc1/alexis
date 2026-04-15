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

Changes from v3 → v5c (based on 38,977-trial LLM evaluation — Q4 2025):
    - Reordered search segments: outcomes first, eligibility last.
      This ensures high-signal outcome fields are evaluated before noisy
      eligibility text, reducing false positives from safety-screen matches.
    - Introduced NOISY_TARGETS: targets that commonly appear as eligibility
      safety thresholds. When a noisy target fires ONLY in eligibility and
      no other biomarker signal exists elsewhere in the trial, the trial is
      NOT called relevant. Includes original safety labs (Platelet, HBsAg,
      eGFR, HbA1c, HCV RNA, CRP, PSA, HBV DNA, HIV RNA) plus expanded set
      identified by field distribution analysis (Hemoglobin, FSH, CD4, TSH,
      Vitamin D, Testosterone, Progesterone, Estradiol, EGFR, PD-1, CTLA-4,
      TNF, GLP-1, VEGF, PARP, CDK4/6, ALK, ROS1, VEGFR, ESR1, MSI-H,
      ADA, IL-6, Insulin).
    - Added 83 new targets across IO, cell therapy, viral, tumor markers,
      hormones, bone markers, hematology, oncology/molecular, cytokines,
      lipids, and fibrosis categories.
    - Added NEW_TARGETS_3: TMB (expanded), MET, AR, HRD, CTC, RET, ATM,
      ER, UACR, ANA, Complement, BNP (already existed — patterns verified).
    - Net genuine improvement vs v3 baseline: +2,122
      (2,362 genuine FPs fixed, 988 genuine FNs fixed, 1,228 genuine TPs lost)
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
        True,
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
        True,
    ),

    # ── Immunolog ────────────────────────────────────────────────────────────
    (
        re.compile(r"\bimmunolog", re.I),
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
        [re.compile(r"\bimmunolog(?:ic|ical)\s+(?:disorder|disease|condition|dysfunction)\b", re.I),
         re.compile(r"\bhistory\s+of.*immunolog", re.I),
         re.compile(r"\bno\s+(?:known\s+)?immunolog", re.I),
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
        [re.compile(r"\bcognitive\s+assay\b", re.I),
         re.compile(r"\bneuropsychological\b", re.I),
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
        [re.compile(r"\bfiducial\s+marker\b", re.I),
         re.compile(r"\blesion\s+marker\b", re.I),
         re.compile(r"\bimaging\s+marker\b|\bradiograph", re.I),
         re.compile(r"\bRECIST\b|\bRANO\b|\bMacdonald\b", re.I),
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


# ── NOISY_TARGETS — corroboration required when firing only in eligibility ────
#
# These targets frequently appear as eligibility safety thresholds or patient
# selection criteria rather than as measured bioanalytical endpoints. When a
# noisy target fires ONLY in the eligibility field and no other biomarker signal
# exists anywhere else in the trial, the trial is NOT called relevant.
#
# Corroboration = any HIGH_CONFIDENCE pattern or any non-noisy BIOMARKER_TARGET
# firing in title, brief_summary, detailed_description, or outcome fields.

NOISY_TARGETS = {
    # Original safety labs (v4)
    "Platelet", "HBsAg", "HbA1c", "eGFR",
    "HCV RNA", "CRP", "PSA", "HBV DNA", "HIV RNA",
    # Clear eligibility screens ≥85% elig% (v5b)
    "Hemoglobin", "HBV RNA", "FSH", "CD4", "TSH", "Vitamin D",
    # Gray zone 72-82% elig% (v5b)
    "Testosterone", "Progesterone", "Estradiol",
    # Genomic/IHC patient selection criteria (v5c)
    "EGFR", "CTLA-4", "PD-1", "TNF", "GLP-1",
    "VEGF", "PARP", "CDK4/6", "ALK", "ROS1",
    "VEGFR", "ESR1", "MSI-H",
    # Low elig% targets — added to NOISY_TARGETS for net positive (v5c)
    "ADA", "IL-6", "Insulin",
}

# FLAT_PATTERNS_NON_NOISY is populated after BIOMARKER_TARGETS is defined (see below)


def has_any_signal_outside_eligibility(fields: dict) -> bool:
    """
    Returns True if any biomarker signal fires in non-eligibility fields.
    Uses pre-built fields dict with 'non_elig' key and keyword pre-filtering
    to eliminate most regex calls.
    """
    text     = fields.get("non_elig", "")
    text_low = text.lower()

    # HIGH_CONFIDENCE patterns
    for pat in HIGH_CONFIDENCE_PATTERNS:
        m = pat.search(text)
        if m and not is_negated(text, m):
            return True

    # Non-noisy targets only — with keyword pre-filter
    for target, kw, pat in FLAT_PATTERNS_NON_NOISY:
        if kw and kw not in text_low:
            continue
        m = pat.search(text)
        if m and not is_negated(text, m):
            return True

    # CONTEXT_UPGRADEABLE — needs per-field same_sentence check
    for field_key in ["title", "brief_summary", "detailed_desc", "primary", "secondary"]:
        field_text = fields.get(field_key, "")
        if not field_text:
            continue
        for entry in CONTEXT_UPGRADEABLE:
            term_pat        = entry[0]
            context_pats    = entry[1]
            exclusion_pats  = entry[2]
            require_context = entry[3] if len(entry) == 4 else False
            m = term_pat.search(field_text)
            if not m or is_negated(field_text, m):
                continue
            if any(ep.search(field_text) for ep in exclusion_pats):
                continue
            if any(same_sentence(field_text, term_pat, cp) for cp in context_pats):
                return True
            if not require_context:
                return True

    return False


def is_biomarker_relevant(trial: dict) -> tuple[bool, str, str]:
    """
    Returns (is_relevant, confidence, reason).
    confidence: 'high' | 'medium'
    reason: human-readable evidence string

    v5c architecture:
    - Segments searched in order: outcomes first, eligibility last
    - Noisy targets in eligibility require corroboration from other fields
    """
    # Build ordered segments — outcomes first, eligibility last
    primary_text   = " ".join(
        f"{o.get('measure', '')} {o.get('description', '')}"
        for o in trial.get("primary_outcomes", [])
    )
    secondary_text = " ".join(
        f"{o.get('measure', '')} {o.get('description', '')}"
        for o in trial.get("secondary_outcomes", [])
    )
    title_text       = trial.get("title", "") or ""
    summary_text     = trial.get("brief_summary", "") or ""
    detailed_text    = trial.get("detailed_description", "") or ""
    eligibility_text = trial.get("eligibility_criteria", "") or ""

    ordered = [
        ("primary_outcome",      primary_text),
        ("secondary_outcome",    secondary_text),
        ("title",                title_text),
        ("brief_summary",        summary_text),
        ("detailed_description", detailed_text),
        ("eligibility",          eligibility_text),
    ]

    # Pre-build non-eligibility concatenation for corroboration checks
    non_elig_text = " ".join(filter(None, [
        title_text, summary_text, detailed_text,
        primary_text, secondary_text,
    ]))
    fields_for_corroboration = {
        "non_elig":     non_elig_text,
        "title":        title_text,
        "brief_summary": summary_text,
        "detailed_desc": detailed_text,
        "primary":      primary_text,
        "secondary":    secondary_text,
    }

    # Pass 1 — HIGH_CONFIDENCE patterns (outcomes first, eligibility last)
    for source, text in ordered:
        if not text:
            continue
        for pat in HIGH_CONFIDENCE_PATTERNS:
            m = pat.search(text)
            if m and not is_negated(text, m):
                return True, "high", f'"{m.group()}" in {source}'

    # Pass 2 — Known targets (outcomes first, eligibility last)
    # Uses keyword pre-filter to skip regex when target keyword is absent.
    # Noisy targets in eligibility require corroboration from other fields.
    for source, text in ordered:
        if not text:
            continue
        text_low = text.lower()
        for target, kw, pat in FLAT_PATTERNS:
            if kw and kw not in text_low:
                continue  # keyword absent — skip regex entirely
            m = pat.search(text)
            if m and not is_negated(text, m):
                if source == "eligibility" and target in NOISY_TARGETS:
                    if not has_any_signal_outside_eligibility(
                        fields_for_corroboration
                    ):
                        continue  # eligibility-only noisy hit, no corroboration
                return (True, "high",
                        f'"{m.group()}" ({target}) in {source}')

    # Pass 3 — CONTEXT_UPGRADEABLE
    for source, text in ordered:
        if not text:
            continue
        for entry in CONTEXT_UPGRADEABLE:
            term_pat        = entry[0]
            context_pats    = entry[1]
            exclusion_pats  = entry[2]
            require_context = entry[3] if len(entry) == 4 else False

            m = term_pat.search(text)
            if not m:
                continue
            if is_negated(text, m):
                continue
            if any(ep.search(text) for ep in exclusion_pats):
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
                continue
            else:
                return (True, "medium",
                        f'"{m.group()}" in {source} (no context confirmed)')

    return False, "", ""


# ── Eligibility splitting ─────────────────────────────────────────────────────

def split_eligibility(text: str) -> tuple[str, str]:
    """Split eligibility text into inclusion and exclusion sections."""
    lower     = text.lower()
    split_idx = lower.find("exclusion criteria")
    if split_idx == -1:
        return text, ""
    return text[:split_idx], text[split_idx:]


# ── Step 2 — biomarker target dictionary ─────────────────────────────────────
#
# v5c additions marked with # [NEW]

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
                  re.compile(r"\bMET\s+exon\s*14\b", re.I),
                  re.compile(r"\bc[\s-]?MET\b", re.I)],
    "FGFR":      [re.compile(r"\bFGFR[\s-]?[1-4]?\b", re.I)],
    "NTRK":      [re.compile(r"\bNTRK[\s-]?[1-3]?\b", re.I)],
    "RET":       [re.compile(r"\bRET\b(?=.*(?:fusion|rearrange|mutation|inhibit|alteration))", re.I),
                  re.compile(r"\bRET\s+(?:fusion|proto-oncogene)\b", re.I)],

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
    "ER":        [re.compile(r"\bestrogen\s+receptor\b", re.I),                 # [NEW]
                  re.compile(r"\bER\b(?=.*(?:positive|negative|express|status|IHC|Allred|H[\s-]?score|percent))", re.I)],
    "AR":        [re.compile(r"\bandrogen\s+receptor\b", re.I),
                  re.compile(r"\bAR\b(?=.*(?:positive|express|signaling|pathway|splice\s+variant|amplif|mutation|activity|level))", re.I)],
    "HRD":       [re.compile(r"\bHRD\b|\bhomologous\s+recombination\s+deficien", re.I),  # [NEW standalone]
                  re.compile(r"\bHRR\b|\bhomologous\s+recombination\s+repair\b", re.I)],

    # ── Genomic instability/MRD ──────────────────────────────────────────────
    "TMB":       [re.compile(r"\btumor\s+mutational\s+burden\b", re.I),
                  re.compile(r"\btumour\s+mutational\s+burden\b", re.I),         # [NEW]
                  re.compile(r"\bTMB\b(?=.*(?:high|score|mutational|status))", re.I)],
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
                  re.compile(r"\bCTC\b(?=.*(?:count|detect|tumor|circulating|enumerat|isolat|measur))", re.I)],

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
    "ATM":       [re.compile(r"\bATM\b(?=.*(?:mutation|alterat|deficien|loss|delet|express|status))", re.I),  # [NEW]
                  re.compile(r"\bATM\s+(?:gene|protein|kinase)\b", re.I)],

    # ── Inflammatory/autoimmune ──────────────────────────────────────────────
    "CRP":       [re.compile(r"\bC[\s-]?reactive\s+protein\b", re.I),
                  re.compile(r"\bCRP\b(?=.*(?:level|mg|inflammation|serum|plasma|high[\s-]?sensitivity|hsCRP|hs[\s-]CRP))", re.I),
                  re.compile(r"\bhs[\s-]?CRP\b|\bhsCRP\b", re.I)],
    "ANA":       [re.compile(r"\bantinuclear\s+antibod", re.I),
                  re.compile(r"\bANA\b(?=.*(?:titer|titre|level|antibod|positive|lupus|measur))", re.I)],
    "anti-dsDNA":[re.compile(r"\banti[\s-]?ds[\s-]?DNA\b", re.I),
                  re.compile(r"\banti[\s-]?double\s+stranded\s+DNA\b", re.I)],
    "Complement":[re.compile(r"\bcomplement\s+(?:C3|C4|CH50|level|activat|measur)\b", re.I),
                  re.compile(r"\bcomplement\s+[C34]\d?\b", re.I),
                  re.compile(r"\bserum\s+complement\b", re.I),
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
    "Hemoglobin":[re.compile(r"\bhemoglobin\b(?=.*(?:g/dL|g/L|level|concentrat|response|change|baseline))", re.I),  # [NEW]
                  re.compile(r"\bHb\b(?=.*(?:g/dL|g/L|level|concentrat|response|change))", re.I)],

    # ── Renal biomarkers ─────────────────────────────────────────────────────
    "UACR":      [re.compile(r"\burine\s+albumin[\s-]?to[\s-]?creatinine\b", re.I),
                  re.compile(r"\bUACR\b", re.I),
                  re.compile(r"\burinary\s+albumin[\s-]?creatinine\s+ratio\b", re.I),
                  re.compile(r"\burinary\s+albumin[\s-]to[\s-]creatinine\s+ratio\b", re.I)],
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

    # ── IO targets / novel cell surface [NEW] ────────────────────────────────
    "B7-H3":     [re.compile(r"\bB7[\s-]?H3\b", re.I)],
    "GPC3":      [re.compile(r"\bGPC[\s-]?3\b|\bglypican[\s-]?3\b", re.I)],
    "CD70":      [re.compile(r"\bCD70\b", re.I)],
    "GD2":       [re.compile(r"\bGD[\s-]?2\b", re.I)],
    "CLDN18.2":  [re.compile(r"\bCLDN[\s-]?18\.2\b|\bclaudin[\s-]?18\.2\b", re.I)],
    "TROP2":     [re.compile(r"\bTROP[\s-]?2\b|\btrophoblast\s+cell\s+surface\s+antigen\s+2\b", re.I)],
    "HER3":      [re.compile(r"\bHER[\s-]?3\b|\bERBB3\b", re.I)],
    "MSLN":      [re.compile(r"\bMSLN\b|\bmesothelin\b", re.I)],
    "Nectin-4":  [re.compile(r"\bNectin[\s-]?4\b|\bNECTIN[\s-]?4\b", re.I)],

    # ── CAR-T / cell therapy [NEW] ───────────────────────────────────────────
    "CAR-T":     [re.compile(r"\bCAR[\s-]T\s+cell\b", re.I),
                  re.compile(r"\bchimeric\s+antigen\s+receptor\s+T", re.I),
                  re.compile(r"\bCAR[\s-]T\s+(?:persist|expand|concentrat|pharmacokinetic|engraft)", re.I),
                  re.compile(r"\bCAR\s+copies\b", re.I),
                  re.compile(r"\bTIL\b(?=.*(?:persist|expand|engraft|infus|measur|count|frequenc))", re.I)],

    # ── Viral [NEW] ──────────────────────────────────────────────────────────
    "EBV DNA":   [re.compile(r"\bEBV[\s-]?DNA\b|\bEpstein[\s-]?Barr.*DNA\b", re.I),
                  re.compile(r"\bEBV[\s-]?RNA\b|\bplasma\s+EBV\b", re.I)],
    "CMV DNA":   [re.compile(r"\bCMV[\s-]?DNA\b|\bCMV[\s-]?RNA\b", re.I),
                  re.compile(r"\bcytomegalovirus.*(?:DNA|RNA|viral\s+load)\b", re.I)],
    "HDV RNA":   [re.compile(r"\bHDV[\s-]?RNA\b|\bhepatitis\s+D.*RNA\b", re.I)],
    "RSV RNA":   [re.compile(r"\bRSV[\s-]?RNA\b|\brespiratory\s+syncytial.*RNA\b", re.I)],
    "HBV RNA":   [re.compile(r"\bHBV[\s-]?RNA\b|\bhepatitis\s+B.*RNA\b", re.I)],
    "Dengue RNA":[re.compile(r"\bdengue.*(?:RNA|viremia|viral\s+load)\b", re.I)],
    "Influenza RNA":[re.compile(r"\binfluenza.*(?:RNA|viral\s+load|titer|viremia)\b", re.I)],
    "SARS-CoV-2":[re.compile(r"\bSARS[\s-]?CoV[\s-]?2.*(?:RNA|viral\s+load|PCR)\b", re.I)],

    # ── Classical tumor markers [NEW] ────────────────────────────────────────
    "Ki-67":     [re.compile(r"\bKi[\s-]?67\b|\bKI67\b", re.I),
                  re.compile(r"\bproliferation\s+index\b(?=.*(?:Ki|tumor|biopsy))", re.I)],
    "CA19-9":    [re.compile(r"\bCA[\s-]?19[\s-]?9\b", re.I)],
    "CEA":       [re.compile(r"\bcarcinoembryonic\s+antigen\b", re.I),
                  re.compile(r"\bCEA\b(?=.*(?:level|serum|plasma|ng|response|progression|monitor))", re.I)],
    "AFP":       [re.compile(r"\balpha[\s-]?fetoprotein\b", re.I),
                  re.compile(r"\bAFP\b(?=.*(?:level|serum|ng|response|hepat|tumor\s+marker))", re.I)],
    "M-protein": [re.compile(r"\bM[\s-]?protein\b(?=.*(?:serum|urine|level|electrophoresis|myeloma|paraprotein))", re.I),
                  re.compile(r"\bmonoclonal\s+protein\b", re.I),
                  re.compile(r"\bserum\s+protein\s+electrophoresis\b", re.I),
                  re.compile(r"\bBence[\s-]?Jones\s+protein\b", re.I)],
    "Free light chain": [re.compile(r"\bfree\s+light\s+chain\b", re.I),
                  re.compile(r"\bsFLC\b|\bdFLC\b", re.I),
                  re.compile(r"\bserum\s+free\s+light\s+chain\b", re.I)],
    "CA-125":    [re.compile(r"\bCA[\s-]?125\b|\bCA125\b", re.I)],

    # ── Hormones / endocrine [NEW] ───────────────────────────────────────────
    "Testosterone": [re.compile(r"\b(?:serum|plasma|total|free)\s+testosterone\b", re.I),
                  re.compile(r"\btestosterone\s+(?:level|concentration|response|suppression)\b", re.I)],
    "FSH":       [re.compile(r"\bFSH\b(?=.*(?:level|serum|plasma|IU|mIU|response|ovarian))", re.I),
                  re.compile(r"\bfollicle[\s-]?stimulating\s+hormone\b", re.I)],
    "Estradiol": [re.compile(r"\bestradiol\b(?=.*(?:level|serum|plasma|pg|pmol|response))", re.I),
                  re.compile(r"\bserum\s+estradiol\b|\bplasma\s+estradiol\b", re.I)],
    "Cortisol":  [re.compile(r"\b(?:serum|plasma|urinary|salivary)\s+cortisol\b", re.I),
                  re.compile(r"\bcortisol\s+(?:level|response|suppression|concentration)\b", re.I),
                  re.compile(r"\bUFC\b(?=.*(?:cortisol|Cushing|adrenal))", re.I)],
    "IGF-1":     [re.compile(r"\bIGF[\s-]?1\b|\bIGF[\s-]?I\b|\binsulin[\s-]?like\s+growth\s+factor[\s-]?1\b", re.I)],
    "PTH":       [re.compile(r"\b(?:intact|serum|plasma)\s+PTH\b|\bparathyroid\s+hormone\b", re.I),
                  re.compile(r"\biPTH\b|\bPTH\b(?=.*(?:calcium|bone|parathyroid|level))", re.I)],
    "Vitamin D": [re.compile(r"\b25[\s-]?(?:OH|hydroxy)[\s-]?(?:D|vitamin\s+D)\b", re.I),
                  re.compile(r"\b1,25[\s-]?(?:OH|dihydroxy)[\s-]?(?:D|vitamin\s+D)\b", re.I),
                  re.compile(r"\bvitamin\s+D\s+(?:level|deficien|insufficien|concentrat|serum)\b", re.I)],
    "Progesterone": [re.compile(r"\bprogesterone\b(?=.*(?:level|serum|plasma|ng|measure|response))", re.I)],
    "TSH":       [re.compile(r"\bTSH\b(?=.*(?:level|serum|thyroid|mIU|measure|change|suppression))", re.I),
                  re.compile(r"\bthyroid[\s-]stimulating\s+hormone\b", re.I)],
    "Thyroglobulin": [re.compile(r"\bthyroglobulin\b(?=.*(?:level|serum|ng|measure|response|change))", re.I)],

    # ── Bone markers [NEW] ───────────────────────────────────────────────────
    "P1NP":      [re.compile(r"\bP1NP\b|\bprocollagen\s+type\s+1\s+N[\s-]?terminal\b", re.I),
                  re.compile(r"\bbone\s+formation\s+marker\b", re.I)],
    "CTx":       [re.compile(r"\bCTx\b|\bCTX[\s-]?1?\b|\bC[\s-]?terminal\s+telopeptide\b", re.I),
                  re.compile(r"\bbeta[\s-]?CTx\b|\bbone\s+resorption\s+marker\b", re.I)],
    "Osteocalcin": [re.compile(r"\bosteocalcin\b|\bOCN\b(?=.*(?:bone|osteocalcin|serum))", re.I)],
    "Bone turnover": [re.compile(r"\bbone\s+turnover\s+marker\b", re.I)],

    # ── GI/microbiome [NEW] ──────────────────────────────────────────────────
    "Fecal calprotectin": [re.compile(r"\bfecal\s+calprotectin\b|\bfaecal\s+calprotectin\b", re.I)],
    "Microbiome":[re.compile(r"\bgut\s+microbiom\b|\bfecal\s+microbiom\b|\bintestinal\s+microbiom\b", re.I),
                  re.compile(r"\bmicrobiota\s+(?:composition|diversity|analysis)\b", re.I)],
    "C-peptide": [re.compile(r"\bC[\s-]?peptide\b(?=.*(?:level|serum|plasma|measure|response|secretion))", re.I)],

    # ── Hematology / immune cells [NEW] ─────────────────────────────────────
    "CD8":       [re.compile(r"\bCD8\b(?=.*(?:\+|count|cell|T.cell|percent|level|infiltrat|subset|measure|assess))", re.I)],
    "CD4":       [re.compile(r"\bCD4\b(?=.*(?:\+|count|cell|T.cell|percent|level|subset|measure|assess))", re.I)],
    "NK cells":  [re.compile(r"\bNK\s+cell\b(?=.*(?:count|percent|activit|cytotox|subset|measure|assess|level))", re.I),
                  re.compile(r"\bnatural\s+killer\s+cell\b(?=.*(?:count|activit|subset|measure))", re.I)],
    "Regulatory T cells": [re.compile(r"\bregulatory\s+T\s+cells?\b|\bTreg\b|\bT[\s-]?reg\s+cell", re.I)],
    "MDSC":      [re.compile(r"\bMDSC\b|\bmyeloid[\s-]derived\s+suppressor\s+cell", re.I)],

    # ── Oncology / molecular [NEW] ───────────────────────────────────────────
    "TP53":      [re.compile(r"\bTP53\b|\bp53\b(?=.*(?:mutation|status|expression|protein|level|deletion|alteration))", re.I)],
    "MGMT":      [re.compile(r"\bMGMT\b(?=.*(?:methylat|status|promot|express|deficien))", re.I)],
    "KIT":       [re.compile(r"\bKIT\b(?=.*(?:mutation|D816V|express|amplif|exon|inhibit))", re.I),
                  re.compile(r"\bc[\s-]?KIT\b", re.I)],
    "BCR-ABL":   [re.compile(r"\bBCR[\s-]?ABL\b|\bBCR::ABL\b", re.I),
                  re.compile(r"\bBCR[\s-]?ABL1\b|\bPhiladelphia\s+chromosome\b", re.I)],
    "EGFRvIII":  [re.compile(r"\bEGFRvIII\b|\bEGFR\s+variant\s+III\b", re.I)],
    "PSMA":      [re.compile(r"\bPSMA\b|\bprostate[\s-]specific\s+membrane\s+antigen\b", re.I)],
    "NY-ESO-1":  [re.compile(r"\bNY[\s-]?ESO[\s-]?1\b", re.I)],
    "DLL3":      [re.compile(r"\bDLL[\s-]?3\b|\bdelta[\s-]like\s+(?:canonical\s+)?notch\s+ligand\s+3\b", re.I)],
    "NfL":       [re.compile(r"\bNfL\b|\bneurofilament\s+light\b|\bsNfL\b", re.I)],
    "PDGFRA":    [re.compile(r"\bPDGFRA\b|\bPDGFR[\s-]?alpha\b", re.I)],
    "TIGIT":     [re.compile(r"\bTIGIT\b", re.I)],
    "EZH2":      [re.compile(r"\bEZH2\b", re.I)],

    # ── Cytokines / immune [NEW] ─────────────────────────────────────────────
    "IL-2":      [re.compile(r"\bIL[\s-]?2\b(?=.*(?:level|concentrat|serum|plasma|measur|assess))", re.I),
                  re.compile(r"\binterleukin[\s-]?2\b", re.I)],
    "IL-18":     [re.compile(r"\bIL[\s-]?18\b|\binterleukin[\s-]?18\b", re.I)],
    "GM-CSF":    [re.compile(r"\bGM[\s-]?CSF\b(?=.*(?:level|serum|plasma|measur|concentrat))", re.I),
                  re.compile(r"\bgranulocyte[\s-]macrophage\s+colony[\s-]stimulating\b", re.I)],
    "IFN-gamma": [re.compile(r"\bIFN[\s-]?(?:gamma|γ|g)\b(?=.*(?:level|serum|plasma|measur|concentrat|release))", re.I),
                  re.compile(r"\binterferon[\s-]?gamma\b", re.I)],
    "MCP-1":     [re.compile(r"\bMCP[\s-]?1\b|\bCCL2\b|\bmonocyte\s+chemoattractant\s+protein", re.I)],
    "TGF-beta":  [re.compile(r"\bTGF[\s-]?(?:beta|β|b)[\s-]?1?\b|\btransforming\s+growth\s+factor[\s-]?beta\b", re.I)],
    "IL-1beta":  [re.compile(r"\bIL[\s-]?1[\s-]?(?:beta|β|b)\b|\binterleukin[\s-]?1[\s-]?beta\b", re.I)],

    # ── Lipids / metabolic [NEW] — pending Bo confirmation ───────────────────
    "LDL-C":     [re.compile(r"\bLDL[\s-]?C\b|\bLDL\s+cholesterol\b|\blow[\s-]density\s+lipoprotein\s+cholesterol\b", re.I)],
    "Triglycerides": [re.compile(r"\btriglyceride\b(?=.*(?:level|serum|plasma|fasting|mg|mmol|measure|change))", re.I),
                  re.compile(r"\bTG\b(?=.*(?:triglyceride|lipid|serum|plasma|fasting|level))", re.I)],
    "APOC3":     [re.compile(r"\bAPOC[\s-]?3\b|\bapolipoprotein\s+C[\s-]?III\b", re.I)],
    "Lipoprotein(a)": [re.compile(r"\blp[\s-]?\(a\)\b|\blipoprotein[\s-]?\(a\)\b|\bLp\(a\)\b", re.I)],
    "HDL-C":     [re.compile(r"\bHDL[\s-]?C\b|\bHDL\s+cholesterol\b|\bhigh[\s-]density\s+lipoprotein\s+cholesterol\b", re.I)],

    # ── Labs / other [NEW] ───────────────────────────────────────────────────
    "Ferritin":  [re.compile(r"\bferritin\b(?=.*(?:level|serum|plasma|ng|µg|measure|change|iron))", re.I)],
    "Ammonia":   [re.compile(r"\bammonia\b(?=.*(?:level|serum|plasma|blood|µmol|measure|change))", re.I),
                  re.compile(r"\bplasma\s+ammonia\b|\bserum\s+ammonia\b", re.I)],
    "Chimerism": [re.compile(r"\bchimerism\b(?=.*(?:donor|myeloid|lymphoid|engraft|measure|assess|percent))", re.I)],
    "ACPA":      [re.compile(r"\bACPA\b|\banti[\s-]CCP\b|\banti[\s-]citrullinated\s+protein\s+antibod", re.I)],
    "Tenofovir": [re.compile(r"\btenofovir\b(?=.*(?:plasma|concentrat|level|TFV|diphosphate|PK))", re.I),
                  re.compile(r"\bTFV[\s-]?DP\b|\btenofovir\s+diphosphate\b", re.I)],
    "LDH":       [re.compile(r"\bLDH\b(?=.*(?:level|serum|plasma|IU|measure|change|response|elevation))", re.I),
                  re.compile(r"\blactate\s+dehydrogenase\b(?=.*(?:level|serum|measure))", re.I)],
    "Uric acid": [re.compile(r"\buric\s+acid\b(?=.*(?:serum|plasma|level|mg|measure|change|gout))", re.I),
                  re.compile(r"\bserum\s+uric\s+acid\b|\bsUA\b(?=.*(?:gout|uric|level))", re.I)],

    # ── Fibrosis [NEW] ───────────────────────────────────────────────────────
    "Hyaluronic acid": [re.compile(r"\bhyaluronic\s+acid\b(?=.*(?:level|serum|fibrosis|liver))", re.I)],
    "TIMP-1":    [re.compile(r"\bTIMP[\s-]?1\b|\btissue\s+inhibitor\s+of\s+metalloproteinase[\s-]?1\b", re.I)],
    "PRO-C3":    [re.compile(r"\bPRO[\s-]?C3\b|\bprocollagen\s+type\s+3\b|\bP3NP\b", re.I)],

    # ── NEW_TARGETS_3 ────────────────────────────────────────────────────────
    "TMB_v2":    [],   # covered above under TMB — no separate entry needed
}

# Remove placeholder
del BIOMARKER_TARGETS["TMB_v2"]


# ── Keyword pre-filter ────────────────────────────────────────────────────────
#
# One lowercase literal keyword per target. If the keyword is absent from a
# field's lowercased text, ALL patterns for that target are skipped — no regex
# is called. This eliminates ~95% of wasted regex calls.
#
# Rules:
#   - Keyword MUST appear in any text where the target's patterns could match
#   - Empty string "" = no keyword, regex always runs (safe fallback)
#   - When unsure, use "" — correctness > speed

TARGET_KEYWORDS: dict[str, str] = {
    # Only keep keywords that are guaranteed present for ALL patterns of that target.
    # Any target with alternative full-name patterns uses "" (regex always runs).
    # Default for any target not listed is "" (safe).

    # Unambiguous CD markers — these only appear as "CDxx" never as full names
    "CD19":         "cd19",
    "CD20":         "cd20",
    "CD22":         "cd22",
    "CD38":         "cd38",
    "CD79b":        "cd79",
    "CD3":          "cd3",
    "CD33":         "cd33",
    "CD47":         "cd47",
    "CD30":         "cd30",
    "CD123":        "cd123",
    "CD34":         "cd34",
    "CD8":          "cd8",
    "CD4":          "cd4",
    "CD70":         "cd70",
    # Unambiguous gene/target names with no full-name alternatives in patterns
    "BCMA":         "bcma",
    "FLT3":         "flt3",
    "IDH1":         "idh1",
    "IDH2":         "idh2",
    "JAK2":         "jak2",
    "PIK3CA":       "pik3ca",
    "FGFR":         "fgfr",
    "NTRK":         "ntrk",
    "ctDNA":        "ctdna",
    "CTC":          "ctc",
    "TMB":          "tmb",
    "MRD":          "mrd",
    "BRCA":         "brca",
    "mTOR":         "mtor",
    "PARP":         "parp",
    "PSMA":         "psma",
    "TIGIT":        "tigit",
    "EZH2":         "ezh2",
    "PDGFRA":       "pdgfra",
    "NfL":          "nfl",
    "DLL3":         "dll3",
    "MGMT":         "mgmt",
    "TP53":         "tp53",
    "MDSC":         "mdsc",
    "GPC3":         "gpc3",
    "GD2":          "gd2",
    "TROP2":        "trop2",
    "CLDN18.2":     "cldn18",
    "NY-ESO-1":     "ny-eso",
    "B7-H3":        "b7-h3",
    "MSLN":         "msln",
    "Nectin-4":     "nectin",
    "HER3":         "her3",
    "EGFRvIII":     "egfrviii",
    "BCR-ABL":      "bcr-abl",
    "ACPA":         "acpa",
    "Chimerism":    "chimerism",
    "Tenofovir":    "tenofovir",
    "UACR":         "uacr",
    "DSA":          "dsa",
    "APOC3":        "apoc3",
    "P1NP":         "p1np",
    "Osteocalcin":  "osteocalcin",
    "Bone turnover":"bone turnover",
    "Fecal calprotectin": "calprotectin",
    "Microbiome":   "microbiom",
    "Dengue RNA":   "dengue",
    "Influenza RNA":"influenza",
    "SARS-CoV-2":   "sars",
    "EBV DNA":      "ebv",
    "CMV DNA":      "cmv",
    "HDV RNA":      "hdv",
    "RSV RNA":      "rsv",
    "Regulatory T cells": "treg",
    "NK cells":     "nk cell",
    "Thyroglobulin":"thyroglobulin",
    "Progesterone": "progesterone",
    "Testosterone": "testosterone",
    "Estradiol":    "estradiol",
    "Cortisol":     "cortisol",
    "Ammonia":      "ammonia",
    "Ferritin":     "ferritin",
    "Hyaluronic acid": "hyaluronic",
    "TIMP-1":       "timp-1",
    "PRO-C3":       "pro-c3",
    "LDH":          "ldh",
    "Uric acid":    "uric acid",
    "Triglycerides":"triglyceride",
    "Lipoprotein(a)":"lipoprotein",
    "Hemoglobin":   "hemoglobin",
    "HbF":          "hbf",
    "Amyloid-b":    "amyloid",
    "HBV DNA":      "hbv",
    "HBV RNA":      "hbv",
    "MCP-1":        "mcp-1",
    "IL-18":        "il-18",
    "IL-2":         "il-2",
    "TTR":          "ttr",
    "NRAS":         "nras",
    "HLA":          "hla",
    "C-peptide":    "c-peptide",
    "CTx":          "ctx",
}

# Pre-built flat list: (target, keyword, pattern)
# keyword is "" for targets where pre-filtering is unsafe/unclear
FLAT_PATTERNS: list = []
for _target, _patterns in BIOMARKER_TARGETS.items():
    _kw = TARGET_KEYWORDS.get(_target, "")
    for _pat in _patterns:
        FLAT_PATTERNS.append((_target, _kw, _pat))

# Same but excluding NOISY_TARGETS — for corroboration checks
FLAT_PATTERNS_NON_NOISY: list = [
    (_target, _kw, _pat)
    for _target, _kw, _pat in FLAT_PATTERNS
    if _target not in NOISY_TARGETS
]


# ── Target metadata ───────────────────────────────────────────────────────────

TARGET_METADATA: dict[str, dict] = {
    # Confirmed Biosciences
    "ADA":        {"type": "immunogenicity",    "bs_relevant": True,  "safety_lab": False},
    "IL-6":       {"type": "cytokine",          "bs_relevant": True,  "safety_lab": False},
    "IL-17":      {"type": "cytokine",          "bs_relevant": True,  "safety_lab": False},
    "TNF":        {"type": "cytokine",          "bs_relevant": True,  "safety_lab": False},
    "VEGF":       {"type": "cytokine",          "bs_relevant": True,  "safety_lab": False},
    "ctDNA":      {"type": "liquid_biopsy",     "bs_relevant": True,  "safety_lab": False},
    "CTC":        {"type": "liquid_biopsy",     "bs_relevant": True,  "safety_lab": False},
    "MRD":        {"type": "functional",        "bs_relevant": True,  "safety_lab": False},
    "GLP-1":      {"type": "hormone",           "bs_relevant": True,  "safety_lab": False},
    "Glucagon":   {"type": "hormone",           "bs_relevant": True,  "safety_lab": False},
    "Insulin":    {"type": "hormone",           "bs_relevant": True,  "safety_lab": False},

    # Confirmed NOT Biosciences
    "HBsAg":      {"type": "viral_marker",      "bs_relevant": False, "safety_lab": True},
    "HCV RNA":    {"type": "viral_marker",      "bs_relevant": False, "safety_lab": True},
    "HIV RNA":    {"type": "viral_marker",      "bs_relevant": False, "safety_lab": True},
    "HBV DNA":    {"type": "viral_marker",      "bs_relevant": False, "safety_lab": False},
    "HER2 CDx":   {"type": "companion_dx",      "bs_relevant": False, "safety_lab": False},
    "PD-L1 CDx":  {"type": "companion_dx",      "bs_relevant": False, "safety_lab": False},

    # Needs Bo confirmation — cell surface / checkpoint
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

    # Genes
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
    "ER":         {"type": "receptor",          "bs_relevant": None,  "safety_lab": False},
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
    "HRD":        {"type": "functional",        "bs_relevant": None,  "safety_lab": False},
    "ATM":        {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "TP53":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "MGMT":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "KIT":        {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "BCR-ABL":    {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "EGFRvIII":   {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "PDGFRA":     {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "TIGIT":      {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "EZH2":       {"type": "gene",              "bs_relevant": None,  "safety_lab": False},

    # Inflammatory/autoimmune
    "CRP":        {"type": "cytokine",          "bs_relevant": None,  "safety_lab": False},
    "ANA":        {"type": "autoantibody",      "bs_relevant": None,  "safety_lab": False},
    "anti-dsDNA": {"type": "autoantibody",      "bs_relevant": None,  "safety_lab": False},
    "Complement": {"type": "protein",           "bs_relevant": None,  "safety_lab": False},
    "IgE":        {"type": "immunoglobulin",    "bs_relevant": None,  "safety_lab": False},
    "Eosinophil": {"type": "cell",              "bs_relevant": None,  "safety_lab": False},

    # Cardiac
    "NT-proBNP":  {"type": "cardiac_biomarker", "bs_relevant": None,  "safety_lab": False},
    "BNP":        {"type": "cardiac_biomarker", "bs_relevant": None,  "safety_lab": False},
    "Troponin":   {"type": "cardiac_biomarker", "bs_relevant": None,  "safety_lab": False},
    "TTR":        {"type": "protein",           "bs_relevant": None,  "safety_lab": False},

    # Metabolic/endocrine
    "HbA1c":      {"type": "metabolic",         "bs_relevant": None,  "safety_lab": False},
    "PSA":        {"type": "tumor_marker",      "bs_relevant": None,  "safety_lab": False},
    "GLP-1":      {"type": "hormone",           "bs_relevant": True,  "safety_lab": False},
    "Testosterone":{"type": "hormone",          "bs_relevant": None,  "safety_lab": False},
    "FSH":        {"type": "hormone",           "bs_relevant": None,  "safety_lab": False},
    "Estradiol":  {"type": "hormone",           "bs_relevant": None,  "safety_lab": False},
    "Cortisol":   {"type": "hormone",           "bs_relevant": None,  "safety_lab": False},
    "IGF-1":      {"type": "hormone",           "bs_relevant": None,  "safety_lab": False},
    "PTH":        {"type": "hormone",           "bs_relevant": None,  "safety_lab": False},
    "Vitamin D":  {"type": "metabolic",         "bs_relevant": None,  "safety_lab": False},
    "Progesterone":{"type": "hormone",          "bs_relevant": None,  "safety_lab": False},
    "TSH":        {"type": "hormone",           "bs_relevant": None,  "safety_lab": False},
    "Thyroglobulin":{"type": "tumor_marker",    "bs_relevant": None,  "safety_lab": False},
    "Hemoglobin": {"type": "hematology",        "bs_relevant": None,  "safety_lab": True},

    # Hematology
    "HbF":        {"type": "hematology",        "bs_relevant": None,  "safety_lab": False},
    "Platelet":   {"type": "hematology",        "bs_relevant": None,  "safety_lab": True},
    "CD8":        {"type": "cell",              "bs_relevant": None,  "safety_lab": False},
    "CD4":        {"type": "cell",              "bs_relevant": None,  "safety_lab": False},
    "NK cells":   {"type": "cell",              "bs_relevant": None,  "safety_lab": False},
    "Regulatory T cells": {"type": "cell",      "bs_relevant": None,  "safety_lab": False},
    "MDSC":       {"type": "cell",              "bs_relevant": None,  "safety_lab": False},

    # Renal
    "UACR":       {"type": "renal_biomarker",   "bs_relevant": None,  "safety_lab": False},
    "eGFR":       {"type": "renal_biomarker",   "bs_relevant": None,  "safety_lab": True},

    # Transplant
    "DSA":        {"type": "autoantibody",      "bs_relevant": None,  "safety_lab": False},
    "HLA":        {"type": "genetic",           "bs_relevant": None,  "safety_lab": False},

    # Neurodegeneration
    "p-tau":      {"type": "neurodegeneration", "bs_relevant": None,  "safety_lab": False},
    "Amyloid-b":  {"type": "neurodegeneration", "bs_relevant": None,  "safety_lab": False},
    "NfL":        {"type": "neurodegeneration", "bs_relevant": None,  "safety_lab": False},

    # IO / novel targets
    "B7-H3":      {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "GPC3":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "CD70":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "GD2":        {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "CLDN18.2":   {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "TROP2":      {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "HER3":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "MSLN":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "Nectin-4":   {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "PSMA":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "NY-ESO-1":   {"type": "tumor_antigen",     "bs_relevant": None,  "safety_lab": False},
    "DLL3":       {"type": "cell_surface",      "bs_relevant": None,  "safety_lab": False},
    "CA-125":     {"type": "tumor_marker",      "bs_relevant": None,  "safety_lab": False},

    # CAR-T
    "CAR-T":      {"type": "cell_therapy",      "bs_relevant": None,  "safety_lab": False},

    # Viral
    "EBV DNA":    {"type": "viral_marker",      "bs_relevant": None,  "safety_lab": False},
    "CMV DNA":    {"type": "viral_marker",      "bs_relevant": None,  "safety_lab": False},
    "HDV RNA":    {"type": "viral_marker",      "bs_relevant": None,  "safety_lab": False},
    "RSV RNA":    {"type": "viral_marker",      "bs_relevant": None,  "safety_lab": False},
    "HBV RNA":    {"type": "viral_marker",      "bs_relevant": None,  "safety_lab": False},
    "Dengue RNA": {"type": "viral_marker",      "bs_relevant": None,  "safety_lab": False},
    "Influenza RNA":{"type": "viral_marker",    "bs_relevant": None,  "safety_lab": False},
    "SARS-CoV-2": {"type": "viral_marker",      "bs_relevant": None,  "safety_lab": False},

    # Tumor markers
    "Ki-67":      {"type": "tumor_marker",      "bs_relevant": None,  "safety_lab": False},
    "CA19-9":     {"type": "tumor_marker",      "bs_relevant": None,  "safety_lab": False},
    "CEA":        {"type": "tumor_marker",      "bs_relevant": None,  "safety_lab": False},
    "AFP":        {"type": "tumor_marker",      "bs_relevant": None,  "safety_lab": False},
    "M-protein":  {"type": "tumor_marker",      "bs_relevant": None,  "safety_lab": False},
    "Free light chain": {"type": "tumor_marker","bs_relevant": None,  "safety_lab": False},

    # Bone
    "P1NP":       {"type": "bone_marker",       "bs_relevant": None,  "safety_lab": False},
    "CTx":        {"type": "bone_marker",       "bs_relevant": None,  "safety_lab": False},
    "Osteocalcin":{"type": "bone_marker",       "bs_relevant": None,  "safety_lab": False},
    "Bone turnover":{"type": "bone_marker",     "bs_relevant": None,  "safety_lab": False},

    # GI
    "Fecal calprotectin":{"type": "gi_marker",  "bs_relevant": None,  "safety_lab": False},
    "Microbiome": {"type": "microbiome",        "bs_relevant": None,  "safety_lab": False},
    "C-peptide":  {"type": "metabolic",         "bs_relevant": None,  "safety_lab": False},

    # Cytokines
    "IL-2":       {"type": "cytokine",          "bs_relevant": None,  "safety_lab": False},
    "IL-18":      {"type": "cytokine",          "bs_relevant": None,  "safety_lab": False},
    "GM-CSF":     {"type": "cytokine",          "bs_relevant": None,  "safety_lab": False},
    "IFN-gamma":  {"type": "cytokine",          "bs_relevant": None,  "safety_lab": False},
    "MCP-1":      {"type": "cytokine",          "bs_relevant": None,  "safety_lab": False},
    "TGF-beta":   {"type": "cytokine",          "bs_relevant": None,  "safety_lab": False},
    "IL-1beta":   {"type": "cytokine",          "bs_relevant": None,  "safety_lab": False},

    # Lipids
    "LDL-C":      {"type": "lipid",             "bs_relevant": None,  "safety_lab": False},
    "Triglycerides":{"type": "lipid",           "bs_relevant": None,  "safety_lab": False},
    "APOC3":      {"type": "lipid",             "bs_relevant": None,  "safety_lab": False},
    "Lipoprotein(a)":{"type": "lipid",          "bs_relevant": None,  "safety_lab": False},
    "HDL-C":      {"type": "lipid",             "bs_relevant": None,  "safety_lab": False},

    # Labs
    "Ferritin":   {"type": "hematology",        "bs_relevant": None,  "safety_lab": False},
    "Ammonia":    {"type": "metabolic",         "bs_relevant": None,  "safety_lab": False},
    "Chimerism":  {"type": "hematology",        "bs_relevant": None,  "safety_lab": False},
    "ACPA":       {"type": "autoantibody",      "bs_relevant": None,  "safety_lab": False},
    "Tenofovir":  {"type": "drug_level",        "bs_relevant": None,  "safety_lab": False},
    "LDH":        {"type": "metabolic",         "bs_relevant": None,  "safety_lab": False},
    "Uric acid":  {"type": "metabolic",         "bs_relevant": None,  "safety_lab": False},

    # Fibrosis
    "Hyaluronic acid":{"type": "fibrosis_marker","bs_relevant": None, "safety_lab": False},
    "TIMP-1":     {"type": "fibrosis_marker",   "bs_relevant": None,  "safety_lab": False},
    "PRO-C3":     {"type": "fibrosis_marker",   "bs_relevant": None,  "safety_lab": False},

    # NEW_TARGETS_3
    "HRD":        {"type": "functional",        "bs_relevant": None,  "safety_lab": False},
    "MET":        {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "AR":         {"type": "receptor",          "bs_relevant": None,  "safety_lab": False},
    "CTC":        {"type": "liquid_biopsy",     "bs_relevant": True,  "safety_lab": False},
    "RET":        {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "ATM":        {"type": "gene",              "bs_relevant": None,  "safety_lab": False},
    "ER":         {"type": "receptor",          "bs_relevant": None,  "safety_lab": False},
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
    results = []
    found   = set()

    eligibility          = trial.get("eligibility_criteria", "") or ""
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
    for outcome_type, key in [("primary_endpoint",     "primary_outcomes"),
                               ("secondary_endpoint",   "secondary_outcomes"),
                               ("brief_summary",        None),
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
