
# analytics/bd_aw1.py
'''
BD / aw1 (ANZCTR) -- Foreign-Sponsor First-in-Human Table

Business question (Mike Brown):
    'Which foreign-sponsored Phase 0/1 drug trials are actively recruiting in Australia?'

Source:
    Enriched ANZCTR snapshot trials[] with update_type == 'new' or all drug trials
    when no enriched file is available (falls back to full snapshot).

Returns:
    list of trial row dicts, sorted by priority_score descending.
'''

from collections import defaultdict
from analytics.shared import modality_weight, phase_weight

FIH_PHASES = {'EARLY_PHASE1', 'PHASE1', 'PHASE1_PHASE2'}
ACTIVE_STATUSES = {'RECRUITING', 'NOT_YET_RECRUITING', 'ACTIVE_NOT_RECRUITING'}

def _is_fih(phase):
    return (phase or '').upper() in FIH_PHASES

def _is_active(trial):
    status = (trial.get('overall_status') or trial.get('recruitment_status') or '').upper().replace(' ', '_')
    return status in ACTIVE_STATUSES

def aw1_foreign_sponsor_fih_table(enriched_trials, all_trials=None):
    '''
    Build the foreign-sponsor FIH action table.

    Args:
        enriched_trials: trials from anzctr_enriched_*.json  (may have update_type)
        all_trials:      fallback full snapshot trials if no enriched file available

    Returns:
        dict with keys:
            rows:        list of trial row dicts
            total_fih:   int
            total_foreign_drug: int
            available:   bool
    '''
    # Prefer new registrations from enriched; fall back to full snapshot
    if enriched_trials:
        # include both new and existing so Mike Brown always sees the full active window
        candidates = [t for t in enriched_trials if t.get('is_drug_trial')]
    elif all_trials:
        candidates = [t for t in all_trials if t.get('is_drug_trial')]
    else:
        return {'available': False, 'reason': 'no ANZCTR trial data', 'rows': []}

    foreign_drug = [t for t in candidates if t.get('is_foreign_sponsored')]
    fih_active   = [
        t for t in foreign_drug
        if _is_fih(t.get('phase')) and _is_active(t)
    ]

    rows = []
    for t in fih_active:
        score = modality_weight(t.get('modality')) * phase_weight(t.get('phase'))
        if score >= 8:
            priority_label = 'HIGH'
        elif score >= 3:
            priority_label = 'MED'
        else:
            priority_label = 'LOW'

        rows.append({
            'nct_id':                t.get('nct_id'),
            'title':                 t.get('title'),
            'phase':                 t.get('phase'),
            'overall_status':        t.get('overall_status') or t.get('recruitment_status'),
            'modality':              t.get('modality'),
            'therapeutic_area':      t.get('therapeutic_area'),
            'sponsor_name':          t.get('sponsor_name'),
            'sponsor_class':         t.get('sponsor_class'),
            'primary_sponsor_country': t.get('primary_sponsor_country'),
            'source_url':            t.get('source_url'),
            'first_posted_date':     t.get('first_posted_date'),
            'start_date':            t.get('start_date'),
            'conditions':            t.get('conditions', []),
            'interventions_text':    t.get('interventions_text', []),
            'priority_score':        round(score, 1),
            'priority_label':        priority_label,
            'is_new':                t.get('update_type') == 'new',
        })

    rows.sort(key=lambda r: (r['priority_score'], r['is_new']), reverse=True)

    return {
        'available':        True,
        'rows':             rows,
        'total_fih':        len(fih_active),
        'total_foreign_drug': len(foreign_drug),
        'total_drug':       len(candidates),
        'fih_phases':       sorted(FIH_PHASES),
    }
