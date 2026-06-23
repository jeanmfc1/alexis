
# pipelines/classify_anzctr_to_snapshot.py
'''
Classify ANZCTR trials and produce an ALEXIS-compatible snapshot JSON.

Reads storage/anzctr_flat.parquet (built by ingest_anzctr_xlsx.py), runs
intl_drug_classifier_v2 + intl_ta_classifier, and writes a snapshot that
diff_anzctr_snapshots.py and the aw* analytics can consume.

Input:   storage/anzctr_flat.parquet         (or --input)
Model:   classifiers/intl_drug_classifier_v2.pkl
Output:  storage/snapshots/clinical_trials_v2/anzctr/YYYY-MM-DD_anzctr_v1.json

Usage:
    PYTHONPATH=. python pipelines/classify_anzctr_to_snapshot.py
    PYTHONPATH=. python pipelines/classify_anzctr_to_snapshot.py --force
'''

from __future__ import annotations
import argparse, json, pickle, re, time, warnings
from datetime import date, datetime
from pathlib import Path
from typing import Optional

warnings.filterwarnings('ignore', message='.*InconsistentVersionWarning.*')
try:
    from sklearn.exceptions import InconsistentVersionWarning
    warnings.filterwarnings('ignore', category=InconsistentVersionWarning)
except ImportError:
    pass

import numpy as np
import pandas as pd

from storage.models_v2 import ClinicalTrialSignalV2

REGISTRY   = 'ANZCTR'
SOURCE_TAG = 'anzctr'

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

GENE_THERAPY_RE = re.compile(
    r'aav\d*|lentiviral|retroviral|gene editing|crispr|'
    r'cas9|in vivo gene|ex vivo gene|viral vector|'
    r'adeno.associated|onasemnogene|zolgensma|'
    r'gene transfer|gene correction|gene therap',
    re.IGNORECASE,
)
RADIOPHARMA_IV_RE = re.compile(
    r'\d+[cCfF]|68ga|18f|177lu|89zr|64cu|'
    r'lutetium|gallium|florbetapir|flutemetamol|psma',
    re.IGNORECASE,
)
BIOLOGIC_MIN_CONF = 0.75


def _norm_phase(raw):
    if not raw or str(raw).lower() in ('nan', 'none', ''):
        return 'NA'
    return _PHASE_MAP.get(str(raw).strip().lower(), 'NA')

def _norm_status(raw):
    if not raw or str(raw).lower() in ('nan', 'none', ''):
        return None
    return _STATUS_MAP.get(str(raw).strip().lower(), str(raw).strip().upper().replace(' ', '_'))

def _norm_study_type(raw):
    if not raw:
        return 'OTHER'
    r = str(raw).strip().upper()
    if 'INTERVENTIONAL' in r:
        return 'INTERVENTIONAL'
    if 'OBSERVATIONAL' in r:
        return 'OBSERVATIONAL'
    return 'OTHER'

def _norm_sponsor_class(sponsor_type, funding_source, sponsor_name):
    blob = ' '.join(filter(None, [sponsor_type, funding_source, sponsor_name]))
    key = blob.strip().lower()
    if 'commercial sector/industry' in key:
        return 'INDUSTRY'
    if 'government' in key:
        return 'OTHER_GOV'
    if any(k in key for k in ('university', 'hospital', 'institute', 'college')):
        return 'OTHER'
    return 'OTHER'

def _parse_conditions(raw):
    if not raw or str(raw).lower() in ('nan', 'none', ''):
        return []
    s = str(raw)
    if ';' in s:
        return [p.strip() for p in s.split(';') if p.strip()]
    if ',' in s:
        return [p.strip() for p in s.split(',') if p.strip()]
    return [s.strip()]

def _parse_interventions(interventions_raw, medicine_detail=None):
    results = []
    if interventions_raw and str(interventions_raw).lower() not in ('nan', 'none', ''):
        for arm in str(interventions_raw).split('|'):
            arm = arm.strip()
            if arm and arm.lower() not in ('nan', 'none', ''):
                if ':' in arm:
                    arm = arm.split(':', 1)[1].strip()
                if arm:
                    results.append(arm)
    return results

def build_clf_text(row):
    parts = [
        row.get('title_detail') or '',
        row.get('objectives') or '',
        row.get('interventions_raw') or '',
        row.get('target_disease') or '',
        row.get('medicine_detail') or '',
    ]
    return ' '.join(p for p in parts if p).strip()

def build_iv_text(row):
    return ' '.join(filter(None, [
        row.get('interventions_raw') or '',
        row.get('medicine_detail') or '',
    ]))

def apply_overrides(pred, conf, text, iv_text):
    override = None
    flagged  = False
    if pred in ('biologic', 'non_drug') and GENE_THERAPY_RE.search(text):
        override = 'gene_therapy'
    elif pred == 'radiopharmaceutical' and not RADIOPHARMA_IV_RE.search(iv_text):
        override = 'non_drug'
    elif pred == 'biologic' and conf < BIOLOGIC_MIN_CONF:
        flagged = True
    return override or pred, override, flagged


def row_to_dict(row, modality, conf, override, flagged, ta_pred=None):
    is_drug    = modality != 'non_drug'
    iv_texts   = _parse_interventions(row.get('interventions_raw'), row.get('medicine_detail'))
    conditions = _parse_conditions(row.get('target_disease'))

    NON_DISEASE_TA = 'Non-disease drug study'
    UNASSIGNED_TA  = 'Unassigned drug study'

    if not is_drug or ta_pred is None:
        therapeutic_area = None
        study_intent     = None
        study_category   = None
        study_category_evidence = []
        ta_detected = []
    elif ta_pred == NON_DISEASE_TA:
        therapeutic_area = NON_DISEASE_TA
        study_intent     = 'non_disease'
        ta_detected      = [NON_DISEASE_TA]
        from analytics.summary_v2 import assign_non_disease_study_category
        _title = row.get('title_detail') or ''
        _ivs   = ' '.join(iv_texts)
        _cached = f'{_ivs} {_title}'.lower()
        _conds = conditions
        class _FT:
            interventions_text          = iv_texts
            title                       = _title
            conditions                  = _conds
            _cached_title_interventions = _cached
        study_category, study_category_evidence = assign_non_disease_study_category(_FT())
    elif ta_pred == UNASSIGNED_TA:
        therapeutic_area = UNASSIGNED_TA
        study_intent     = None
        study_category   = None
        study_category_evidence = []
        ta_detected = [UNASSIGNED_TA]
    else:
        therapeutic_area = ta_pred
        study_intent     = 'disease'
        study_category   = None
        study_category_evidence = []
        ta_detected = [ta_pred]

    flags = ['anzctr_no_mesh']
    if flagged:
        flags.append('low_confidence_biologic')
    if override:
        flags.append(f'override:{override}')

    prim_country  = row.get('primary_sponsor_country')
    is_foreign    = row.get('is_foreign_sponsored', False)
    if isinstance(is_foreign, str):
        is_foreign = is_foreign.lower() in ('true', '1', 'yes')

    overall_status = _norm_status(row.get('recruitment_status'))

    return {
        'nct_id':                     row.get('proj_id') or row.get('actrn'),
        'title':                      row.get('title_detail'),
        'brief_summary':              row.get('objectives'),
        'detailed_description':       None,
        'registry':                   REGISTRY,
        'source_url':                 row.get('source_url'),
        'study_type':                 _norm_study_type(row.get('study_type')),
        'phase':                      _norm_phase(row.get('phase')),
        'sponsor_class':              _norm_sponsor_class(
                                          row.get('primary_sponsor_type'),
                                          row.get('funding_source'),
                                          row.get('primary_sponsor')),
        'sponsor_name':               row.get('primary_sponsor'),
        'primary_sponsor_country':    prim_country,
        'is_foreign_sponsored':       bool(is_foreign),
        'recruitment_status':         row.get('recruitment_status'),
        'overall_status':             overall_status,
        'conditions':                 conditions,
        'enrollment':                 None,
        'enrollment_type':            None,
        'why_stopped':                row.get('why_stopped'),
        'start_date':                 row.get('study_start'),
        'completion_date':            row.get('study_end'),
        'primary_completion_date':    None,
        'first_posted_date':          row.get('registration_date') or row.get('reg_date'),
        'last_update_posted_date':    None,
        'primary_outcomes':           [],
        'secondary_outcomes':         [],
        'facilities':                 [],
        'facility_count':             0,
        'interventions':              [],
        'interventions_text':         iv_texts,
        'interventions_all':          [],
        'arm_group_map':              {},
        'intervention_meshes':        [],
        'intervention_mesh_ancestors':[],
        'condition_meshes':           [],
        'condition_mesh_ancestors':   [],
        'therapeutic_area':           therapeutic_area,
        'therapeutic_areas_detected': ta_detected,
        'is_drug_trial':              is_drug,
        'modality':                   modality if is_drug else None,
        'modality_source':            'intl_classifier',
        'info_flags':                 flags,
        'study_intent':               study_intent,
        'study_category':             study_category,
        'study_category_evidence':    study_category_evidence,
        'mesh_missing_condition':     True,
        'update_type':                None,
        'update_categories':          [],
        'linked_from':                None,
        'outcome':                    None,
    }


def main():
    from core.paths import storage_dir, models_dir, snapshots_dir
    parser = argparse.ArgumentParser()
    parser.add_argument('--input',    default=str(storage_dir() / 'anzctr_flat.parquet'))
    parser.add_argument('--model',    default=str(models_dir() / 'intl_drug_classifier_v2.pkl'))
    parser.add_argument('--ta-model', default=str(models_dir() / 'intl_ta_classifier.pkl'))
    parser.add_argument('--out-dir',  default=str(snapshots_dir() / 'anzctr'))
    parser.add_argument('--force',    action='store_true')
    args = parser.parse_args()

    input_path = Path(args.input)
    model_path = Path(args.model)
    out_dir    = Path(args.out_dir)
    today      = date.today().isoformat()
    out_path   = out_dir / f'{today}_anzctr_v1.json'

    W = 60
    print('=' * W)
    print('  ALEXIS -- ANZCTR Classify -> Snapshot')
    print('=' * W)
    print(f'  Input:    {input_path}')
    print(f'  Model:    {model_path}')
    print(f'  Out:      {out_path}')

    if out_path.exists() and not args.force:
        print(f'  Snapshot already exists. Use --force to overwrite.')
        return

    if not input_path.exists():
        raise FileNotFoundError(f'Run ingest_anzctr_xlsx.py first: {input_path}')

    df = pd.read_parquet(input_path)
    print(f'  Loaded {len(df):,} trials')

    print(f'  Loading model from {model_path} ...')
    with open(model_path, 'rb') as f:
        clf = pickle.load(f)
    vectorizer = clf['vectorizer']
    model      = clf['model']
    classes    = clf['classes']

    ta_model = ta_classes = None
    ta_path  = Path(args.ta_model)
    if ta_path.exists():
        with open(ta_path, 'rb') as f:
            ta_clf = pickle.load(f)
        ta_model   = ta_clf['model']
        ta_classes = ta_clf['classes']
        print(f'  TA classes: {len(ta_classes)}')

    texts    = [build_clf_text(r) for _, r in df.iterrows()]
    iv_texts = [build_iv_text(r)  for _, r in df.iterrows()]

    print(f'  Vectorizing {len(texts):,} trials ...')
    t0 = time.time()
    X  = vectorizer.transform(texts)
    print(f'  Done in {time.time()-t0:.1f}s')

    probs    = model.predict_proba(X)
    pred_idx = np.argmax(probs, axis=1)
    preds    = [classes[i] for i in pred_idx]
    confs    = probs[np.arange(len(texts)), pred_idx].tolist()

    final_preds, overrides, flagged_list = [], [], []
    for txt, ivt, pred, conf in zip(texts, iv_texts, preds, confs):
        fp, ov, fl = apply_overrides(pred, conf, txt, ivt)
        final_preds.append(fp)
        overrides.append(ov)
        flagged_list.append(fl)

    ta_preds = [None] * len(df)
    if ta_model is not None:
        drug_indices = [i for i, p in enumerate(final_preds) if p != 'non_drug']
        if drug_indices:
            X_drug = vectorizer.transform([texts[i] for i in drug_indices])
            ta_probs    = ta_model.predict_proba(X_drug)
            ta_pred_idx = np.argmax(ta_probs, axis=1)
            for j, idx in enumerate(drug_indices):
                ta_preds[idx] = ta_classes[ta_pred_idx[j]]

    print(f'  Building {len(df):,} trial dicts ...')
    trial_dicts = []
    for i, (_, row) in enumerate(df.iterrows()):
        d = row_to_dict(row.to_dict(), final_preds[i], confs[i],
                        overrides[i], flagged_list[i], ta_preds[i])
        trial_dicts.append(d)
        if (i+1) % 500 == 0 or (i+1) == len(df):
            pct = (i+1) / len(df)
            bar = '|' * int(20*pct) + '.' * (20 - int(20*pct))
            print(f'  [{bar}] {i+1:,}/{len(df):,}', end='\r', flush=True)
    print()

    drug_n   = sum(1 for d in trial_dicts if d.get('is_drug_trial'))
    foreign_n = sum(1 for d in trial_dicts if d.get('is_foreign_sponsored'))
    print(f'  Drug trials:       {drug_n:,}')
    print(f'  Foreign-sponsored: {foreign_n:,}')

    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {
        'metadata': {
            'source':       REGISTRY,
            'registry':     REGISTRY,
            'as_of':        today,
            'window_start': None,
            'window_end':   today,
            'total_trials': len(trial_dicts),
            'drug_trials':  drug_n,
            'generated_at': datetime.now().isoformat(),
            'classifier':   'intl_drug_classifier_v2',
            'input_file':   str(input_path),
        },
        'trials':  trial_dicts,
        'summary': {},
    }
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, default=str)

    size_mb = out_path.stat().st_size / 1e6
    print(f'  Saved -> {out_path}  ({size_mb:.1f} MB, {len(trial_dicts):,} trials)')

if __name__ == '__main__':
    main()
