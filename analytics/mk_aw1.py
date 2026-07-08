
# analytics/mk_aw1.py
'''
Marketing / aw2 (ANZCTR) -- Therapeutic-Area Momentum (monthly cadence)
Mirrors mk_cw1.py but with monthly baseline (30-day interval, not weekly).
'''

from collections import Counter, defaultdict
from statistics import mean

ACCELERATING_RATIO = 1.5
ACCELERATING_MIN   = 2
SLOWING_RATIO      = 0.5
SLOWING_MIN_BASE   = 1
MIN_DAYS_BETWEEN   = 20
MAX_DRUG_PER_DAY   = 200
SCALE_TO_MONTHLY   = 30.0

def _classify_trend(this_period, baseline):
    if baseline == 0:
        return 'new' if this_period > 0 else 'steady'
    ratio = this_period / baseline
    if ratio >= ACCELERATING_RATIO and this_period >= ACCELERATING_MIN:
        return 'accelerating'
    if ratio <= SLOWING_RATIO and baseline >= SLOWING_MIN_BASE:
        return 'slowing'
    return 'steady'

def _parse_as_of(s):
    from datetime import datetime as _dt
    try:
        return _dt.fromisoformat(str(s)[:10]).date()
    except Exception:
        return None


def aw2_anzctr_ta_momentum(enriched_trials, prior_snapshots):
    new_drug    = [t for t in enriched_trials
                   if t.get('update_type') == 'new' and t.get('is_drug_trial')]
    this_counts = Counter((t.get('therapeutic_area') or 'Unassigned') for t in new_drug)
    total_new   = sum(this_counts.values())

    top_mod_by_ta = {}
    for ta in this_counts:
        mc = Counter(t.get('modality') for t in new_drug
                     if (t.get('therapeutic_area') or 'Unassigned') == ta)
        top_mod_by_ta[ta] = mc.most_common(1)[0][0] if mc else None

    baseline_per_ta = defaultdict(list)
    pair_windows = 0
    pair_windows_skipped = 0

    if prior_snapshots:
        snaps_asc = sorted(prior_snapshots,
                           key=lambda s: (s.get('metadata', {}) or {}).get('as_of', ''))
        if len(snaps_asc) >= 2:
            for older, newer in zip(snaps_asc, snaps_asc[1:]):
                old_d = _parse_as_of((older.get('metadata', {}) or {}).get('as_of'))
                new_d = _parse_as_of((newer.get('metadata', {}) or {}).get('as_of'))
                if not (old_d and new_d):
                    pair_windows_skipped += 1; continue
                days = (new_d - old_d).days
                if days < MIN_DAYS_BETWEEN:
                    pair_windows_skipped += 1; continue
                older_ids = {t.get('nct_id') for t in older.get('trials', [])
                             if t.get('is_drug_trial') and t.get('nct_id')}
                added = [t for t in newer.get('trials', [])
                         if t.get('is_drug_trial') and t.get('nct_id') not in older_ids]
                if days > 0 and (len(added) / days) > MAX_DRUG_PER_DAY:
                    pair_windows_skipped += 1; continue
                scale = SCALE_TO_MONTHLY / max(days, 1)
                by_ta = Counter((t.get('therapeutic_area') or 'Unassigned') for t in added)
                for ta, n in by_ta.items():
                    baseline_per_ta[ta].append(n * scale)
                pair_windows += 1
        else:
            only = snaps_asc[0]
            for ta, n in Counter((t.get('therapeutic_area') or 'Unassigned')
                                  for t in only.get('trials', [])
                                  if t.get('is_drug_trial')).items():
                baseline_per_ta[ta].append(n / 12.0)

    no_valid = (pair_windows == 0) and not baseline_per_ta
    if no_valid and prior_snapshots:
        return {'available': False,
                'reason': f'No valid baseline ({pair_windows_skipped} pairs skipped). Run backfill_anzctr_snapshots.py.',
                'pair_windows_skipped': pair_windows_skipped}

    items = []
    for ta in set(this_counts) | set(baseline_per_ta):
        this_n   = this_counts.get(ta, 0)
        base_avg = mean(baseline_per_ta[ta]) if baseline_per_ta.get(ta) else 0.0
        trend    = _classify_trend(this_n, base_avg)
        ratio    = (this_n / base_avg) if base_avg > 0 else None
        items.append({'ta': ta, 'this_period': this_n, 'baseline': round(base_avg, 2),
                      'ratio': round(ratio, 2) if ratio is not None else None,
                      'trend': trend, 'top_modality': top_mod_by_ta.get(ta)})

    trend_rank = {'accelerating': 0, 'new': 1, 'steady': 2, 'slowing': 3}
    items.sort(key=lambda r: (trend_rank.get(r['trend'], 9), -(r['ratio'] or 0), -r['this_period']))

    accel = [i for i in items if i['trend'] == 'accelerating']
    slow  = [i for i in items if i['trend'] == 'slowing']
    fresh = [i for i in items if i['trend'] == 'new']
    total_baseline = round(sum(mean(v) for v in baseline_per_ta.values() if v), 1)
    overall_ratio  = round(total_new / total_baseline, 2) if total_baseline > 0 else None

    def _top(rows, n=4, key='this_period'):
        return [{'ta': r['ta'], 'value': r[key], 'ratio': r['ratio'],
                 'modality': r['top_modality']} for r in rows[:n]]

    cards = [
        {'title': 'NEW DRUG TRIALS',   'value': total_new,
         'sub':  f'baseline ~{total_baseline}/month' + (f'  ({overall_ratio}x)' if overall_ratio else ''),
         'detail': _top(items), 'note': 'Volume vs monthly baseline'},
        {'title': 'ACCELERATING TAs',  'value': len(accel),
         'sub':  f'{ACCELERATING_RATIO}x baseline + min {ACCELERATING_MIN}',
         'detail': _top(accel), 'note': 'TAs concentrating in AU'},
        {'title': 'NEW / EMERGING TAs','value': len(fresh),
         'sub':  'absent from prior periods',
         'detail': _top(fresh), 'note': 'No prior baseline'},
        {'title': 'SLOWING TAs',       'value': len(slow),
         'sub':  f'<= {SLOWING_RATIO}x baseline',
         'detail': _top(slow, key='baseline'), 'note': 'Cooling vs prior months'},
    ]

    return {
        'available': total_new > 0 or bool(baseline_per_ta),
        'items': items, 'cards': cards,
        'total_new': total_new, 'total_baseline': total_baseline,
        'snapshots_used': len(prior_snapshots),
        'pair_windows': pair_windows, 'pair_windows_skipped': pair_windows_skipped,
        'cadence': 'monthly',
        'thresholds': {'accelerating_ratio': ACCELERATING_RATIO,
                       'accelerating_min': ACCELERATING_MIN,
                       'slowing_ratio': SLOWING_RATIO,
                       'slowing_min_base': SLOWING_MIN_BASE},
    }
