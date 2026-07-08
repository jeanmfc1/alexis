
# analytics/ops_aw1.py
'''
Operations / aw4 (ANZCTR) -- Pipeline Health & Classifier Confidence
Mirrors ops_cw1.py for the ANZCTR corpus.
'''

from collections import Counter
from datetime import date, datetime
from pathlib import Path

def aw4_anzctr_pipeline_health(current_snap, xlsx_path='storage/TrialDetails ANZCTR/TrialDetails65.xlsx'):
    meta   = current_snap.get('metadata', {}) or {}
    trials = current_snap.get('trials', []) or []

    as_of = meta.get('as_of')
    try:
        as_of_date = date.fromisoformat(as_of) if as_of else None
    except ValueError:
        as_of_date = None
    days_since = (date.today() - as_of_date).days if as_of_date else None

    xlsx = Path(xlsx_path)
    if xlsx.exists():
        xlsx_mtime_dt  = datetime.fromtimestamp(xlsx.stat().st_mtime)
        xlsx_mtime     = xlsx_mtime_dt.isoformat(timespec='seconds')
        xlsx_age_days  = (datetime.now() - xlsx_mtime_dt).days
    else:
        xlsx_mtime    = None
        xlsx_age_days = None

    drug_trials   = [t for t in trials if t.get('is_drug_trial')]
    foreign_drug  = [t for t in drug_trials if t.get('is_foreign_sponsored')]
    fih_active    = [t for t in drug_trials
                     if (t.get('phase') or '') in ('EARLY_PHASE1', 'PHASE1', 'PHASE1_PHASE2')
                     and (t.get('overall_status') or '').upper() in
                         ('RECRUITING', 'NOT_YET_RECRUITING', 'ACTIVE_NOT_RECRUITING')]

    current_total = len(trials)
    current_drug  = len(drug_trials)
    drug_share    = (current_drug / current_total) if current_total else 0.0

    gt_override  = 0
    low_conf_bio = 0
    info_counter: Counter = Counter()
    sample_low_conf = []

    for t in trials:
        for f in (t.get('info_flags') or []):
            info_counter[f] += 1
            if f.startswith('override:gene_therapy'):
                gt_override += 1
            if f == 'low_confidence_biologic':
                low_conf_bio += 1
                if len(sample_low_conf) < 10:
                    sample_low_conf.append({
                        'nct_id':     t.get('nct_id'),
                        'title':      (t.get('title') or '')[:180],
                        'modality':   t.get('modality'),
                        'sponsor':    t.get('sponsor_name'),
                        'country':    t.get('primary_sponsor_country'),
                        'source_url': t.get('source_url'),
                    })

    modality_dist = Counter((t.get('modality') or 'unknown') for t in drug_trials)
    ta_dist       = Counter((t.get('therapeutic_area') or 'Unassigned') for t in drug_trials)
    country_dist  = Counter((t.get('primary_sponsor_country') or 'Unknown') for t in foreign_drug)

    return {
        'freshness': {
            'current_as_of':   as_of,
            'days_since':      days_since,
            'xlsx_mtime':      xlsx_mtime,
            'xlsx_age_days':   xlsx_age_days,
        },
        'counts': {
            'current_total':  current_total,
            'current_drug':   current_drug,
            'drug_share':     round(drug_share, 3),
            'foreign_drug':   len(foreign_drug),
            'fih_active':     len(fih_active),
        },
        'classifier_overrides': {
            'gene_therapy_override':   gt_override,
            'low_confidence_biologic': low_conf_bio,
        },
        'modality_distribution': dict(modality_dist.most_common()),
        'ta_distribution':       dict(ta_dist.most_common(15)),
        'foreign_country_distribution': dict(country_dist.most_common(15)),
        'info_flag_counts':      dict(info_counter.most_common()),
        'sample_low_confidence': sample_low_conf,
    }
