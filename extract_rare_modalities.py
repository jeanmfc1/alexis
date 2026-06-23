import ijson, pandas as pd, sys, re
from pathlib import Path

TARGET = {'gene_therapy', 'radiopharmaceutical'}
base = Path('storage/snapshots/clinical_trials_v2/active_universe')
files = [
    'master_DB_2025_Q4.json',
    'master_DB_2025_Q3.json',
    'master_DB_2024_Q4.json',
    'master_DB_2023_Q4.json',
    'master_DB_2022_Q4.json',
    'master_DB_2021_Q4.json',
    'master_DB_2020_Q4.json',
    'master_DB_2019_Q4.json',
]
seen = {}

def get_total_trials(path):
    with path.open('r', encoding='utf-8') as f:
        head = f.read(20000)
    m = re.search(r'"drug_trials_total":\s*(\d+)', head)
    return int(m.group(1)) if m else 0

for fname in files:
    path = base / fname
    file_size = path.stat().st_size
    total = get_total_trials(path)
    added = 0
    trials_seen = 0
    print(f'\n{fname} ({file_size/1024**2:.0f} MB, {total:,} drug trials)')

    with path.open('rb') as f:
        for trial in ijson.items(f, 'trials.item'):
            trials_seen += 1
            nct = trial.get('nct_id')
            if nct and trial.get('modality') in TARGET and nct not in seen:
                seen[nct] = {
                    'nct_id':                nct,
                    'title':                 trial.get('title'),
                    'study_type':            trial.get('study_type'),
                    'phase':                 trial.get('phase'),
                    'conditions_text':       ' | '.join(trial.get('conditions') or []),
                    'interventions_text':    ' | '.join(trial.get('interventions_text') or []),
                    'is_drug_trial':         True,
                    'modality':              trial.get('modality'),
                    'modality_source':       'mesh_tree',
                    'mesh_derived_modality': True,
                    'therapeutic_area':      trial.get('therapeutic_area'),
                    'ta_provenance':         'mesh',
                    'has_condition_mesh':    bool(trial.get('condition_meshes')),
                    'has_intv_mesh':         bool(trial.get('intervention_meshes')),
                }
                added += 1

            pct = trials_seen / total if total else 0
            filled = int(30 * pct)
            bar = '█' * filled + '░' * (30 - filled)
            sys.stdout.write(
                f'\r  [{bar}] {trials_seen:,}/{total:,}  '
                f'found={added}  unique={len(seen):,}'
            )
            sys.stdout.flush()

    print(f'\r  [██████████████████████████████] {trials_seen:,}/{total:,}  '
          f'found={added}  unique={len(seen):,}  done')

print(f'\n\nFinal unique: {len(seen):,}')
df = pd.DataFrame(seen.values())
print(df['modality'].value_counts().to_string())

# Save under the configured data dir (was a hardcoded /mnt/c/ALEXIS_eval path)
from core.paths import data_root, ensure_dir
out = ensure_dir(data_root() / 'eval') / 'rare_modalities_raw.parquet'
df.to_parquet(out, index=False)
print(f'\nSaved {len(df):,} records → {out}')
print('Now run the merge on Windows PowerShell.')
