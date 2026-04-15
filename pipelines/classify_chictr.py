# pipelines/classify_chictr.py
"""
Classify ChiCTR trials using ALEXIS TA and modality classifiers.
Bypasses MeSH-dependent paths (not available for ChiCTR).

Modality is only attempted for trials whose intervention text contains
INN-style drug name patterns — avoids flooding output with spurious
"other_drug" labels for procedure/device/acupuncture studies.

Input:  storage/chictr_interventional_all.csv
Output: storage/chictr_classified.parquet
"""

import re
import sys
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.models_v2 import ClinicalTrialSignalV2
from classifiers.therapeutic_area import assign_therapeutic_area
from classifiers.trial_modality_v2 import assign_trial_modality_v2


# ------------------------------------------------------------------
# INN suffix pattern — gates modality classification
# ------------------------------------------------------------------
INN_PATTERN = re.compile(
    r'\b\w*('
    r'mab|nib|tinib|zumab|lumab|ciclib|rafenib|lizumab|parib'
    r'|vastatin|sartan|prazole|lukast|fenib|setib|glutide'
    r'|tide|pelimab|ertinib|cizumab|ilimab|olimab|alizumab'
    r'|becepta|kinase inhibitor|checkpoint inhibitor'
    r')\b',
    re.IGNORECASE,
)

COMPOUND_CODE_PATTERN = re.compile(
    r'\b[A-Z]{1,5}[-_]?\d{3,5}\b|\b[A-Z]{2,4}\d{3,5}\b',
    re.IGNORECASE,
)


def has_drug_signal(title: str, interventions: str) -> bool:
    combined = f"{title or ''} {interventions or ''}"
    return bool(INN_PATTERN.search(combined) or COMPOUND_CODE_PATTERN.search(combined))


# ------------------------------------------------------------------
# Row → ClinicalTrialSignalV2 stub
# ------------------------------------------------------------------

def chictr_row_to_trial(row: pd.Series) -> ClinicalTrialSignalV2:
    trial = ClinicalTrialSignalV2(
        nct_id=row.get("trial_id", "") or "",
        title=row.get("brief_title", "") or "",
    )

    trial.study_type    = "INTERVENTIONAL"
    trial.is_drug_trial = True

    raw_cond = row.get("conditions_raw", "")
    trial.conditions = [raw_cond] if isinstance(raw_cond, str) and raw_cond else []

    raw_iv = row.get("interventions_raw", "")
    trial.interventions_text = [raw_iv] if isinstance(raw_iv, str) and raw_iv else []

    # No structured types or MeSH available for ChiCTR
    trial.interventions_all           = []
    trial.intervention_meshes         = []
    trial.intervention_mesh_ancestors = []
    trial.condition_meshes            = []
    trial.condition_mesh_ancestors    = []

    # Pre-cache text blobs used by classifiers
    trial._cached_title_conditions = " ".join(
        [trial.title] + trial.conditions
    ).lower()
    trial._cached_title_interventions = " ".join(
        trial.interventions_text + [trial.title]
    ).lower()

    if not hasattr(trial, "info_flags") or trial.info_flags is None:
        trial.info_flags = []

    return trial


# ------------------------------------------------------------------
# Main classifier loop
# ------------------------------------------------------------------

def classify_chictr(input_path: str, output_path: str) -> pd.DataFrame:
    df = pd.read_csv(input_path)
    print(f"Loaded {len(df):,} ChiCTR interventional trials")

    df["_has_drug_signal"] = df.apply(
        lambda r: has_drug_signal(
            r.get("brief_title", ""),
            r.get("interventions_raw", ""),
        ),
        axis=1,
    )
    n_drug_signal = df["_has_drug_signal"].sum()
    print(f"Trials with INN/compound drug signal: {n_drug_signal:,} / {len(df):,}")

    results = []
    for i, (_, row) in enumerate(df.iterrows()):
        trial = chictr_row_to_trial(row)

        # TA — always run
        ta = assign_therapeutic_area(trial)
        trial.therapeutic_area = ta

        # Modality — only for trials with a recognizable drug name
        modality        = None
        modality_source = None
        if row["_has_drug_signal"]:
            try:
                modality = assign_trial_modality_v2(trial)
                modality_source = getattr(trial, "modality_source", "text")
                # Suppress uninformative base-only results
                if modality == "other_drug" and modality_source == "intervention_type":
                    modality        = None
                    modality_source = None
            except Exception:
                modality = None

        results.append({
            "trial_id":          row.get("trial_id"),
            "brief_title":       row.get("brief_title"),
            "conditions_raw":    row.get("conditions_raw"),
            "interventions_raw": row.get("interventions_raw"),
            "lead_sponsor_name": row.get("lead_sponsor_name"),
            "phase":             row.get("phase"),
            "overall_status":    row.get("overall_status"),
            "registration_date": row.get("registration_date"),
            "source_url":        row.get("source_url"),
            "therapeutic_area":  ta,
            "modality":          modality,
            "modality_source":   modality_source,
            "has_drug_signal":   row["_has_drug_signal"],
            "info_flags":        str(getattr(trial, "info_flags", [])),
        })

        if (i + 1) % 500 == 0:
            print(f"  {i+1:,}/{len(df):,} classified...")

    out_df = pd.DataFrame(results)

    print(f"\nTA breakdown:")
    print(out_df["therapeutic_area"].value_counts().to_string())

    print(f"\nModality breakdown (drug-signal trials only):")
    print(out_df[out_df["has_drug_signal"]]["modality"].value_counts().to_string())

    print(f"\nModality source:")
    print(out_df["modality_source"].value_counts().to_string())

    out_df.to_parquet(output_path, index=False)
    print(f"\nSaved {len(out_df):,} classified trials → {output_path}")
    return out_df


if __name__ == "__main__":
    input_path  = sys.argv[1] if len(sys.argv) > 1 else "storage/chictr_interventional_all.csv"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "storage/chictr_classified.parquet"
    classify_chictr(input_path, output_path)
