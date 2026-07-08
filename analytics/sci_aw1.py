
# analytics/sci_aw1.py
'''
Scientific / aw3 (ANZCTR) -- TA x Modality Bubble Matrix
Mirrors sci_cw1.py for the ANZCTR corpus.
'''

from collections import Counter, defaultdict

MAX_TA  = 12
MAX_MOD = 10

def aw3_anzctr_ta_modality_matrix(enriched_trials, prior_snapshots=None):
    ta_mod_week = defaultdict(lambda: defaultdict(int))
    cell_trials = defaultdict(list)

    new_drug = [t for t in enriched_trials
                if t.get('update_type') == 'new' and t.get('is_drug_trial')]

    for t in new_drug:
        ta  = t.get('therapeutic_area') or 'Unknown'
        mod = t.get('modality')         or 'Unknown'
        ta_mod_week[ta][mod] += 1
        cell_trials[f'{ta}||{mod}'].append({
            'nct_id':     t.get('nct_id'),
            'title':      t.get('title'),
            'phase':      t.get('phase') or '-',
            'sponsor':    t.get('sponsor_name'),
            'country':    t.get('primary_sponsor_country'),
            'source_url': t.get('source_url'),
        })

    if not ta_mod_week:
        return {'available': False, 'rows': [], 'columns': [], 'cells': {},
                'row_totals': {}, 'col_totals': {}, 'grand_total': 0,
                'has_heat': False, 'heat_mode': 'none', 'prior_weeks_used': 0, 'week_total': 0}

    ta_totals  = {ta: sum(m.values()) for ta, m in ta_mod_week.items()}
    mod_totals = defaultdict(int)
    for mods in ta_mod_week.values():
        for mod, n in mods.items():
            mod_totals[mod] += n

    top_tas  = sorted(ta_totals,  key=ta_totals.__getitem__,  reverse=True)[:MAX_TA]
    top_mods = sorted(mod_totals, key=mod_totals.__getitem__, reverse=True)[:MAX_MOD]

    week_total  = sum(mod_totals.values()) or 1
    grand_total = sum(ta_totals[ta] for ta in top_tas)

    prior_weeks = []
    if prior_snapshots and len(prior_snapshots) >= 2:
        snaps_asc = sorted(prior_snapshots,
                           key=lambda s: (s.get('metadata', {}) or {}).get('as_of', ''))
        for older, newer in zip(snaps_asc, snaps_asc[1:]):
            older_ids = {t.get('nct_id') for t in older.get('trials', [])
                         if t.get('is_drug_trial') and t.get('nct_id')}
            pw_new = [t for t in newer.get('trials', [])
                      if t.get('is_drug_trial') and t.get('nct_id') not in older_ids]
            pw_ta_mod = defaultdict(lambda: defaultdict(int))
            for t in pw_new:
                pw_ta_mod[t.get('therapeutic_area') or 'Unknown'][t.get('modality') or 'Unknown'] += 1
            newer_as_of = (newer.get('metadata') or {}).get('as_of', '')
            older_as_of = (older.get('metadata') or {}).get('as_of', '')
            prior_weeks.append({
                'window_label':   f'{older_as_of} -> {newer_as_of}',
                'drug_new_total': len(pw_new),
                'ta_mod': {ta: dict(mods) for ta, mods in pw_ta_mod.items()},
            })

    has_heat  = bool(prior_weeks)
    heat_mode = 'rolling_avg' if has_heat else 'none'
    prior_avg_pct = {}
    if has_heat:
        for ta in top_tas:
            for mod in top_mods:
                contributions = []
                for pw in prior_weeks:
                    pw_total = pw.get('drug_new_total') or 0
                    if pw_total > 0:
                        contributions.append((pw.get('ta_mod') or {}).get(ta, {}).get(mod, 0) / pw_total)
                prior_avg_pct[(ta, mod)] = sum(contributions) / len(contributions) if contributions else 0.0

    cells = {}
    for ta in top_tas:
        for mod in top_mods:
            count = ta_mod_week[ta].get(mod, 0)
            prior_avg_count = None
            if has_heat:
                cnts = [(pw.get('ta_mod') or {}).get(ta, {}).get(mod, 0) for pw in prior_weeks]
                prior_avg_count = round(sum(cnts) / len(cnts), 1) if cnts else None
            heat = heat_label = None
            if count > 0 and has_heat:
                avg_pct  = prior_avg_pct.get((ta, mod), 0.0)
                curr_pct = count / week_total
                raw      = (curr_pct - avg_pct) / max(avg_pct, 0.001)
                heat     = max(-1.0, min(1.0, raw))
                if avg_pct == 0:
                    heat_label = 'new this period -- not in prior snapshots'
                else:
                    dp = round(heat * 100, 0)
                    if heat >= 0.15:
                        heat_label = f'+{abs(dp):.0f}% above {len(prior_weeks)}-period avg'
                    elif heat <= -0.15:
                        heat_label = f'-{abs(dp):.0f}% below {len(prior_weeks)}-period avg'
                    else:
                        heat_label = f'in line with {len(prior_weeks)}-period avg'

            cells[f'{ta}||{mod}'] = {
                'ta': ta, 'mod': mod, 'count': count,
                'baseline_n': None, 'prior_avg_count': prior_avg_count,
                'heat': round(heat, 3) if heat is not None else None,
                'heat_label': heat_label,
                'trials': cell_trials.get(f'{ta}||{mod}', []),
            }

    row_totals = {ta:  sum(ta_mod_week[ta].get(m, 0)  for m  in top_mods) for ta  in top_tas}
    col_totals = {mod: sum(ta_mod_week[ta].get(mod, 0) for ta in top_tas) for mod in top_mods}

    return {
        'available': True, 'has_heat': has_heat, 'heat_mode': heat_mode,
        'prior_weeks_used': len(prior_weeks),
        'prior_window_labels': [pw['window_label'] for pw in prior_weeks],
        'rows': top_tas, 'columns': top_mods, 'cells': cells,
        'row_totals': row_totals, 'col_totals': col_totals,
        'grand_total': grand_total, 'db_total': 0, 'week_total': week_total,
    }
