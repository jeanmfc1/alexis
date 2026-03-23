"""
backfill_snapshots.py - Backfills eligibility_criteria and why_stopped
into all existing ALEXIS snapshot JSON files by querying AACT live.
Usage: python backfill_snapshots.py [--dry-run]
"""

from __future__ import annotations
import json, sys, io, time, argparse, traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set
import psycopg2

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

_UTC = timezone.utc

AACT_HOST = 'aact-db.ctti-clinicaltrials.org'
AACT_PORT = 5432
AACT_DB = 'aact'
AACT_USER = 'jeanmfc'
AACT_PASS = 'jmarcos4'
BATCH_SIZE = 1000
SLEEP_BETWEEN_BATCHES = 0.3

SNAPSHOT_ROOT = Path('//wsl.localhost/Ubuntu/home/jeanmfc/projects/ALEXIS/storage/snapshots/clinical_trials_v2')
SNAPSHOT_DIRS = [SNAPSHOT_ROOT / 'active_universe', SNAPSHOT_ROOT / 'last_update']
SKIP_PATTERNS = {'cache'}

def connect_aact():
    print(f'  Connecting to AACT ({AACT_HOST}:{AACT_PORT}/{AACT_DB}) ...')
    conn = psycopg2.connect(host=AACT_HOST, port=AACT_PORT, dbname=AACT_DB,
                            user=AACT_USER, password=AACT_PASS, connect_timeout=30)
    conn.set_client_encoding('UTF8')
    print('  Connected.')
    return conn


def fetch_eligibility_batch(cur, nct_ids):
    if not nct_ids: return {}
    cur.execute('SELECT nct_id, criteria FROM ctgov.eligibilities WHERE nct_id = ANY(%s)', (nct_ids,))
    return {r[0]: r[1] for r in cur.fetchall() if r[1]}


def fetch_why_stopped_batch(cur, nct_ids):
    if not nct_ids: return {}
    cur.execute('SELECT nct_id, why_stopped FROM ctgov.studies '
                'WHERE nct_id = ANY(%s) AND why_stopped IS NOT NULL', (nct_ids,))
    return {r[0]: r[1] for r in cur.fetchall() if r[1]}


def fetch_fields_for_ncts(conn, nct_ids, need_eligibility=True, need_why_stopped=True):
    elig_map, ws_map = {}, {}
    cur = conn.cursor()
    total = len(nct_ids)
    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, total, BATCH_SIZE):
        batch = nct_ids[i:i+BATCH_SIZE]
        bn = (i // BATCH_SIZE) + 1
        if need_eligibility: elig_map.update(fetch_eligibility_batch(cur, batch))
        if need_why_stopped: ws_map.update(fetch_why_stopped_batch(cur, batch))
        if bn % 10 == 0 or bn == num_batches:
            print(f'    Batch {bn}/{num_batches} ({len(elig_map)} elig, {len(ws_map)} ws)')
        if bn < num_batches: time.sleep(SLEEP_BETWEEN_BATCHES)
    cur.close()
    return elig_map, ws_map


def discover_snapshot_files():
    files = []
    for d in SNAPSHOT_DIRS:
        if d.is_dir():
            for fp in sorted(d.glob('*.json')):
                files.append(fp)
    return files


def should_skip(path, data):
    name = path.stem
    for pat in SKIP_PATTERNS:
        if pat in name:
            return True, 'cache file (no trials)'
    meta = data.get('metadata', {})
    patched = meta.get('patched_fields')
    if patched and 'eligibility_criteria' in patched and 'why_stopped' in patched:
        return True, 'already patched'
    trials = data.get('trials')
    if not trials or not isinstance(trials, list) or len(trials) == 0:
        return True, 'no trials in file'
    return False, ''


def patch_file(path, conn, dry_run=False):
    stats = {'file': path.name, 'status': 'unknown', 'trials': 0,
             'elig_patched': 0, 'ws_patched': 0,
             'elig_already': 0, 'ws_already': 0, 'missing_in_aact': 0}
    try:
        print()
        print(f'Loading {path.name} ...')
        with path.open('r', encoding='utf-8') as fh:
            data = json.load(fh)
        skip, reason = should_skip(path, data)
        if skip:
            print(f'    SKIP: {reason}')
            stats['status'] = f'skipped: {reason}'
            return stats
        trials = data['trials']
        stats['trials'] = len(trials)
        print(f'    {len(trials):,} trials')
        nct_ids, need_elig_ncts, need_ws_ncts = [], set(), set()
        for t in trials:
            nct = t.get('nct_id')
            if not nct: continue
            nct_ids.append(nct)
            if not t.get('eligibility_criteria'):
                need_elig_ncts.add(nct)
            else:
                stats['elig_already'] += 1
            if not t.get('why_stopped'):
                need_ws_ncts.add(nct)
            else:
                stats['ws_already'] += 1
        ea, wa = stats['elig_already'], stats['ws_already']
        print(f'    Need: {len(need_elig_ncts):,} elig, {len(need_ws_ncts):,} ws | Have: {ea:,} elig, {wa:,} ws')
        need_elig = len(need_elig_ncts) > 0
        need_ws = len(need_ws_ncts) > 0
        elig_map, ws_map = {}, {}
        if not need_elig and not need_ws:
            print('    All trials already have both fields -- marking as patched')
        else:
            all_ncts = list(set(nct_ids))
            print(f'    Fetching from AACT ({len(all_ncts):,} NCTs) ...')
            t0 = time.time()
            elig_map, ws_map = fetch_fields_for_ncts(conn, all_ncts,
                need_eligibility=need_elig, need_why_stopped=need_ws)
            elapsed = time.time() - t0
            print(f'    Fetched in {elapsed:.1f}s: {len(elig_map):,} elig, {len(ws_map):,} ws')
            for t in trials:
                nct = t.get('nct_id')
                if not nct: continue
                if need_elig and nct in need_elig_ncts:
                    ec = elig_map.get(nct)
                    if ec:
                        t['eligibility_criteria'] = ec
                        stats['elig_patched'] += 1
                    else:
                        t.setdefault('eligibility_criteria', None)
                if need_ws and nct in need_ws_ncts:
                    ws = ws_map.get(nct)
                    if ws:
                        t['why_stopped'] = ws
                        stats['ws_patched'] += 1
                    else:
                        t.setdefault('why_stopped', None)
            stats['missing_in_aact'] = len(need_elig_ncts - set(elig_map.keys()))
        meta = data.get('metadata', {})
        pf = set(meta.get('patched_fields', []) or [])
        pf.add('eligibility_criteria')
        pf.add('why_stopped')
        meta['patched_fields'] = sorted(pf)
        meta['patched_at'] = datetime.now(_UTC).isoformat()
        data['metadata'] = meta
        ep, wp, miss = stats['elig_patched'], stats['ws_patched'], stats['missing_in_aact']
        print(f'    Patched: {ep:,} elig, {wp:,} ws')
        if miss > 0:
            print(f'    Missing in AACT: {miss:,} NCTs (no eligibility found)')
        if dry_run:
            print(f'    [DRY RUN] Would overwrite {path.name}')
            stats['status'] = 'dry_run'
        else:
            out_name = path.stem + '_backfilled' + path.suffix
            out_path = path.parent / out_name
            print(f'    Saving copy as {out_name} ...')
            with out_path.open('w', encoding='utf-8') as fh:
                json.dump(data, fh, indent=2, sort_keys=False, ensure_ascii=False)
            size_mb = out_path.stat().st_size / (1024 * 1024)
            print(f'    Saved ({size_mb:.1f} MB)')
            stats['status'] = 'patched'
            stats['output_file'] = str(out_path)
    except Exception as e:
        print(f'    ERROR: {e}')
        traceback.print_exc()
        stats['status'] = f'error: {e}'
    return stats


def main():
    parser = argparse.ArgumentParser(description='Backfill eligibility_criteria and why_stopped')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
    args = parser.parse_args()
    W = 60
    print()
    print(f'{"=" * W}')
    print('  ALEXIS SNAPSHOT BACKFILL')
    print('  Fields: eligibility_criteria, why_stopped')
    print(f'  Source: AACT live ({AACT_HOST})')
    if args.dry_run: print('  MODE: DRY RUN')
    print('=' * W)
    files = discover_snapshot_files()
    print()
    print(f'Found {len(files)} JSON files to evaluate')
    conn = connect_aact()
    all_stats, n_skip, n_patch, n_err = [], 0, 0, 0
    try:
        for fp in files:
            stats = patch_file(fp, conn, dry_run=args.dry_run)
            all_stats.append(stats)
            if 'skipped' in stats['status']: n_skip += 1
            elif stats['status'] in ('patched','dry_run'): n_patch += 1
            elif 'error' in stats['status']: n_err += 1
    finally:
        conn.close()
        print()
        print('AACT connection closed.')
    print()
    print(f'{"=" * W}')
    print('  BACKFILL SUMMARY')
    print('=' * W)
    print(f'  Files evaluated:   {len(all_stats)}')
    print(f'  Files patched:     {n_patch}')
    print(f'  Files skipped:     {n_skip}')
    print(f'  Files with errors: {n_err}')
    hdr = f"  {'File':<45s} {'Status':<12s} {'Trials':>7s} {'Elig':>6s} {'WS':>6s} {'Miss':>6s}"
    sep = f"  {'-'*45} {'-'*12} {'-'*7} {'-'*6} {'-'*6} {'-'*6}"
    print()
    print(f'{hdr}')
    print(sep)
    for s in all_stats:
        st = s['status'][:12]
        print(f"  {s['file']:<45s} {st:<12s} {s['trials']:>7,} {s['elig_patched']:>6,} {s['ws_patched']:>6,} {s['missing_in_aact']:>6,}")
    incomplete = [s for s in all_stats if s['missing_in_aact'] > 0 and 'error' not in s['status']]
    if incomplete:
        print()
        print(f'WARNING: Files with incomplete patches:')
        for s in incomplete:
            miss = s['missing_in_aact']
            print(f"    {s['file']}: {miss:,} NCTs missing eligibility")
    print()
    print('Done.')


if __name__ == '__main__':
    main()
