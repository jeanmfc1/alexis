
# pipelines/diff_anzctr_snapshots.py
'''
Diff two ANZCTR snapshots (same logic as diff_chictr_snapshots.py).

Since ANZCTR is a static monthly Excel export, each new ingest is a fresh
full corpus. The diff between runs reveals new registrations and changes.

Usage:
    PYTHONPATH=. python pipelines/diff_anzctr_snapshots.py --prior PRIOR --current CURR
    PYTHONPATH=. python pipelines/run_diff_anzctr.py   (interactive launcher)
'''

from __future__ import annotations
import argparse, json, sys
from collections import Counter
from datetime import datetime
from pathlib import Path

W = 72

FIELD_TO_CATEGORY = {
    'title':                   'title_change',
    'phase':                   'phase_change',
    'study_type':              'study_type_change',
    'overall_status':          'status_change',
    'sponsor_class':           'sponsor_change',
    'sponsor_name':            'sponsor_change',
    'conditions':              'condition_change',
    'interventions_text':      'intervention_change',
    'is_drug_trial':           'drug_status_change',
    'modality':                'modality_change',
    'therapeutic_area':        'ta_change',
    'study_intent':            'intent_change',
    'study_category':          'intent_change',
    'start_date':              'date_change',
    'completion_date':         'date_change',
    'first_posted_date':       'date_change',
}

def _norm(v):
    if isinstance(v, list):
        return tuple(sorted(str(x) for x in v if x is not None))
    if isinstance(v, str):
        return v.strip()
    return v

def diff_trial(prior, current):
    changes = []
    for field, category in FIELD_TO_CATEGORY.items():
        p = _norm(prior.get(field))
        c = _norm(current.get(field))
        if p != c:
            changes.append({'category': category, 'field': field,
                            'prior': prior.get(field), 'current': current.get(field)})
    return changes

def compute_diff(prior_snap, current_snap):
    prior_map   = {t['nct_id']: t for t in prior_snap['trials']}
    current_map = {t['nct_id']: t for t in current_snap['trials']}
    prior_ids   = set(prior_map)
    current_ids = set(current_map)
    new_ids     = current_ids - prior_ids
    removed_ids = prior_ids - current_ids

    enriched = []
    update_count   = Counter()
    category_count = Counter()
    category_combos = Counter()
    per_trial_change_count = Counter()

    for nct in current_ids:
        row = dict(current_map[nct])
        if nct in new_ids:
            row['update_type'] = 'new'
            row['update_categories'] = []
            update_count['new'] += 1
        else:
            changes = diff_trial(prior_map[nct], current_map[nct])
            if changes:
                row['update_type'] = 'existing'
                row['update_categories'] = changes
                update_count['existing'] += 1
                cats = {c['category'] for c in changes}
                for cat in cats:
                    category_count[cat] += 1
                category_combos[tuple(sorted(cats))] += 1
                per_trial_change_count[len(changes)] += 1
            else:
                row['update_type'] = 'unchanged'
                row['update_categories'] = []
                update_count['unchanged'] += 1
        enriched.append(row)

    changelog = {
        'prior_snapshot':   prior_snap.get('metadata', {}),
        'current_snapshot': current_snap.get('metadata', {}),
        'generated_at':     datetime.now().isoformat(),
        'counts': {
            'prior_trials':       len(prior_ids),
            'current_trials':     len(current_ids),
            'new':                len(new_ids),
            'removed':            len(removed_ids),
            'existing_changed':   update_count['existing'],
            'existing_unchanged': update_count['unchanged'],
        },
        'removed_nct_ids':  sorted(removed_ids)[:500],
        'category_counts':  dict(category_count),
        'category_combos':  {' + '.join(combo): n for combo, n in category_combos.most_common()},
        'per_trial_change_count': dict(per_trial_change_count),
    }
    return enriched, changelog

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--prior',   required=True)
    parser.add_argument('--current', required=True)
    parser.add_argument('--out-dir', default='storage/anzctr_changelogs')
    args = parser.parse_args(argv)

    prior_path   = Path(args.prior)
    current_path = Path(args.current)
    out_dir      = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f'Loading prior:   {prior_path}')
    print(f'Loading current: {current_path}')
    prior_snap   = json.load(open(prior_path, encoding='utf-8'))
    current_snap = json.load(open(current_path, encoding='utf-8'))
    print(f'  prior:   {len(prior_snap["trials"]):,}')
    print(f'  current: {len(current_snap["trials"]):,}')

    enriched, changelog = compute_diff(prior_snap, current_snap)
    c = changelog['counts']
    print(f'  new={c["new"]:,}  changed={c["existing_changed"]:,}  unchanged={c["existing_unchanged"]:,}  removed={c["removed"]:,}')

    prior_stem   = prior_path.stem.split('_anzctr_v1')[0]
    curr_stem    = current_path.stem.split('_anzctr_v1')[0]
    enr_path     = out_dir / f'anzctr_enriched_{curr_stem}_vs_{prior_stem}.json'
    clog_path    = out_dir / f'anzctr_changelog_{curr_stem}_vs_{prior_stem}.json'

    enriched_out = {
        'metadata': {'source': 'ANZCTR', 'diff_prior': str(prior_path),
                     'diff_current': str(current_path),
                     'generated_at': datetime.now().isoformat(),
                     **current_snap.get('metadata', {})},
        'trials':           enriched,
        'changelog_counts': changelog['counts'],
    }

    enr_path.write_text(json.dumps(enriched_out, ensure_ascii=False, default=str), encoding='utf-8')
    clog_path.write_text(json.dumps(changelog, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(f'  Enriched: {enr_path}  ({enr_path.stat().st_size/1e6:.1f} MB)')
    print(f'  Changelog: {clog_path}')

if __name__ == '__main__':
    main()
