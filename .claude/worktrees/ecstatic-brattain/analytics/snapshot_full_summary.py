"""
snapshot_full_summary.py
Run from ALEXIS root: ipython analytics/snapshot_full_summary.py
"""
import json, os, sys
sys.path.insert(0, '.')

from storage.models_v2 import ClinicalTrialSignalV2
from analytics.summary_v2 import (
    drug_trial_counts,
    drug_info_overview,
    drug_modality_summary,
    drug_therapeutic_area_summary,
    drug_modality_provenance_summary,
    drug_ta_provenance_summary,
    drug_study_intent_summary,
    drug_mesh_missing_condition_summary,
    info_flag_counts_true_drugs,
    non_disease_study_category_summary,
    ta_by_phase,
    modality_by_phase,
    multi_ta_rate_by_phase,
)

# ── Load ──────────────────────────────────────────────────────────────────────
SNAPSHOT = os.environ.get(
    'SNAPSHOT',
    'storage/snapshots/clinical_trials_v2/reclassified/reclassified_2026_feb_w4.json'
)
print(f"Loading: {SNAPSHOT}")
raw    = json.load(open(SNAPSHOT))
trials = [ClinicalTrialSignalV2(**t) for t in raw['trials']]
print(f"Trials loaded: {len(trials):,}\n")

# ── Helpers ───────────────────────────────────────────────────────────────────
W = 52

def banner(title):
    print(f"\n{'='*70}\n  {title}\n{'='*70}")

def show(d, pct_of=None, sort=True):
    total = pct_of if pct_of is not None else sum(d.values())
    rows  = sorted(d.items(), key=lambda x: -x[1]) if sort else d.items()
    for k, v in rows:
        pct = f"  ({v/total*100:.1f}%)" if total else ""
        print(f"  {str(k):<{W}} {v:>8,}{pct}")

def show_pct_only(d):
    for k, v in sorted(d.items(), key=lambda x: -x[1]):
        print(f"  {str(k):<{W}} {v*100:>8.1f}%")

def show_nested(d):
    """Dict of dicts — one sub-section per outer key, sorted by total."""
    for outer_key in sorted(d, key=lambda k: -sum(d[k].values())):
        row   = d[outer_key]
        total = sum(row.values())
        print(f"\n  {outer_key}  [{total:,}]")
        for k, v in sorted(row.items(), key=lambda x: -x[1]):
            pct = f"  ({v/total*100:.1f}%)" if total else ""
            print(f"    {str(k):<{W-2}} {v:>8,}{pct}")

# ── 1. Top-line ───────────────────────────────────────────────────────────────
banner("1. TOP-LINE COUNTS")
tc = drug_trial_counts(trials)
show(tc, sort=False)

# ── 2. Drug info overview ─────────────────────────────────────────────────────
banner("2. DRUG INFO OVERVIEW")
show(drug_info_overview(trials), sort=False)

# ── 3. Study intent ───────────────────────────────────────────────────────────
banner("3. STUDY INTENT  (drug trials only)")
si = drug_study_intent_summary(trials)
si['none_or_unset'] = tc['drug_trials'] - si.get('disease',0) - si.get('non_disease',0)
show(si, pct_of=tc['drug_trials'])

# ── 4. Therapeutic area ───────────────────────────────────────────────────────
banner("4. THERAPEUTIC AREA  (drug trials only)")
show(drug_therapeutic_area_summary(trials), pct_of=tc['drug_trials'])

# ── 5. Modality ───────────────────────────────────────────────────────────────
banner("5. MODALITY  (drug trials only)")
show(drug_modality_summary(trials), pct_of=tc['drug_trials'])

# ── 6. TA provenance ──────────────────────────────────────────────────────────
banner("6. TA PROVENANCE")
show(drug_ta_provenance_summary(trials), pct_of=tc['drug_trials'])

# ── 7. Modality provenance ────────────────────────────────────────────────────
banner("7. MODALITY PROVENANCE")
show(drug_modality_provenance_summary(trials), pct_of=tc['drug_trials'])

# ── 8. Info flags ─────────────────────────────────────────────────────────────
banner("8. INFO FLAGS  (drug trials only)")
show(info_flag_counts_true_drugs(trials))

# ── 9. Non-disease categories ─────────────────────────────────────────────────
banner("9. NON-DISEASE STUDY CATEGORIES")
nd = non_disease_study_category_summary(trials)
show(nd, pct_of=sum(nd.values()))

# ── 10. Condition mesh missing ────────────────────────────────────────────────
banner("10. CONDITION MESH MISSING")
show(drug_mesh_missing_condition_summary(trials), pct_of=tc['drug_trials'])

# ── 11. Multi-TA rate by phase ────────────────────────────────────────────────
banner("11. MULTI-TA RATE BY PHASE")
show_pct_only(multi_ta_rate_by_phase(trials))

# ── 12. TA × Phase ────────────────────────────────────────────────────────────
banner("12. TA × PHASE  (drug trials only)")
show_nested(ta_by_phase(trials))

# ── 13. Modality × Phase ──────────────────────────────────────────────────────
banner("13. MODALITY × PHASE  (drug trials only)")
show_nested(modality_by_phase(trials))

print(f"\n{'='*70}\n  DONE\n{'='*70}\n")
