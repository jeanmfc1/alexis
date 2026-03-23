#!/usr/bin/env python3
"""
MASTER TRIAL TRACKING DATABASE BUILDER

Converts 474 weekly snapshots into ONE master database tracking each trial over time.

INPUT:  storage/snapshots/clinical_trials_v2/reclassified/*.json
OUTPUT: storage/trial_tracking_database.json + trial_tracking_indices.json
TIME:   ~15-20 minutes
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import sys


def normalize_value(value):
    """Normalize values for consistent comparison"""
    if value is None or value == '' or value == []:
        return None
    
    if isinstance(value, list):
        try:
            return tuple(sorted(json.dumps(v, sort_keys=True) for v in value))
        except:
            return tuple(sorted(str(v) for v in value))
    
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    
    return value


def detect_change(old_value, new_value):
    """Check if field actually changed"""
    old_norm = normalize_value(old_value)
    new_norm = normalize_value(new_value)
    changed = old_norm != new_norm
    return changed, old_norm, new_norm


def create_change_record(snapshot_date, field, old_value, new_value):
    """Create structured change record"""
    return {
        'snapshot_date': snapshot_date,
        'field': field,
        'old_value': old_value,
        'new_value': new_value,
    }


def build_master_tracking_database():
    """Build master trial tracking database from all snapshots"""
    
    print("="*70)
    print("MASTER TRIAL TRACKING DATABASE BUILDER")
    print("="*70)
    
    # Find snapshot files
    print("\nSTEP 1: Finding snapshot files...")
    reclass_dir = Path('storage/snapshots/clinical_trials_v2/reclassified')
    
    if not reclass_dir.exists():
        print(f"\n❌ ERROR: Directory not found: {reclass_dir}")
        sys.exit(1)
    
    snapshot_files = list(reclass_dir.glob('reclassified_*.json'))
    
    if len(snapshot_files) == 0:
        print(f"\n❌ ERROR: No snapshot files found in {reclass_dir}")
        sys.exit(1)
    
    print(f"  Found {len(snapshot_files)} snapshot files")
    
    # Load and sort snapshots
    print("\nSTEP 2: Loading and sorting snapshots chronologically...")
    
    snapshots = []
    load_errors = []
    
    for snap_path in snapshot_files:
        try:
            with open(snap_path) as f:
                snap = json.load(f)
            
            if 'metadata' not in snap or 'trials' not in snap:
                load_errors.append(f"{snap_path.name}: Missing metadata or trials")
                continue
            
            if 'window_end' not in snap['metadata']:
                load_errors.append(f"{snap_path.name}: Missing window_end in metadata")
                continue
            
            window_end = snap['metadata']['window_end']
            snapshots.append((window_end, snap_path, snap))
            
        except json.JSONDecodeError as e:
            load_errors.append(f"{snap_path.name}: Invalid JSON - {e}")
        except Exception as e:
            load_errors.append(f"{snap_path.name}: Error - {e}")
    
    if load_errors:
        print(f"\n⚠️  WARNING: {len(load_errors)} files had errors:")
        for err in load_errors[:5]:
            print(f"    {err}")
        if len(load_errors) > 5:
            print(f"    ... and {len(load_errors) - 5} more")
        
        response = input(f"\nContinue with {len(snapshots)} valid files? [y/N]: ")
        if response.lower() != 'y':
            print("Cancelled.")
            sys.exit(1)
    
    snapshots.sort(key=lambda x: x[0])
    
    print(f"  Successfully loaded {len(snapshots)} snapshots")
    print(f"  Date range: {snapshots[0][0]} to {snapshots[-1][0]}")
    
    # Process snapshots
    print("\nSTEP 3: Processing snapshots chronologically...")
    
    master = {}
    stats = {
        'snapshots_processed': 0,
        'trials_seen': 0,
        'new_trials_added': 0,
        'total_changes_detected': 0,
        'changes_by_field': defaultdict(int),
    }
    
    TRACKED_FIELDS = {
        'overall_status', 'phase', 'enrollment',
        'is_drug_trial', 'modality', 'therapeutic_area',
        'sponsor_class', 'conditions',
    }
    
    for snapshot_date, snap_path, snap in snapshots:
        stats['snapshots_processed'] += 1
        
        if stats['snapshots_processed'] % 25 == 0:
            print(f"  Processed {stats['snapshots_processed']}/{len(snapshots)} snapshots...")
        
        for trial in snap['trials']:
            nct_id = trial.get('nct_id')
            if not nct_id:
                continue
            
            stats['trials_seen'] += 1
            
            # First time seeing this trial
            if nct_id not in master:
                stats['new_trials_added'] += 1
                
                master[nct_id] = {
                    'nct_id': nct_id,
                    'title': trial.get('title', ''),
                    'first_seen_in_database': snapshot_date,
                    'last_seen_in_database': snapshot_date,
                    'appearance_count': 1,
                    'appearance_dates': [snapshot_date],
                    'current': {
                        field: trial.get(field)
                        for field in TRACKED_FIELDS | {
                            'first_posted_date', 'last_update_posted_date',
                            'start_date', 'primary_completion_date',
                            'study_type'
                        }
                        if field in trial
                    },
                    'changes': [],
                }
                continue
            
            # Seen before - check for changes
            record = master[nct_id]
            record['last_seen_in_database'] = snapshot_date
            record['appearance_count'] += 1
            record['appearance_dates'].append(snapshot_date)
            
            for field in TRACKED_FIELDS:
                old_value = record['current'].get(field)
                new_value = trial.get(field)
                
                changed, old_norm, new_norm = detect_change(old_value, new_value)
                
                if changed:
                    change_record = create_change_record(
                        snapshot_date, field, old_value, new_value
                    )
                    record['changes'].append(change_record)
                    stats['total_changes_detected'] += 1
                    stats['changes_by_field'][field] += 1
                    record['current'][field] = new_value
            
            for date_field in ['first_posted_date', 'last_update_posted_date',
                              'start_date', 'primary_completion_date']:
                if date_field in trial:
                    record['current'][date_field] = trial[date_field]
    
    print(f"\n  ✓ Completed processing {stats['snapshots_processed']} snapshots")
    
    # Generate statistics
    print("\nSTEP 4: Generating statistics...")
    
    print(f"\n{'='*70}")
    print("DATABASE STATISTICS")
    print("="*70)
    
    print(f"\nProcessing Summary:")
    print(f"  Snapshots processed: {stats['snapshots_processed']}")
    print(f"  Total trial appearances: {stats['trials_seen']:,}")
    print(f"  Unique trials: {len(master):,}")
    print(f"  New trials added: {stats['new_trials_added']:,}")
    print(f"  Total changes detected: {stats['total_changes_detected']:,}")
    
    print(f"\nTop 10 fields that changed:")
    for field, count in sorted(stats['changes_by_field'].items(), 
                               key=lambda x: -x[1])[:10]:
        print(f"  {field:<30} {count:>6,} changes")
    
    appearance_dist = defaultdict(int)
    for record in master.values():
        appearance_dist[record['appearance_count']] += 1
    
    print(f"\nAppearance frequency:")
    for appearances in sorted(appearance_dist.keys())[:10]:
        count = appearance_dist[appearances]
        pct = count / len(master) * 100
        print(f"  {appearances:>3} weeks: {count:>6,} trials ({pct:.1f}%)")
    
    if len(appearance_dist) > 10:
        print(f"  ... ({len(appearance_dist) - 10} more buckets)")
    
    drug_trials = sum(1 for r in master.values() 
                     if r['current'].get('is_drug_trial'))
    
    print(f"\nTrial Classification:")
    print(f"  Drug trials: {drug_trials:,} ({drug_trials/len(master)*100:.1f}%)")
    print(f"  Non-drug: {len(master)-drug_trials:,}")
    
    # Save database
    print(f"\n{'='*70}")
    print("STEP 5: Saving database...")
    print("="*70)
    
    output_path = Path('storage/trial_tracking_database.json')
    
    master_data = {
        'metadata': {
            'created': datetime.now().isoformat(),
            'description': 'Longitudinal trial tracking database',
            'source': 'reclassified snapshots 2017-2026',
            'snapshot_count': stats['snapshots_processed'],
            'date_range': {
                'earliest': snapshots[0][0],
                'latest': snapshots[-1][0],
            },
            'total_unique_trials': len(master),
            'format': 'TRIAL_TRACKING_DATABASE_V1',
        },
        'statistics': {
            'processing': dict(stats),
            'appearance_distribution': dict(appearance_dist),
            'drug_trials': drug_trials,
        },
        'trials': master,
    }
    
    try:
        with open(output_path, 'w') as f:
            json.dump(master_data, f, indent=2)
        
        file_size_mb = output_path.stat().st_size / 1024 / 1024
        
        print(f"\n✓ Database saved:")
        print(f"  Path: {output_path}")
        print(f"  Size: {file_size_mb:.1f} MB")
        print(f"  Trials: {len(master):,}")
        
    except Exception as e:
        print(f"\n❌ ERROR saving database: {e}")
        sys.exit(1)
    
    # Create indices
    print(f"\n{'='*70}")
    print("STEP 6: Creating indices...")
    print("="*70)
    
    indices = {
        'by_modality': defaultdict(list),
        'by_therapeutic_area': defaultdict(list),
        'by_phase': defaultdict(list),
    }
    
    for year in range(2017, 2027):
        indices[f'registered_{year}'] = []
    
    indices['frequently_updated'] = []
    indices['rarely_updated'] = []
    
    total_weeks = len(snapshots)
    
    for nct_id, record in master.items():
        mod = record['current'].get('modality')
        if mod:
            indices['by_modality'][mod].append(nct_id)
        
        ta = record['current'].get('therapeutic_area')
        if ta:
            indices['by_therapeutic_area'][ta].append(nct_id)
        
        phase = record['current'].get('phase')
        if phase:
            indices['by_phase'][phase].append(nct_id)
        
        first_posted = record['current'].get('first_posted_date', '')
        for year in range(2017, 2027):
            if first_posted.startswith(str(year)):
                indices[f'registered_{year}'].append(nct_id)
                break
        
        appearance_rate = record['appearance_count'] / total_weeks
        if appearance_rate > 0.25:
            indices['frequently_updated'].append(nct_id)
        elif appearance_rate < 0.05:
            indices['rarely_updated'].append(nct_id)
    
    indices['by_modality'] = dict(indices['by_modality'])
    indices['by_therapeutic_area'] = dict(indices['by_therapeutic_area'])
    indices['by_phase'] = dict(indices['by_phase'])
    
    index_path = Path('storage/trial_tracking_indices.json')
    
    try:
        with open(index_path, 'w') as f:
            json.dump(indices, f, indent=2)
        
        print(f"\n✓ Indices saved: {index_path}")
        print(f"\nRegistrations by year:")
        for year in range(2017, 2027):
            count = len(indices[f'registered_{year}'])
            if count > 0:
                print(f"  {year}: {count:,} trials")
        
    except Exception as e:
        print(f"\n⚠️  Warning: Could not save indices: {e}")
    
    print(f"\n{'='*70}")
    print("BUILD COMPLETE ✓")
    print("="*70)
    
    return master_data, indices


if __name__ == "__main__":
    print("\nMaster Trial Tracking Database Builder")
    print("Time: ~15-20 minutes\n")
    
    response = input("Ready to begin? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        sys.exit(0)
    
    try:
        master_data, indices = build_master_tracking_database()
        print("\n✓ SUCCESS - Database ready for analysis")
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
