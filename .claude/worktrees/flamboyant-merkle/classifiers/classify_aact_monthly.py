"""
Process and classify AACT monthly archives using ALEXIS classifiers.

This script:
1. Finds extracted AACT tables in storage/snapshots/clinical_trials_v2/aact/
2. Normalizes them to ClinicalTrialSignalV2 format
3. Applies ALEXIS drug/modality/TA classifiers (same as weekly_pulse)
4. Saves classified snapshots in standard ALEXIS format
5. Runs continuously, processing new extractions as they appear

Usage:
    python classify_aact_monthly.py
    
    Press Ctrl+C to stop and see final summary
"""

from pathlib import Path
from datetime import date
import time
from tqdm import tqdm

# Import from collectors package
from collectors.clinicaltrials.normalize_aact_tables import normalize_aact_tables

# Import utilities
from utils.parallel_processor import process_trials_parallel

# Import policy
from policy.ta_policy import TA_NON_DISEASE, select_primary_ta, TA_UNASSIGNED

# Import classifiers
from classifiers.therapeutic_area import (
    assign_therapeutic_area,
    detect_therapeutic_area_evidence,
)
from classifiers.drug_non_drug_v2 import is_drug_trial_v2
from classifiers.trial_modality_v2 import assign_trial_modality_v2

# Import storage
from storage.models_v2 import ClinicalTrialSignalV2
from storage.snapshots_io_v2 import save_trial_snapshot_v2, SnapshotMetadataV2

# Import analytics
from analytics.summary_v2 import (
    ta_modality_counts_true_drugs,
    drug_trial_counts,
    info_flag_counts_true_drugs,
    drug_modality_summary,
    drug_therapeutic_area_summary,
    drug_info_overview,
    intervention_type_summary_all_trials,
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
    has_enabling_signal,
    assign_non_disease_study_category,
    non_disease_study_category_summary,
)


# Directories
AACT_EXTRACTED_DIR = Path("storage/snapshots/clinical_trials_v2/aact")
OUTPUT_BASE_DIR = Path("storage/snapshots/clinical_trials_v2")

# Track already processed months
PROCESSED_MONTHS_FILE = OUTPUT_BASE_DIR / "aact_classified" / ".processed_months.txt"


def is_already_classified(month_dir_name: str) -> bool:
    """
    Check if this month has already been classified.
    
    Args:
        month_dir_name: Directory name like '2017_Jul'
    
    Returns:
        True if already processed
    """
    if not PROCESSED_MONTHS_FILE.exists():
        return False
    
    with open(PROCESSED_MONTHS_FILE, 'r') as f:
        processed = set(line.strip() for line in f)
    
    return month_dir_name in processed


def mark_as_classified(month_dir_name: str) -> None:
    """Mark a month as successfully classified."""
    PROCESSED_MONTHS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with open(PROCESSED_MONTHS_FILE, 'a') as f:
        f.write(f"{month_dir_name}\n")


def classify_single_trial(trial: ClinicalTrialSignalV2) -> ClinicalTrialSignalV2:
    """
    Classify a single trial - IDENTICAL to weekly_pulse_clinical_v2.py
    """
    # Pre-cache text
    trial._cached_title_interventions = " ".join(
        (trial.interventions_text or []) + [trial.title or ""]
    ).lower()
    trial._cached_title_conditions = " ".join(
        [trial.title or ""] + (trial.conditions or [])
    ).lower()

    # Drug status FIRST
    trial.is_drug_trial = is_drug_trial_v2(trial)

    # Skip expensive processing for non-drug trials
    if not trial.is_drug_trial:
        trial.therapeutic_area = None
        trial.therapeutic_areas_detected = []
        trial.study_intent = None
        trial.study_category = None
        trial.study_category_evidence = []
        trial.mesh_missing_condition = False
        trial.modality = None
        return trial

    # Therapeutic Area
    ta_evidence = detect_therapeutic_area_evidence(trial)
    trial.therapeutic_areas_detected = sorted(ta_evidence.keys())
    primary_ta = select_primary_ta(trial.therapeutic_areas_detected)

    if primary_ta:
        trial.therapeutic_area = primary_ta
    else:
        text_ta = assign_therapeutic_area(trial)
        if text_ta and text_ta != "Other":
            trial.therapeutic_area = text_ta
        elif trial.is_drug_trial:
            if has_enabling_signal(trial):
                trial.therapeutic_area = TA_NON_DISEASE
            else:
                trial.therapeutic_area = TA_UNASSIGNED
        else:
            trial.therapeutic_area = None

    # Study intent
    if not trial.is_drug_trial:
        trial.study_intent = None
    elif trial.therapeutic_area == TA_NON_DISEASE:
        trial.study_intent = "non_disease"
    elif trial.therapeutic_area == TA_UNASSIGNED:
        trial.study_intent = None
    else:
        trial.study_intent = "disease"
    
    # Non-disease study category
    if trial.is_drug_trial and trial.study_intent == "non_disease":
        cat, ev = assign_non_disease_study_category(trial)
        trial.study_category = cat
        trial.study_category_evidence = ev
    else:
        trial.study_category = None
        trial.study_category_evidence = []

    # Data completeness flag
    trial.mesh_missing_condition = bool(
        trial.is_drug_trial and not trial.condition_meshes
    )

    # Modality
    if trial.is_drug_trial:
        trial.modality = assign_trial_modality_v2(trial)
    else:
        trial.modality = None
    
    return trial


def parse_aact_dirname(dirname: str) -> tuple:
    """
    Parse directory name like '2017_Jul' into (year, month).
    Returns: (year: int, month: str) or None
    """
    try:
        parts = dirname.split('_')
        if len(parts) != 2:
            return None
        year = int(parts[0])
        month = parts[1]
        return (year, month)
    except:
        return None


def process_aact_month(month_dir: Path) -> Path:
    """
    Process one AACT monthly archive directory.
    
    Args:
        month_dir: Path to directory containing 6 extracted tables
    
    Returns:
        Path to saved classified snapshot
    """
    print(f"\n{'='*70}")
    print(f"Processing: {month_dir.name}")
    print(f"{'='*70}")
    
    # Parse year and month
    parsed = parse_aact_dirname(month_dir.name)
    if not parsed:
        print(f"  ✗ Could not parse directory name: {month_dir.name}")
        return None
    
    year, month = parsed
    
    # Verify all required tables exist
    required_tables = {
        'studies.txt',
        'sponsors.txt',
        'interventions.txt',
        'conditions.txt',
        'browse_conditions.txt',
        'browse_interventions.txt'
    }
    
    missing = []
    for table in required_tables:
        if not (month_dir / table).exists():
            missing.append(table)
    
    if missing:
        print(f"  ✗ Missing tables: {missing}")
        return None
    
    # Normalize AACT tables to ClinicalTrialSignalV2
    print(f"  Normalizing AACT tables...")
    trials = normalize_aact_tables(
        studies_path=month_dir / "studies.txt",
        sponsors_path=month_dir / "sponsors.txt",
        interventions_path=month_dir / "interventions.txt",
        conditions_path=month_dir / "conditions.txt",
        browse_conditions_path=month_dir / "browse_conditions.txt",
        browse_interventions_path=month_dir / "browse_interventions.txt",
    )
    
    print(f"  Normalized {len(trials):,} trials")
    
    # Classify in parallel
    print(f"  Classifying trials...")
    start_time = time.time()
    
    trials = process_trials_parallel(
        trials=trials,
        classifier_function=classify_single_trial,
        num_workers=None
    )
    
    elapsed = time.time() - start_time
    trials_per_sec = len(trials) / elapsed if elapsed > 0 else 0
    print(f"  ✓ Classification completed in {elapsed:.1f}s ({trials_per_sec:.1f} trials/sec)")
    
    # Compute summaries
    print(f"  Computing summaries...")
    summary = {
        "ta_modality_counts_true_drugs": ta_modality_counts_true_drugs(trials),
        "drug_trial_counts": drug_trial_counts(trials),
        "info_flag_counts_true_drugs": info_flag_counts_true_drugs(trials),
        "drug_info_overview": drug_info_overview(trials),
        "intervention_type_summary": intervention_type_summary_all_trials(trials),
        "study_type_summary": study_type_summary_all_trials(trials),
        "drug_modality_provenance": drug_modality_provenance_summary(trials),
        "drug_ta_provenance": drug_ta_provenance_summary(trials),
        "drug_study_intent": drug_study_intent_summary(trials),
        "non_disease_drug_subtypes": non_disease_drug_subtype_summary(trials),
        "ta_by_phase": ta_by_phase(trials),
        "modality_by_phase": modality_by_phase(trials),
        "ta_by_sponsor_class": ta_by_sponsor_class(trials),
        "multi_ta_rate_by_phase": multi_ta_rate_by_phase(trials),
        "drug_mesh_missing_condition": drug_mesh_missing_condition_summary(trials),
        "non_disease_study_categories": non_disease_study_category_summary(trials),
    }
    
    # Build metadata
    # Use first day of month as snapshot date
    snapshot_date = date(year, month_to_number(month), 1)
    
    metadata = SnapshotMetadataV2(
        source="AACT",
        window_basis="MonthlyArchive",
        as_of=snapshot_date,
        window_start=snapshot_date.isoformat(),
        window_end=snapshot_date.isoformat(),
        page_size=None,
        max_studies=None,
    )
    
    # Save snapshot
    output_path = save_trial_snapshot_v2(
        base_dir=str(OUTPUT_BASE_DIR),
        basis_folder="aact_classified",
        metadata=metadata,
        trials=trials,
        summary=summary,
    )
    
    print(f"  ✓ Saved: {output_path}")
    
    # Print summary stats
    drug_count = sum(1 for t in trials if t.is_drug_trial)
    print(f"\n  Summary:")
    print(f"    Total trials: {len(trials):,}")
    print(f"    Drug trials: {drug_count:,} ({drug_count/len(trials)*100:.1f}%)")
    
    return output_path


def month_to_number(month: str) -> int:
    """Convert month name to number (Jan=1, Dec=12)."""
    months = {
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
        'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
        'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
    }
    return months.get(month, 1)


def main():
    """
    Process all extracted AACT monthly archives.
    """
    print("AACT Monthly Archive Classifier")
    print("=" * 70)
    print(f"Looking for extracted AACT tables in: {AACT_EXTRACTED_DIR}")
    
    # Find all month directories
    if not AACT_EXTRACTED_DIR.exists():
        print(f"\n✗ AACT directory not found: {AACT_EXTRACTED_DIR}")
        print("  Run extract_aact_tables.py first to extract tables from ZIPs")
        return
    
    month_dirs = [
        d for d in sorted(AACT_EXTRACTED_DIR.iterdir())
        if d.is_dir() and parse_aact_dirname(d.name)
    ]
    
    if not month_dirs:
        print(f"\n✗ No AACT month directories found")
        print("  Expected format: YYYY_Mon (e.g., 2017_Jul)")
        return
    
    print(f"\nFound {len(month_dirs)} AACT monthly archives:")
    for d in month_dirs:
        print(f"  - {d.name}")
    
    # Process each month
    print(f"\n{'='*70}")
    print("Starting classification...")
    print(f"{'='*70}")
    
    successful = []
    failed = []
    
    for month_dir in month_dirs:
        try:
            output_path = process_aact_month(month_dir)
            if output_path:
                successful.append((month_dir.name, output_path))
            else:
                failed.append(month_dir.name)
        except Exception as e:
            print(f"\n✗ ERROR processing {month_dir.name}: {e}")
            import traceback
            traceback.print_exc()
            failed.append(month_dir.name)
            continue
    
    # Final summary
    print(f"\n{'='*70}")
    print("PROCESSING COMPLETE")
    print(f"{'='*70}")
    print(f"\nSuccessful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    
    if successful:
        print(f"\nClassified snapshots:")
        for month, path in successful:
            print(f"  {month:15} → {path}")
    
    if failed:
        print(f"\nFailed months:")
        for month in failed:
            print(f"  - {month}")


if __name__ == '__main__':
    main()
