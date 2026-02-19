#!/usr/bin/env python3
"""
Audit snapshots to find which ones have broken drug classification
"""

import json
from pathlib import Path
import sys

reclass_dir = Path("storage/snapshots/clinical_trials_v2/reclassified")

print("=== AUDITING RECLASSIFIED SNAPSHOTS ===\n")
print(f"{'Filename':<35} {'Total':>7} {'Drug':>6} {'Non-Drug':>9} {'Status':<10}")
print("-" * 75)

broken_files = []
good_files = []

for snapshot_path in sorted(reclass_dir.glob("*.json")):
    try:
        with open(snapshot_path) as f:
            snap = json.load(f)
        
        total = len(snap.get('trials', []))
        drug = len([t for t in snap['trials'] if t.get('is_drug_trial')])
        non_drug = total - drug
        
        # Check if broken (0 drug trials despite having total trials)
        if total > 0 and drug == 0:
            status = "❌ BROKEN"
            broken_files.append(snapshot_path.name)
        elif total == 0:
            status = "⚠️ EMPTY"
            broken_files.append(snapshot_path.name)
        else:
            status = "✓ OK"
            good_files.append(snapshot_path.name)
        
        print(f"{snapshot_path.name:<35} {total:>7,} {drug:>6,} {non_drug:>9,} {status:<10}")
        
    except Exception as e:
        print(f"{snapshot_path.name:<35} ERROR: {e}")
        broken_files.append(snapshot_path.name)

print(f"\n{'='*75}")
print(f"Summary:")
print(f"  Good snapshots: {len(good_files)}")
print(f"  Broken snapshots: {len(broken_files)}")

if broken_files:
    print(f"\n{'='*75}")
    print("BROKEN FILES TO DELETE:")
    print("="*75)
    for f in broken_files:
        print(f"  rm storage/snapshots/clinical_trials_v2/reclassified/{f}")
    
    print(f"\nOr delete all at once:")
    print(f"  rm " + " ".join([f"storage/snapshots/clinical_trials_v2/reclassified/{f}" for f in broken_files]))

# Check the original source files for broken ones
print(f"\n{'='*75}")
print("CHECKING ORIGINAL SOURCE FILES:")
print("="*75)

orig_dir = Path("storage/snapshots/clinical_trials_v2/last_update")

for broken_file in broken_files:
    # Try to find the original
    orig_name = broken_file.replace('reclassified_', '')
    orig_path = orig_dir / orig_name
    
    if orig_path.exists():
        try:
            with open(orig_path) as f:
                snap = json.load(f)
            total = len(snap.get('trials', []))
            has_iv_all = False
            if snap.get('trials'):
                has_iv_all = 'interventions_all' in snap['trials'][0]
            
            print(f"\n{orig_name}:")
            print(f"  Original trials: {total}")
            print(f"  Has interventions_all: {has_iv_all}")
            
            if total > 0 and not has_iv_all:
                print(f"  ⚠️ CORRUPTED SOURCE - missing interventions_all field")
                print(f"  → DELETE: rm storage/snapshots/clinical_trials_v2/last_update/{orig_name}")
        except Exception as e:
            print(f"  ERROR reading original: {e}")
    else:
        print(f"\n{orig_name}: Original not found")