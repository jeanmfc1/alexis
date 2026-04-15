# pipelines/classify_chictr_to_snapshot.py
"""
Classify ChiCTR trials and produce a full ALEXIS-compatible snapshot JSON.

Reads the live checkpoint JSONL (updated by scrape_chictr_details.py), runs
the intl drug classifier for is_drug_trial + modality, runs the ALEXIS text
TA classifier, maps all fields to the ALEXIS snapshot trial schema, and saves
a snapshot JSON that can be loaded by any ALEXIS analytics or dashboard.

Input:   storage/chictr_details_checkpoint.jsonl   (or --input)
Model:   classifiers/intl_drug_classifier_v2.pkl   (or --model)
Output:  storage/snapshots/clinical_trials_v2/chictr/YYYY-MM-DD_chictr_v1.json

Usage:
    python pipelines/classify_chictr_to_snapshot.py
    python pipelines/classify_chictr_to_snapshot.py --input storage/chictr_details.parquet
    python pipelines/classify_chictr_to_snapshot.py --min-conf 0.8
"""

from __future__ import annotations

import argparse
import json
import pickle
import re
import time
import warnings
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# Suppress sklearn version mismatch warnings (model trained on Windows sklearn,
# running on Linux sklearn of same version — different binary, same behaviour)
warnings.filterwarnings("ignore", message=".*InconsistentVersionWarning.*")
try:
    from sklearn.exceptions import InconsistentVersionWarning
    warnings.filterwarnings("ignore", category=InconsistentVersionWarning)
except ImportError:
    pass

import numpy as np
import pandas as pd

from storage.models_v2 import ClinicalTrialSignalV2, InterventionV2, MeshTermV2
from analytics.summary_v2 import (
    ta_modality_counts_true_drugs,
    drug_trial_counts,
    info_flag_counts_true_drugs,
    drug_modality_summary,
    drug_therapeutic_area_summary,
    drug_info_overview,
    study_type_summary_all_trials,
    drug_modality_provenance_summary,
    drug_ta_provenance_summary,
    drug_study_intent_summary,
    non_disease_drug_subtype_summary,
    ta_by_phase,
    modality_by_phase,
    ta_by_sponsor_class,
    multi_ta_rate_by_phase,
    drug_mesh_missing_condition_summary,
    non_disease_study_category_summary,
)

# ── Constants ─────────────────────────────────────────────────────────────────

REGISTRY   = "ChiCTR"
SOURCE_TAG = "chictr"

# ── Phase normalization ───────────────────────────────────────────────────────

_PHASE_MAP = {
    # Standard text forms
    "phase 1":          "PHASE1",
    "phase1":           "PHASE1",
    "phase i":          "PHASE1",
    "phase 2":          "PHASE2",
    "phase2":           "PHASE2",
    "phase ii":         "PHASE2",
    "phase iib":        "PHASE2",
    "phase 3":          "PHASE3",
    "phase3":           "PHASE3",
    "phase iii":        "PHASE3",
    "phase iiib":       "PHASE3",
    "phase 4":          "PHASE4",
    "phase4":           "PHASE4",
    "phase iv":         "PHASE4",
    "phase 1/phase 2":  "PHASE1_PHASE2",
    "phase 1/2":        "PHASE1_PHASE2",
    "phase i/ii":       "PHASE1_PHASE2",
    "phase 2/phase 3":  "PHASE2_PHASE3",
    "phase 2/3":        "PHASE2_PHASE3",
    "phase ii/iii":     "PHASE2_PHASE3",
    "early phase 1":    "EARLY_PHASE1",
    # ChiCTR numeric forms (field stores number only)
    "0":                "EARLY_PHASE1",
    "1":                "PHASE1",
    "2":                "PHASE2",
    "3":                "PHASE3",
    "4":                "PHASE4",
    "1-2":              "PHASE1_PHASE2",
    "2-3":              "PHASE2_PHASE3",
    # ChiCTR non-phase values
    "n/a":                                    "NA",
    "na":                                     "NA",
    "not applicable":                         "NA",
    "new treatment measure clinical study":   "NA",
    "diagnostic new technique clincal study": "NA",
    "retrospective study":                    "NA",
}

# Regex fallback for phase mentions in title/summary text
_PHASE_TEXT_PATTERNS = [
    (re.compile(r'phase\s*1\s*/\s*2|phase\s*i\s*/\s*ii\b', re.I), "PHASE1_PHASE2"),
    (re.compile(r'phase\s*2\s*/\s*3|phase\s*ii\s*/\s*iii\b', re.I), "PHASE2_PHASE3"),
    (re.compile(r'phase\s*iib?\b', re.I),  "PHASE2"),
    (re.compile(r'phase\s*iiib?\b', re.I), "PHASE3"),
    (re.compile(r'phase\s*iv\b|phase\s*4\b', re.I), "PHASE4"),
    (re.compile(r'phase\s*iii\b|phase\s*3\b', re.I), "PHASE3"),
    (re.compile(r'phase\s*ii\b|phase\s*2\b', re.I),  "PHASE2"),
    (re.compile(r'phase\s*i\b|phase\s*1\b', re.I),   "PHASE1"),
    (re.compile(r'\bsad\b|\bmad\b|single ascending dose|first.in.human|first in human', re.I), "EARLY_PHASE1"),
]

def normalize_phase(raw: Optional[str], fallback_text: Optional[str] = None) -> str:
    if not raw:
        phase = "NA"
    else:
        key = raw.strip().lower()
        phase = _PHASE_MAP.get(key, "NA")

    # If still NA, try regex on fallback text (title + objectives)
    if phase == "NA" and fallback_text:
        for pat, mapped in _PHASE_TEXT_PATTERNS:
            if pat.search(fallback_text):
                return mapped

    return phase


# ── Study type normalization ──────────────────────────────────────────────────

def normalize_study_type(raw: Optional[str]) -> str:
    if not raw:
        return "OTHER"
    r = raw.strip().upper()
    if "INTERVENTIONAL" in r:
        return "INTERVENTIONAL"
    if "OBSERVATIONAL" in r:
        return "OBSERVATIONAL"
    return "OTHER"


# ── Sponsor class inference ───────────────────────────────────────────────────

_GOVT_KEYWORDS   = re.compile(r"national|ministry|government|federal|municipal|bureau|agency|council|commission", re.I)
_ACAD_KEYWORDS   = re.compile(r"university|universit|college|hospital|institute|clinic|medical center|school of|faculty", re.I)
_SELF_KEYWORDS   = re.compile(r"self.?fund|own fund|raised fund|自筹", re.I)

def infer_sponsor_class(funding_source: Optional[str], sponsor: Optional[str]) -> str:
    blob = " ".join(filter(None, [funding_source, sponsor]))
    if not blob:
        return "OTHER"
    if _SELF_KEYWORDS.search(blob):
        return "OTHER"
    if _GOVT_KEYWORDS.search(blob):
        return "OTHER_GOV"
    if _ACAD_KEYWORDS.search(blob):
        return "OTHER"
    # If sponsor looks like a company (no academic/govt keywords) → INDUSTRY
    return "INDUSTRY"


# ── Intervention text parsing ─────────────────────────────────────────────────

_CONTROL_RE = re.compile(r"^(control|placebo|none|no intervention|blank|standard|soc|usual care)", re.I)

def parse_interventions_text(interventions_raw: Optional[str], medicine_detail: Optional[str]) -> list[str]:
    """
    Parse ChiCTR interventions_raw into a list of intervention name strings.
    Format: "Group name: intervention text | Group name: intervention text"
    """
    results = []

    if interventions_raw:
        for arm in interventions_raw.split("|"):
            arm = arm.strip()
            if not arm:
                continue
            # Take the part after the colon (the intervention, not the group name)
            if ":" in arm:
                iv_text = arm.split(":", 1)[1].strip()
            else:
                iv_text = arm
            if iv_text and not _CONTROL_RE.match(iv_text) and iv_text.lower() != "none":
                results.append(iv_text)

    if medicine_detail and medicine_detail.strip():
        results.append(medicine_detail.strip())

    return results if results else []


def parse_conditions(target_disease: Optional[str]) -> list[str]:
    """Split target_disease into a list of condition strings."""
    if not target_disease:
        return []
    # Split on semicolons or commas if semicolons absent
    if ";" in target_disease:
        parts = target_disease.split(";")
    elif "," in target_disease:
        parts = target_disease.split(",")
    else:
        parts = [target_disease]
    return [p.strip() for p in parts if p.strip()]


# ── Post-processing overrides (mirrors classify_intl_drug.py logic) ───────────

GENE_THERAPY_RE = re.compile(
    r'\baav\d*\b|\blentiviral\b|\bretroviral\b|\bgene editing\b|\bcrispr\b|'
    r'\bcas9\b|\bin vivo gene\b|\bex vivo gene\b|\bviral vector\b|'
    r'\badeno.associated\b|\bonasemnogene\b|\bzolgensma\b|'
    r'\bgene transfer\b|\bgene correction\b|\bgene therap',
    re.IGNORECASE,
)
RADIOPHARMA_IV_RE = re.compile(
    r'\b\d+[cCfF]\b|\b68ga\b|\b18f\b|\b177lu\b|\b89zr\b|\b64cu\b|'
    r'\blutetium\b|\bgallium\b|\bflorbetapir\b|\bflutemetamol\b|\bpsma\b',
    re.IGNORECASE,
)
BIOLOGIC_MIN_CONF = 0.75

def apply_overrides(pred: str, conf: float, text: str, iv_text: str):
    override = None
    flagged  = False
    if pred in ("biologic", "non_drug") and GENE_THERAPY_RE.search(text):
        override = "gene_therapy"
    elif pred == "radiopharmaceutical" and not RADIOPHARMA_IV_RE.search(iv_text):
        override = "non_drug"
    elif pred == "biologic" and conf < BIOLOGIC_MIN_CONF:
        flagged = True
    return override or pred, override, flagged


# ── Build text blob for classifier ───────────────────────────────────────────

def build_clf_text(row: pd.Series) -> str:
    parts = [
        row.get("title_detail") or row.get("title_list") or "",
        row.get("objectives") or "",
        row.get("interventions_raw") or "",
        row.get("target_disease") or "",
        row.get("medicine_detail") or "",
    ]
    return " ".join(p for p in parts if p).strip()

def build_iv_text(row: pd.Series) -> str:
    return " ".join(filter(None, [
        row.get("interventions_raw") or "",
        row.get("medicine_detail") or "",
    ]))


# ── Map a ChiCTR row → ClinicalTrialSignalV2 ─────────────────────────────────

def row_to_trial(row: pd.Series, modality: str, conf: float,
                 override: Optional[str], flagged: bool,
                 ta_pred: Optional[str] = None) -> ClinicalTrialSignalV2:
    """
    Build a ClinicalTrialSignalV2 from a ChiCTR row.

    Strategy:
    - is_drug_trial + modality: intl drug classifier (authoritative)
    - TA + study_intent:        intl TA classifier (ta_pred)
      The TA classifier was trained on the same classes as ALEXIS including
      "Non-disease drug study" and "Unassigned drug study", so no MeSH or
      has_enabling_signal logic is needed.
    - study_category:           assign_non_disease_study_category (for non_disease)
    """
    is_drug    = modality != "non_drug"
    iv_texts   = parse_interventions_text(row.get("interventions_raw"), row.get("medicine_detail"))
    conditions = parse_conditions(row.get("target_disease"))

    # ── TA + study_intent from TA classifier ─────────────────────────────────
    NON_DISEASE_TA = "Non-disease drug study"
    UNASSIGNED_TA  = "Unassigned drug study"

    if not is_drug or ta_pred is None:
        therapeutic_area           = None
        therapeutic_areas_detected = []
        study_intent               = None
        study_category             = None
        study_category_evidence    = []
    elif ta_pred == NON_DISEASE_TA:
        therapeutic_area           = NON_DISEASE_TA
        therapeutic_areas_detected = [NON_DISEASE_TA]
        study_intent               = "non_disease"
        # Run non_disease subcategory assignment
        from analytics.summary_v2 import assign_non_disease_study_category
        _title = row.get("title_detail") or row.get("title_list") or ""
        _ivs   = " ".join(iv_texts)
        _cached = f"{_ivs} {_title}".lower()

        _conditions = conditions  # capture in local scope for _FakeTrial

        class _FakeTrial:
            interventions_text          = iv_texts
            title                       = _title
            conditions                  = _conditions
            _cached_title_interventions = _cached

        cat, ev = assign_non_disease_study_category(_FakeTrial())
        study_category          = cat
        study_category_evidence = ev
    elif ta_pred == UNASSIGNED_TA:
        therapeutic_area           = UNASSIGNED_TA
        therapeutic_areas_detected = [UNASSIGNED_TA]
        study_intent               = None
        study_category             = None
        study_category_evidence    = []
    else:
        therapeutic_area           = ta_pred
        therapeutic_areas_detected = [ta_pred]
        study_intent               = "disease"
        study_category             = None
        study_category_evidence    = []

    trial = ClinicalTrialSignalV2(
        nct_id                      = row.get("regno") or f"ChiCTR_{row.get('proj_id')}",
        title                       = row.get("title_detail") or row.get("title_list"),
        study_type                  = normalize_study_type(row.get("study_type") or row.get("study_type_detail")),
        phase                       = normalize_phase(
                            row.get("phase"),
                            fallback_text=(row.get("title_detail") or "") + " " + (row.get("objectives") or ""),
                        ),
        sponsor_class               = infer_sponsor_class(row.get("funding_source"), row.get("primary_sponsor") or row.get("sponsor")),
        conditions                  = conditions,
        first_posted_date           = row.get("registration_date") or row.get("reg_date"),
        last_update_posted_date     = None,
        interventions               = [],
        interventions_all           = [],
        interventions_text          = iv_texts,
        arm_group_map               = {},
        intervention_meshes         = [],
        intervention_mesh_ancestors = [],
        condition_meshes            = [],
        condition_mesh_ancestors    = [],
        therapeutic_area            = therapeutic_area,
        is_drug_trial               = is_drug,
        modality                    = modality if is_drug else None,
        info_flags                  = [],
    )

    trial.therapeutic_areas_detected = therapeutic_areas_detected
    trial.study_intent               = study_intent
    trial.study_category             = study_category
    trial.study_category_evidence    = study_category_evidence
    trial.mesh_missing_condition     = True
    trial.modality_source            = "intl_classifier"

    # ── Metadata flags ────────────────────────────────────────────────────────
    trial.info_flags.append("chictr_no_mesh")
    if flagged:
        trial.info_flags.append("low_confidence_biologic")
    if override:
        trial.info_flags.append(f"override:{override}")

    return trial


# ── Serialize trial to snapshot dict ─────────────────────────────────────────

def trial_to_dict(trial: ClinicalTrialSignalV2, row: pd.Series) -> dict:
    return {
        # Core identity
        "nct_id":                    trial.nct_id,
        "title":                     trial.title,
        "brief_summary":             row.get("objectives"),
        "detailed_description":      None,
        "registry":                  REGISTRY,
        "source_url":                row.get("source_url"),

        # Study metadata
        "study_type":                trial.study_type,
        "phase":                     trial.phase,
        "sponsor_class":             trial.sponsor_class,
        "sponsor_name":              row.get("primary_sponsor") or row.get("sponsor"),
        "conditions":                trial.conditions,
        "overall_status":            None,
        "enrollment":                None,
        "enrollment_type":           None,
        "why_stopped":               None,

        # Dates
        "start_date":                row.get("study_start"),
        "completion_date":           row.get("study_end"),
        "primary_completion_date":   None,
        "first_posted_date":         trial.first_posted_date,
        "last_update_posted_date":   None,

        # Outcomes (not available in ChiCTR scrape)
        "primary_outcomes":          [],
        "secondary_outcomes":        [],

        # Facilities (not available in ChiCTR scrape)
        "facilities":                [],
        "facility_count":            0,

        # Interventions
        "interventions":             [],
        "interventions_text":        trial.interventions_text,
        "interventions_all":         [],
        "arm_group_map":             {},

        # MeSH (not available for ChiCTR)
        "intervention_meshes":       [],
        "intervention_mesh_ancestors": [],
        "condition_meshes":          [],
        "condition_mesh_ancestors":  [],

        # ALEXIS classification
        "therapeutic_area":          trial.therapeutic_area,
        "therapeutic_areas_detected": trial.therapeutic_areas_detected,
        "is_drug_trial":             trial.is_drug_trial,
        "modality":                  trial.modality,
        "info_flags":                trial.info_flags,
        "study_intent":              trial.study_intent,
        "study_category":            trial.study_category,
        "study_category_evidence":   trial.study_category_evidence,
        "mesh_missing_condition":    trial.mesh_missing_condition,

        # Unused snapshot fields (kept for schema compatibility)
        "update_type":               None,
        "update_categories":         [],
        "linked_from":               None,
        "outcome":                   None,
    }


# ── Load input ────────────────────────────────────────────────────────────────

def load_input(path: Path) -> pd.DataFrame:
    if path.suffix == ".jsonl":
        records = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
        df = pd.DataFrame(records).drop_duplicates(subset=["proj_id"])
        print(f"  Loaded {len(df):,} unique trials from checkpoint JSONL")
        return df
    elif path.suffix == ".parquet":
        df = pd.read_parquet(path)
        print(f"  Loaded {len(df):,} trials from parquet")
        return df
    else:
        raise ValueError(f"Unsupported format: {path.suffix}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",    default="storage/chictr_details_checkpoint.jsonl")
    parser.add_argument("--model",    default="classifiers/intl_drug_classifier_v2.pkl")
    parser.add_argument("--out-dir",  default="storage/snapshots/clinical_trials_v2/chictr")
    parser.add_argument("--min-conf", type=float, default=0.7)
    parser.add_argument("--ta-model",  default="classifiers/intl_ta_classifier.pkl",
                        help="Path to intl_ta_classifier.pkl")
    args = parser.parse_args()

    input_path  = Path(args.input)
    model_path  = Path(args.model)
    out_dir     = Path(args.out_dir)
    today       = date.today().isoformat()

    W = 60
    print("=" * W)
    print("  ALEXIS — ChiCTR → Snapshot Pipeline")
    print("=" * W)
    print(f"  Input:    {input_path}")
    print(f"  Model:    {model_path}")
    print(f"  TA Model: {Path(args.ta_model)}")
    print(f"  Out dir:  {out_dir}")
    print(f"  Started:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")
    if not model_path.exists():
        raise FileNotFoundError(
            f"Model not found: {model_path}\n"
            f"Copy intl_drug_classifier_v2.pkl to classifiers/ first."
        )

    # ── Load data ─────────────────────────────────────────────────
    print("─" * W)
    print("STEP 1 — Loading data")
    print("─" * W)
    df = load_input(input_path)

    # ── Classify ──────────────────────────────────────────────────
    print()
    print("─" * W)
    print("STEP 2 — Running intl drug classifier")
    print("─" * W)

    print(f"  Loading model from {model_path} ...")
    with open(model_path, "rb") as f:
        clf = pickle.load(f)
    vectorizer = clf["vectorizer"]
    model      = clf["model"]
    classes    = clf["classes"]

    ta_model_path = Path(args.ta_model)
    ta_model = ta_classes = None
    if ta_model_path.exists():
        print(f"  Loading TA model from {ta_model_path} ...")
        with open(ta_model_path, "rb") as f:
            ta_clf = pickle.load(f)
        ta_model   = ta_clf["model"]
        ta_classes = ta_clf["classes"]
        print(f"  TA classes ({len(ta_classes)}): {ta_classes}")
    else:
        print(f"  ⚠ TA model not found at {ta_model_path} — TA will be unassigned")

    texts    = df.apply(build_clf_text, axis=1).fillna("").tolist()
    iv_texts = df.apply(build_iv_text,  axis=1).fillna("").tolist()

    print(f"  Vectorizing {len(texts):,} trials ...")
    t = time.time()
    X = vectorizer.transform(texts)
    print(f"  Done in {time.time()-t:.1f}s")

    probs    = model.predict_proba(X)
    pred_idx = np.argmax(probs, axis=1)
    preds    = [classes[i] for i in pred_idx]
    confs    = probs[np.arange(len(texts)), pred_idx].tolist()

    final_preds, overrides, flagged_list = [], [], []
    for text, iv_text, pred, conf in zip(texts, iv_texts, preds, confs):
        fp, ov, fl = apply_overrides(pred, conf, text, iv_text)
        final_preds.append(fp)
        overrides.append(ov)
        flagged_list.append(fl)

    # ── Run TA classifier on drug trials ─────────────────────────
    ta_preds = [None] * len(df)
    if ta_model is not None:
        drug_mask = [p != "non_drug" for p in final_preds]
        drug_indices = [i for i, m in enumerate(drug_mask) if m]
        if drug_indices:
            drug_texts = [texts[i] for i in drug_indices]
            print(f"  Running TA classifier on {len(drug_indices):,} drug trials ...")
            t = time.time()
            X_drug = vectorizer.transform(drug_texts)
            ta_probs   = ta_model.predict_proba(X_drug)
            ta_pred_idx = np.argmax(ta_probs, axis=1)
            for j, idx in enumerate(drug_indices):
                ta_preds[idx] = ta_classes[ta_pred_idx[j]]
            print(f"  TA classification done in {time.time()-t:.1f}s")

    # ── Build trial objects + TA classification ───────────────────
    print()
    print("─" * W)
    print("STEP 3 — Building trials + TA classification")
    print("─" * W)

    trials = []
    trial_dicts = []
    for i, (_, row) in enumerate(df.iterrows()):
        trial = row_to_trial(row, final_preds[i], confs[i], overrides[i], flagged_list[i], ta_preds[i])
        trials.append(trial)
        trial_dicts.append(trial_to_dict(trial, row))
        if (i + 1) % 500 == 0 or (i + 1) == len(df):
            pct = (i + 1) / len(df)
            bar = "█" * int(20 * pct) + "░" * (20 - int(20 * pct))
            print(f"  [{bar}] {i+1:,}/{len(df):,}", end="\r", flush=True)

    print()

    # ── Summaries ─────────────────────────────────────────────────
    print()
    print("─" * W)
    print("STEP 4 — Computing summaries")
    print("─" * W)

    drug_trials = [t for t in trials if t.is_drug_trial]
    non_drug    = len(trials) - len(drug_trials)

    summary = {
        "ta_modality_counts_true_drugs":  ta_modality_counts_true_drugs(trials),
        "drug_trial_counts":              drug_trial_counts(trials),
        "info_flag_counts_true_drugs":    info_flag_counts_true_drugs(trials),
        "drug_info_overview":             drug_info_overview(trials),
        # intervention_type_summary omitted — ChiCTR has no structured intervention types
        "study_type_summary":             study_type_summary_all_trials(trials),
        "drug_modality_provenance":       drug_modality_provenance_summary(trials),
        "drug_ta_provenance":             drug_ta_provenance_summary(trials),
        "drug_study_intent":              drug_study_intent_summary(trials),
        "non_disease_drug_subtypes":      non_disease_drug_subtype_summary(trials),
        "ta_by_phase":                    ta_by_phase(trials),
        "modality_by_phase":              modality_by_phase(trials),
        "ta_by_sponsor_class":            ta_by_sponsor_class(trials),
        "multi_ta_rate_by_phase":         multi_ta_rate_by_phase(trials),
        "drug_mesh_missing_condition":    drug_mesh_missing_condition_summary(trials),
        "non_disease_study_categories":   non_disease_study_category_summary(trials),
        "registry":                       REGISTRY,
        "classifier_version":             "intl_drug_classifier_v2",
    }

    # ── Console output matching reclassify_snapshot ───────────────
    print("\nTA × Modality counts (TRUE DRUGS ONLY):")
    for ta, mods in summary["ta_modality_counts_true_drugs"].items():
        for modality, count in mods.items():
            print(f"  {ta:20} | {modality:22} | {count}")

    print("\nModality INFO summary (TRUE DRUGS ONLY):")
    for flag, count in summary["info_flag_counts_true_drugs"].items():
        print(f"  {flag}: {count}")

    print("\nDrug trial overview:")
    for k, v in summary["drug_info_overview"].items():
        print(f"  {k}: {v}")

    print("\nDrug trials by modality:")
    for k, v in sorted(drug_modality_summary(trials).items()):
        print(f"  {k:25} | {v}")

    print("\nDrug trials by therapeutic area:")
    for k, v in sorted(drug_therapeutic_area_summary(trials).items()):
        print(f"  {k:25} | {v}")

    print("\nStudy type summary (ALL trials):")
    for st, count in summary["study_type_summary"].items():
        print(f"  {st}: {count}")

    print("\nDrug modality provenance (drug trials):")
    for k, v in summary["drug_modality_provenance"].items():
        print(f"  {k:20} | {v}")

    print("\nTherapeutic area provenance (drug trials):")
    for k, v in summary["drug_ta_provenance"].items():
        print(f"  {k:20} | {v}")

    print("\nDrug study intent:")
    for k, v in summary["drug_study_intent"].items():
        print(f"  {k:15} | {v}")

    print("\nDrug mesh-missing condition (DATA COMPLETENESS — always True for ChiCTR):")
    for k, v in summary["drug_mesh_missing_condition"].items():
        print(f"  {k:25} | {v}")

    print("\nNon-disease drug study subtypes:")
    for k, v in sorted(summary["non_disease_drug_subtypes"].items()):
        print(f"  {k:25} | {v}")

    print("\nTA × Phase:")
    for ta, phases in summary["ta_by_phase"].items():
        for phase, count in phases.items():
            print(f"  {ta:20} | {str(phase or "None"):10} | {count}")

    print("\nModality × Phase:")
    for mod, phases in summary["modality_by_phase"].items():
        for phase, count in phases.items():
            print(f"  {mod:20} | {str(phase or "None"):10} | {count}")

    print("\nTA × Sponsor class:")
    for ta, sponsors in summary["ta_by_sponsor_class"].items():
        for sponsor, count in sponsors.items():
            print(f"  {ta:20} | {sponsor:15} | {count}")

    print("\nMulti-TA rate by phase:")
    for phase, rate in summary["multi_ta_rate_by_phase"].items():
        print(f"  {str(phase or "None"):10} | {rate:.2%}")

    print("\nNon-disease study categories:")
    for k, v in sorted(summary["non_disease_study_categories"].items()):
        print(f"  {k:25} | {v}")

    # ── Save snapshot ─────────────────────────────────────────────
    print()
    print("─" * W)
    print("STEP 5 — Saving snapshot")
    print("─" * W)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{today}_chictr_v1.json"

    snapshot = {
        "metadata": {
            "source":          REGISTRY,
            "registry":        REGISTRY,
            "as_of":           today,
            "window_start":    None,
            "window_end":      today,
            "total_trials":    len(trials),
            "drug_trials":     len(drug_trials),
            "generated_at":    datetime.now().isoformat(),
            "classifier":      "intl_drug_classifier_v2",
            "input_file":      str(input_path),
        },
        "trials":   trial_dicts,
        "summary":  summary,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, default=str)

    size_mb = out_path.stat().st_size / 1_000_000
    print(f"  Saved → {out_path}  ({size_mb:.1f} MB, {len(trials):,} trials)")
    print(f"  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("  Load in ALEXIS with:")
    print(f'    snapshot = json.load(open("{out_path}"))')
    print(f'    trials   = snapshot["trials"]')


if __name__ == "__main__":
    main()
