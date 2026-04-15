"""
Lightweight TA re-assignment for unassigned drug trials ONLY.

Instead of reclassifying all 87K trials (which OOMs in WSL),
this loads the master JSON, patches the ~650 unassigned drug trials
using the updated ta_policy keywords, and saves a new master.

No trial reconstruction, no modality re-run, no multiprocessing.
Memory: ~400MB (just the JSON dict).
"""
import json
import sys
import time
from pathlib import Path

# ── Import updated keyword lists ──
from policy.ta_policy import (
    ONCOLOGY_KW, PSYCHIATRY_KW, INFECTIOUS_KW, IMMUNO_KW,
    NEURO_KW, CARDIO_KW, METABOLIC_KW, RARE_KW, MSK_KW,
    GI_KW, UROLOGY_KW, OPHTHALMOLOGY_KW, DENTAL_KW,
    DERMATOLOGY_KW, HEMATOLOGY_KW, RESPIRATORY_KW,
    TA_PRIORITY_ORDER, TA_UNASSIGNED, TA_NON_DISEASE,
    select_primary_ta,
)
from analytics.summary_v2 import has_enabling_signal
from storage.models_v2 import ClinicalTrialSignalV2

TA_KW_MAP = {
    "Oncology": ONCOLOGY_KW,
    "Infectious Disease": INFECTIOUS_KW,
    "Immunology / Inflammation": IMMUNO_KW,
    "Neurology / CNS": NEURO_KW,
    "Cardiovascular": CARDIO_KW,
    "Metabolic / Endocrine": METABOLIC_KW,
    "Rare / Genetic": RARE_KW,
    "Musculoskeletal": MSK_KW,
    "Psychiatry": PSYCHIATRY_KW,
    "Gastrointestinal / Hepatic": GI_KW,
    "Respiratory": RESPIRATORY_KW,
    "Ophthalmology": OPHTHALMOLOGY_KW,
    "Urology": UROLOGY_KW,
    "Hematology": HEMATOLOGY_KW,
    "Dermatology": DERMATOLOGY_KW,
    "Dental / Oral Health": DENTAL_KW,
}


def text_match_ta(title: str, conditions: list[str]) -> str | None:
    """Match therapeutic area from title + conditions text using keywords."""
    text = ((title or "") + " " + " ".join(conditions or [])).lower()
    hits = []
    for ta, kws in TA_KW_MAP.items():
        for kw in kws:
            if kw.lower() in text:
                hits.append(ta)
                break
    if not hits:
        return None
    return select_primary_ta(hits)


def main():
    snapshot_path = Path(
        sys.argv[1] if len(sys.argv) > 1
        else "storage/snapshots/clinical_trials_v2/active_universe/master_DB_2025_Q4.json"
    )
    # Derive output from input filename so it works for any master DB,
    # not just Q4 2025.  e.g. master_DB_2026_Q1.json -> master_DB_2026_Q1_ta_patched.json
    output_path = snapshot_path.with_name(
        snapshot_path.stem + "_ta_patched" + snapshot_path.suffix
    )

    print(f"Loading {snapshot_path} ...")
    t0 = time.time()
    with open(snapshot_path, "r") as f:
        data = json.load(f)
    trials = data["trials"]
    print(f"  Loaded {len(trials)} trials in {time.time()-t0:.1f}s")

    # Find unassigned drug trials
    unassigned_idx = [
        i for i, t in enumerate(trials)
        if t.get("therapeutic_area") == "Unassigned drug study"
    ]
    print(f"  Unassigned drug trials: {len(unassigned_idx)}")

    # Patch each one
    patched = 0
    patched_by_ta = {}
    still_unassigned = 0

    for i in unassigned_idx:
        t = trials[i]
        new_ta = text_match_ta(t.get("title"), t.get("conditions"))
        if new_ta:
            trials[i]["therapeutic_area"] = new_ta
            trials[i]["study_intent"] = "disease"
            patched_by_ta[new_ta] = patched_by_ta.get(new_ta, 0) + 1
            patched += 1
        else:
            still_unassigned += 1

    print(f"\n=== Results ===")
    print(f"  Patched: {patched}")
    print(f"  Still unassigned: {still_unassigned}")
    print(f"\n  Patched by TA:")
    for ta, n in sorted(patched_by_ta.items(), key=lambda x: -x[1]):
        print(f"    {ta:35} | {n}")

    # Save
    print(f"\n  Saving to {output_path} ...")
    t0 = time.time()
    with open(output_path, "w") as f:
        json.dump(data, f)
    print(f"  Saved in {time.time()-t0:.1f}s")
    print(f"  File size: {output_path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
