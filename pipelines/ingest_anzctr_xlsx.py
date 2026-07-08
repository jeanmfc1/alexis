
# pipelines/ingest_anzctr_xlsx.py
'''
Flatten the ANZCTR Excel export (19 relational sheets) into a single
parquet file using the same field vocabulary as the ChiCTR checkpoint
JSONL, so classify_anzctr_to_snapshot.py can consume it directly.

Input:   storage/TrialDetails ANZCTR/TrialDetails65.xlsx  (or --source)
Output:  storage/anzctr_flat.parquet

Usage:
    PYTHONPATH=. python pipelines/ingest_anzctr_xlsx.py
    PYTHONPATH=. python pipelines/ingest_anzctr_xlsx.py --source path/to.xlsx
    PYTHONPATH=. python pipelines/ingest_anzctr_xlsx.py --force
'''

from __future__ import annotations
import argparse
import warnings
from pathlib import Path
warnings.filterwarnings('ignore')
import pandas as pd

DEFAULT_XLSX = Path('storage/TrialDetails ANZCTR/TrialDetails65.xlsx')
DEFAULT_OUT  = Path('storage/anzctr_flat.parquet')
ANZCTR_URL_BASE = 'https://www.anzctr.org.au/Trial/Registration/TrialReview.aspx?id='

_PHASE_MAP = {
    'phase 0':           'EARLY_PHASE1',
    'phase 1':           'PHASE1',
    'phase 1/phase 2':   'PHASE1_PHASE2',
    'phase 1 / phase 2': 'PHASE1_PHASE2',
    'phase 1/2':         'PHASE1_PHASE2',
    'phase i/ii':        'PHASE1_PHASE2',
    'phase 2':           'PHASE2',
    'phase 2/phase 3':   'PHASE2_PHASE3',
    'phase 2/3':         'PHASE2_PHASE3',
    'phase 3':           'PHASE3',
    'phase 4':           'PHASE4',
    'not applicable':    'NA',
    'n/a':               'NA',
}

_STATUS_MAP = {
    'not yet recruiting':     'NOT_YET_RECRUITING',
    'recruiting':             'RECRUITING',
    'active, not recruiting': 'ACTIVE_NOT_RECRUITING',
    'completed':              'COMPLETED',
    'stopped early':          'TERMINATED',
    'suspended':              'SUSPENDED',
    'withdrawn':              'WITHDRAWN',
}

_SPONSOR_TYPE_MAP = {
    'commercial sector/industry':  'INDUSTRY',
    'commercial sector/industry/': 'INDUSTRY',
    'government body':             'OTHER_GOV',
    'other collaborative groups':  'OTHER',
    'university':                  'OTHER',
    'hospital':                    'OTHER',
    'individual':                  'OTHER',
    'medical college':             'OTHER',
}

AU_COUNTRIES = {'australia', 'new zealand', 'au', 'nz'}


def norm_phase(raw):
    if not raw or str(raw).lower() in ('nan', 'none', ''):
        return 'NA'
    return _PHASE_MAP.get(str(raw).strip().lower(), 'NA')

def norm_status(raw):
    if not raw or str(raw).lower() in ('nan', 'none', ''):
        return None
    return _STATUS_MAP.get(str(raw).strip().lower(), str(raw).strip().upper().replace(' ', '_'))

def norm_sponsor_type(raw):
    if not raw or str(raw).lower() in ('nan', 'none', ''):
        return 'OTHER'
    return _SPONSOR_TYPE_MAP.get(str(raw).strip().lower(), 'OTHER')

def is_foreign(country):
    if not country or str(country).lower() in ('nan', 'none', ''):
        return False
    return str(country).strip().lower() not in AU_COUNTRIES

def _clean(v):
    s = str(v).strip() if v is not None else ''
    return None if s.lower() in ('nan', 'none', '') else s

def _agg_list(xls, sheet_name, value_col):
    if sheet_name not in xls:
        return {}
    s = xls[sheet_name][['TRIAL ID', value_col]].dropna(subset=[value_col])
    s = s[s[value_col].astype(str).str.strip().str.lower().ne('nan')]
    return s.groupby('TRIAL ID')[value_col].apply(list).to_dict()


def build_flat(xlsx_path):
    print(f'  Loading sheets from {xlsx_path} ...')
    xls = pd.read_excel(xlsx_path, sheet_name=None, dtype=str)
    print(f'  Sheets: {list(xls.keys())}')
    trial = xls['TRIAL'].copy()
    print(f'  TRIAL rows: {len(trial):,}')

    conditions      = _agg_list(xls, 'HEALTH CONDITION', 'HEALTH CONDITION')
    condition_codes = _agg_list(xls, 'CONDITION  CODE', 'CONDITION CODE')
    intv_codes      = _agg_list(xls, 'INTERVENTION CODE', 'INTERVENTION CODE')
    countries_out   = _agg_list(xls, 'COUNTRY OUTSIDE AUSTRALIA', 'COUNTRY')

    fund_src = {}
    if 'FUNDING SOURCE' in xls:
        fs = xls['FUNDING SOURCE'][['TRIAL ID', 'FUNDING SOURCE TYPE', 'FUNDING SOURCE NAME']].dropna(subset=['TRIAL ID'])
        fa = fs.groupby('TRIAL ID').first().reset_index()
        fa['_blob'] = (fa['FUNDING SOURCE TYPE'].fillna('') + ' ' + fa['FUNDING SOURCE NAME'].fillna('')).str.strip()
        fund_src = fa.set_index('TRIAL ID')['_blob'].to_dict()

    rows = []
    for _, r in trial.iterrows():
        tid = _clean(r.get('TRIAL ID'))
        if not tid:
            continue
        actrn_num = _clean(r.get('ACTRN'))
        actrn_str = f'ACTRN{actrn_num}' if actrn_num else tid
        source_url = f'{ANZCTR_URL_BASE}{actrn_num}' if actrn_num else None

        conds   = conditions.get(tid, [])
        iv_list = intv_codes.get(tid, [])

        iv_parts = []
        if _clean(r.get('INTERVENTIONS')):
            iv_parts.append(str(r['INTERVENTIONS']).strip())
        if _clean(r.get('COMPARATOR')):
            iv_parts.append(str(r['COMPARATOR']).strip())
        iv_parts.extend(iv_list)
        interventions_raw = ' | '.join(iv_parts) if iv_parts else None

        target_disease = '; '.join(conds) if conds else _clean(r.get('HEALTH CONDITION'))

        prim_country = _clean(r.get('PRIMARY SPONSOR COUNTRY'))
        foreign = is_foreign(prim_country)

        reg_date = _clean(r.get('APPROVAL DATE'))
        if reg_date and len(reg_date) >= 10:
            reg_date = reg_date[:10]
        start_date = _clean(r.get('ACTUAL START DATE')) or _clean(r.get('ANTICIPATED START DATE'))
        if start_date and len(start_date) >= 10:
            start_date = start_date[:10]

        rows.append({
            'proj_id':                 actrn_str,
            'title_detail':            _clean(r.get('STUDY TITLE')) or _clean(r.get('SCIENTIFIC TITLE')),
            'objectives':              _clean(r.get('BRIEF SUMMARY')),
            'interventions_raw':       interventions_raw,
            'target_disease':          target_disease,
            'medicine_detail':         None,
            'study_type':              _clean(r.get('STUDY TYPE')),
            'phase':                   _clean(r.get('PHASE')),
            'primary_sponsor':         _clean(r.get('PRIMARY SPONSOR NAME')),
            'funding_source':          fund_src.get(tid) or _clean(r.get('PRIMARY SPONSOR TYPE')),
            'registration_date':       reg_date,
            'reg_date':                reg_date,
            'study_start':             start_date,
            'study_end':               _clean(r.get('ACTUAL END DATE')) or _clean(r.get('ANTICIPATED END DATE')),
            'source_url':              source_url,
            'actrn':                   actrn_str,
            'trial_id':                tid,
            'primary_sponsor_country': prim_country,
            'primary_sponsor_type':    _clean(r.get('PRIMARY SPONSOR TYPE')),
            'recruitment_status':      _clean(r.get('RECRUITMENT STATUS')),
            'recruitment_country':     _clean(r.get('RECRUITMENT COUNTRY')),
            'countries_outside_au':    countries_out.get(tid, []),
            'is_foreign_sponsored':    foreign,
            'condition_codes':         condition_codes.get(tid, []),
            'intervention_codes':      iv_list,
            'why_stopped':             _clean(r.get('WITHDRAWN REASON')),
            'purpose':                 _clean(r.get('PURPOSE')),
        })

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description='Flatten ANZCTR Excel to parquet')
    parser.add_argument('--source', type=Path, default=DEFAULT_XLSX)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()

    print('=' * 60)
    print('  ANZCTR Ingest: Excel -> Parquet')
    print('=' * 60)
    print(f'  Source: {args.source}')
    print(f'  Out:    {args.out}')

    if not args.source.exists():
        raise FileNotFoundError(f'Excel not found: {args.source}')

    if args.out.exists() and not args.force:
        if args.out.stat().st_mtime >= args.source.stat().st_mtime:
            print('  Parquet is up-to-date. Use --force to rebuild.')
            return

    df = build_flat(args.source)
    print(f'  Flat rows: {len(df):,}')
    print(f'  Interventional: {(df["study_type"].str.lower().str.contains("interventional", na=False)).sum():,}')
    print(f'  Foreign-sponsored: {int(df["is_foreign_sponsored"].sum()):,}')

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    size = args.out.stat().st_size / 1e6
    print(f'  Saved -> {args.out}  ({size:.1f} MB)')

if __name__ == '__main__':
    main()
