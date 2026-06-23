"""
Continuous AACT processing pipeline.

This script:
1. Monitors downloads folder for new AACT ZIP files
2. Extracts required tables from each ZIP
3. Immediately classifies the extracted data
4. Saves classified snapshots
5. Repeats continuously

Usage:
    python process_aact_continuous.py
"""

import zipfile
import time
import sys
from pathlib import Path
from datetime import date
from tqdm import tqdm

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

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

# Configuration  (portable via core.paths — were hardcoded /mnt/c, ~/projects, CWD-relative)
from core.paths import downloads_dir, snapshots_dir
DOWNLOADS_DIR = downloads_dir()                 # drop folder watched for AACT export zips
EXTRACT_DIR = snapshots_dir() / "aact"
OUTPUT_BASE_DIR = snapshots_dir()

# Required tables (only extract these)
REQUIRED_TABLES = {
    'studies.txt',
    'sponsors.txt',
    'interventions.txt',
    'conditions.txt',
    'browse_conditions.txt',
    'browse_interventions.txt'
}


def parse_month_year(filename: str) -> tuple:
    """Parse filename like 'Jul 2017.zip' into (month_name, year)."""
    try:
        parts = filename.replace('.zip', '').split()
        if len(parts) != 2:
            return None
        
        month_name = parts[0]
        year = int(parts[1])
        
        valid_months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        if month_name not in valid_months:
            return None
        
        return (month_name, year)
    except:
        return None


def month_to_number(month: str) -> int:
    """Convert month name to number (Jan=1, Dec=12)."""
    months = {
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
        'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
        'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
    }
    return months.get(month, 1)


def extract_tables_from_zip(zip_path: Path, output_dir: Path) -> bool:
    """
    Extract only required tables from AACT ZIP.
    
    Returns: True if successful, False otherwise
    """
    print(f"\n{'='*70}")
    print(f"EXTRACTING: {zip_path.name}")
    print(f"{'='*70}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            all_files = zf.namelist()
            
            # Extract only required tables with progress bar
            extracted = []
            for filename in tqdm(all_files, desc="  Extracting tables", unit="file"):
                basename = Path(filename).name
                if basename in REQUIRED_TABLES:
                    zf.extract(filename, output_dir)
                    extracted.append(basename)
            
            # Check for missing tables
            missing = REQUIRED_TABLES - set(extracted)
            
            if missing:
                print(f"  ✗ Missing tables: {missing}")
                return False
            
            # Calculate total size
            total_size_mb = sum(
                (output_dir / f).stat().st_size 
                for f in extracted 
                if (output_dir / f).exists()
            ) / 1024 / 1024
            
            print(f"  ✓ Extracted {len(extracted)} tables ({total_size_mb:.1f} MB)")
            return True
            
    except Exception as e:
        print(f"  ✗ Extraction error: {e}")
        return False


def classify_single_trial(trial: ClinicalTrialSignalV2) -> ClinicalTrialSignalV2:
    """Classify a single trial - same as weekly_pulse_clinical_v2.py"""
    
    # Pre-cache text
    trial._cached_title_interventions = " ".join(
        (trial.interventions_text or []) + [trial.title or ""]
    ).lower()
    trial._cached_title_conditions = " ".join(
        [trial.title or ""] + (trial.conditions or [])
    ).lower()

    # Drug status FIRST
    trial.is_drug_trial = is_drug_trial_v2(trial)

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


def classify_extracted_month(month_dir: Path, month_name: str, year: int) -> Path:
    """
    Classify an extracted AACT month.
    
    Returns: Path to saved snapshot, or None if failed
    """
    print(f"\n{'='*70}")
    print(f"CLASSIFYING: {year} {month_name}")
    print(f"{'='*70}")
    
    # Verify all tables exist
    missing = []
    for table in REQUIRED_TABLES:
        if not (month_dir / table).exists():
            missing.append(table)
    
    if missing:
        print(f"  ✗ Missing tables: {missing}")
        return None
    
    # Normalize
    print(f"  Normalizing AACT tables...")
    trials = normalize_aact_tables(
        studies_path=month_dir / "studies.txt",
        sponsors_path=month_dir / "sponsors.txt",
        interventions_path=month_dir / "interventions.txt",
        conditions_path=month_dir / "conditions.txt",
        browse_conditions_path=month_dir / "browse_conditions.txt",
        browse_interventions_path=month_dir / "browse_interventions.txt",
    )
    
    # Classify with progress bar
    print(f"  Classifying {len(trials):,} trials...")
    start_time = time.time()
    
    trials = process_trials_parallel(
        trials=trials,
        classifier_function=classify_single_trial,
        num_workers=None
    )
    
    elapsed = time.time() - start_time
    trials_per_sec = len(trials) / elapsed if elapsed > 0 else 0
    print(f"  ✓ Classified in {elapsed:.1f}s ({trials_per_sec:.1f} trials/sec)")
    
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
    snapshot_date = date(year, month_to_number(month_name), 1)
    
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
    
    # Print summary
    drug_count = sum(1 for t in trials if t.is_drug_trial)
    print(f"  ✓ Saved: {output_path.name}")
    print(f"    Trials: {len(trials):,} | Drug trials: {drug_count:,} ({drug_count/len(trials)*100:.1f}%)")
    
    return output_path


def is_already_processed(month_name: str, year: int) -> bool:
    """Check if this month has already been extracted AND classified."""
    # Check if extraction exists
    extract_dir = EXTRACT_DIR / f"{year}_{month_name}"
    if not extract_dir.exists():
        return False
    
    # Check if all tables exist
    for table in REQUIRED_TABLES:
        if not (extract_dir / table).exists():
            return False
    
    # Check if classified snapshot exists
    # (Classified snapshots are saved with date-based naming)
    classified_dir = OUTPUT_BASE_DIR / "aact_classified"
    if not classified_dir.exists():
        return False
    
    # Look for any snapshot from this month/year
    # Format: YYYY-MM-DD_*.json
    target_prefix = f"{year}-{month_to_number(month_name):02d}-01"
    for snapshot_file in classified_dir.glob(f"{target_prefix}_*.json"):
        return True
    
    return False


def main():
    """
    Continuous AACT processing pipeline.
    """
    print("=" * 70)
    print("AACT Continuous Processing Pipeline")
    print("=" * 70)
    print(f"\nMonitoring: {DOWNLOADS_DIR}")
    print(f"Extract to: {EXTRACT_DIR}")
    print(f"Classify to: {OUTPUT_BASE_DIR / 'aact_classified'}")
    print(f"\nThis pipeline will:")
    print(f"  1. Watch for new AACT ZIP files")
    print(f"  2. Extract required tables")
    print(f"  3. Classify immediately after extraction")
    print(f"  4. Skip already-processed archives")
    print(f"  5. Run continuously (Ctrl+C to stop)")
    
    processed_zips = set()
    total_processed = 0
    
    try:
        while True:
            # Find all AACT ZIPs
            all_zips = sorted(DOWNLOADS_DIR.glob("*.zip"))
            
            aact_zips = []
            for zf in all_zips:
                parsed = parse_month_year(zf.name)
                if parsed:
                    month_name, year = parsed
                    aact_zips.append((zf, month_name, year))
            
            # Find new ZIPs not yet processed
            new_zips = [
                (zf, month, year)
                for zf, month, year in aact_zips
                if zf.name not in processed_zips
            ]
            
            if new_zips:
                print(f"\n{'='*70}")
                print(f"Found {len(new_zips)} new archive(s)")
                print(f"{'='*70}")
                
                for zip_path, month_name, year in new_zips:
                    # Check if already processed
                    if is_already_processed(month_name, year):
                        print(f"\n⊘ Skipping {zip_path.name} (already processed)")
                        processed_zips.add(zip_path.name)
                        continue
                    
                    # STEP 1: Extract tables
                    extract_dir = EXTRACT_DIR / f"{year}_{month_name}"
                    
                    extraction_success = extract_tables_from_zip(zip_path, extract_dir)
                    
                    if not extraction_success:
                        print(f"  ✗ Extraction failed, skipping classification")
                        continue
                    
                    # STEP 2: Classify immediately
                    try:
                        output_path = classify_extracted_month(extract_dir, month_name, year)
                        
                        if output_path:
                            processed_zips.add(zip_path.name)
                            total_processed += 1
                            print(f"\n✓ COMPLETED: {year} {month_name}")
                            
                            # TODO: Enable ZIP deletion after confirming everything works
                            # Delete ZIP after successful processing
                            # try:
                            #     zip_path.unlink()
                            #     print(f"  ✓ Deleted: {zip_path.name}")
                            # except Exception as e:
                            #     print(f"  ⚠ Could not delete ZIP: {e}")
                        else:
                            print(f"\n✗ Classification failed for {year} {month_name}")
                    
                    except Exception as e:
                        print(f"\n✗ ERROR during classification: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
            
            # Status update
            timestamp = time.strftime('%H:%M:%S')
            print(f"\n[{timestamp}] Waiting for new files...")
            print(f"  Processed: {total_processed} archives")
            print(f"  Press Ctrl+C to stop")
            
            time.sleep(30)
    
    except KeyboardInterrupt:
        print(f"\n\n{'='*70}")
        print("Stopped by user")
        print(f"{'='*70}")
        print(f"\nTotal archives processed: {total_processed}")
        
        if processed_zips:
            print(f"\nProcessed archives:")
            for zip_name in sorted(processed_zips):
                print(f"  - {zip_name}")


if __name__ == '__main__':
    main()
