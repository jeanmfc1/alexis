
# pipelines/backfill_anzctr_snapshots.py
'''
Synthesise historical ANZCTR snapshots by filtering the current corpus
by first_posted_date (mapped from APPROVAL DATE in ingest_anzctr_xlsx.py).

ANZCTR is monthly cadence, so default interval is 30 days and 12 periods
(covers ~1 year of baseline). The synthetic snapshots let mk_aw1 and
sci_aw1 compute momentum baselines without waiting for real monthly snapshots.

Usage:
    PYTHONPATH=. python pipelines/backfill_anzctr_snapshots.py
    PYTHONPATH=. python pipelines/backfill_anzctr_snapshots.py --weeks 12 --interval 30
    PYTHONPATH=. python pipelines/backfill_anzctr_snapshots.py --force
'''

from __future__ import annotations
import argparse, json, sys
from datetime import date, datetime, timedelta
from pathlib import Path

ANZCTR_SNAP_DIR = Path('storage/snapshots/clinical_trials_v2/anzctr')

def _parse_date(s):
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y-%m', '%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def _latest_real_snapshot():
    if not ANZCTR_SNAP_DIR.exists():
        return None
    files = sorted(
        [f for f in ANZCTR_SNAP_DIR.glob('*_anzctr_v1.json') if '_synth' not in f.name],
        key=lambda p: p.name, reverse=True,
    )
    return files[0] if files else None

def _write_synthetic(source_meta, source_file, cutoff, filtered_trials, out_dir):
    drug_count = sum(1 for t in filtered_trials if t.get('is_drug_trial'))
    metadata = {
        'source':              'ANZCTR',
        'registry':            'ANZCTR',
        'as_of':               cutoff.isoformat(),
        'window_start':        None,
        'window_end':          cutoff.isoformat(),
        'total_trials':        len(filtered_trials),
        'drug_trials':         drug_count,
        'generated_at':        datetime.now().isoformat(),
        'classifier':          source_meta.get('classifier', 'intl_drug_classifier_v2'),
        'input_file':          source_meta.get('input_file'),
        'synthetic':           True,
        'backfilled_from':     source_file.name,
        'backfill_cutoff_date': cutoff.isoformat(),
    }
    out_name = f'{cutoff.isoformat()}_anzctr_v1_synth.json'
    out_path = out_dir / out_name
    out_path.write_text(
        json.dumps({'metadata': metadata, 'trials': filtered_trials},
                   ensure_ascii=False, default=str),
        encoding='utf-8',
    )
    return out_path

def backfill(source_path, out_dir, weeks, interval_days, anchor, force=False):
    print(f'Loading source: {source_path}')
    with source_path.open('r', encoding='utf-8') as f:
        raw = json.load(f)
    src_meta   = raw.get('metadata', {})
    src_trials = raw.get('trials', [])
    print(f'  {len(src_trials):,} trials in source')

    parsed = []
    no_date = 0
    for t in src_trials:
        d = _parse_date(t.get('first_posted_date'))
        if d is None:
            no_date += 1
            continue
        parsed.append((d, t))
    parsed.sort(key=lambda x: x[0])
    print(f'  {len(parsed):,} with parseable dates ({no_date:,} skipped)')

    cutoffs = sorted({anchor - timedelta(days=i * interval_days) for i in range(1, weeks + 1)})
    print(f'  {len(cutoffs)} cutoffs: {cutoffs[0]} to {cutoffs[-1]}')

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for cutoff in cutoffs:
        out_name = f'{cutoff.isoformat()}_anzctr_v1_synth.json'
        out_path = out_dir / out_name
        if out_path.exists() and not force:
            print(f'    {cutoff}  skip (exists)')
            continue
        filtered = [t for (d, t) in parsed if d <= cutoff]
        drug_n   = sum(1 for t in filtered if t.get('is_drug_trial'))
        _write_synthetic(src_meta, source_path, cutoff, filtered, out_dir)
        written.append(out_path)
        print(f'    {cutoff}  total={len(filtered):>5,}  drug={drug_n:>5,}  -> {out_name}')

    print(f'  wrote {len(written)} synthetic snapshot(s)')
    return written

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source',   type=Path, default=None)
    parser.add_argument('--out-dir',  type=Path, default=ANZCTR_SNAP_DIR)
    parser.add_argument('--weeks',    type=int,  default=12)
    parser.add_argument('--interval', type=int,  default=30, help='Days between cutoffs (default: 30 = monthly)')
    parser.add_argument('--anchor',   default=None)
    parser.add_argument('--force',    action='store_true')
    args = parser.parse_args()

    src = args.source or _latest_real_snapshot()
    if not src or not src.exists():
        print('ERROR: no source ANZCTR snapshot found.', file=sys.stderr)
        print('       Run classify_anzctr_to_snapshot.py first.', file=sys.stderr)
        sys.exit(1)

    anchor = (datetime.strptime(args.anchor, '%Y-%m-%d').date()
              if args.anchor else date.today())

    print('=' * 64)
    print('  ANZCTR Synthetic Snapshot Backfill')
    print('=' * 64)
    print(f'  Source:   {src}')
    print(f'  Anchor:   {anchor}  Periods: {args.weeks}  Interval: {args.interval}d')
    print(f'  Force:    {args.force}')
    print()

    written = backfill(src, args.out_dir, args.weeks, args.interval, anchor, args.force)
    print()
    print('=' * 64)
    print(f'  Done. {len(written)} synthetic snapshot(s) written.')
    print('=' * 64)

if __name__ == '__main__':
    main()
