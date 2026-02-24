"""
Validation test for text_modality_policy_v2.py pattern additions.
Run from ALEXIS root: ipython test_text_modality_v2.py

Tests:
  1. Unit tests — known phrases → expected modality
  2. Regression on original patterns — nothing broken
  3. Live scan of base_only small_molecule trials in snapshot
"""
import sys, json, inspect, os
from collections import Counter

sys.path.insert(0, '.')
from policy.text_modality_policy_v2 import text_modality_from_text

# Diagnostic: show which file is actually loaded
import policy.text_modality_policy_v2 as _mod
_loaded_path = os.path.abspath(inspect.getfile(_mod))
print(f"LOADED FROM: {_loaded_path}")
_src = open(_loaded_path).read()
for sig in ['cell_therapy', 'lentiviral', 'radiopharmaceutical', 'oncolytic', 'CAR']:
    print(f"  {'FOUND' if sig in _src else 'MISSING':7} | {sig}")

# ── 1. Unit tests ────────────────────────────────────────────────────────────
UNIT_TESTS = [
    # cell_therapy
    ("CD19 CAR-T cells infusion",                       "cell_therapy"),
    ("Metabolically Armed CD19 CAR-T cell infusion",    "cell_therapy"),
    ("T-reg depleted DLI",                              "cell_therapy"),
    ("NK cell therapy",                                 "cell_therapy"),
    ("KL003 Cell Injection Drug Product",               "cell_therapy"),
    ("TCR-T cell therapy",                              "cell_therapy"),
    ("Donor lymphocyte infusion",                       "cell_therapy"),
    ("Dual-targeting BCMA-CD19 CAR-T cell infusion",    "cell_therapy"),
    # gene_therapy additions
    ("recombinant IL-21 oncolytic vaccinia virus",      "gene_therapy"),
    ("Lentiviral vector transduced CD34+ cells",        "gene_therapy"),  # lentiviral wins over cell
    ("mRNA HBV TCR T-cells",                            "gene_therapy"),
    ("AAV5-hRKp.RPGR gene therapy",                    "gene_therapy"),
    ("intrathecal AAV9 gene transfer",                  "gene_therapy"),
    # radiopharmaceutical
    ("[18F]CSB-321 PET imaging",                        "radiopharmaceutical"),
    ("[177Lu]Lu-PSMA I&T radioligand therapy",          "radiopharmaceutical"),
    ("Ga68-FAPI-46 radiotracer",                        "radiopharmaceutical"),
    ("Gallium-68-labeled FAPI",                         "radiopharmaceutical"),
    ("[11C]UCB-J PET",                                  "radiopharmaceutical"),
    # biologic
    ("Recombinant human surfactant protein D",          "biologic"),
    ("rhBNP recombinant human brain natriuretic",       "biologic"),
    # vaccine
    ("KRAS Neoantigen Nanovaccine",                     "vaccine"),
    ("Vacucis autovaccine Candida",                     "vaccine"),
    ("mRNA vaccine against SARS-CoV-2",                 "vaccine"),       # vaccine before mRNA
    # original patterns still work
    ("anti-PD1 monoclonal antibody treatment",          "monoclonal_antibody"),
    ("bispecific CD3xCD20 antibody",                    "monoclonal_antibody"),
    ("antisense oligonucleotide therapy",               "oligonucleotide"),
    ("CRISPR gene editing",                             "gene_therapy"),
    ("viral vector gene delivery",                      "gene_therapy"),
]

print("=== UNIT TESTS ===")
passed = failed = 0
for text, expected in UNIT_TESTS:
    result = text_modality_from_text(text, "small_molecule")
    ok = result == expected
    if ok:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL  [{expected}] expected, got [{result}]: {text}")

print(f"\n  {passed}/{len(UNIT_TESTS)} passed, {failed} failed")

# ── 2. Live scan — how many base_only small_molecule trials are now fixed ────
print("\n=== LIVE SNAPSHOT SCAN ===")
path = 'storage/snapshots/clinical_trials_v2/reclassified/reclassified_2026_feb_w4.json'
data = json.load(open(path))

base_only_sm = [
    t for t in data['trials']
    if t.get('is_drug_trial')
    and t.get('modality') == 'small_molecule'
    and not t.get('intervention_meshes')
]
print(f"base_only small_molecule trials: {len(base_only_sm)}")

reclassified = Counter()
for t in base_only_sm:
    txt = " ".join((t.get('interventions_text') or []) + [t.get('title') or ''])
    new_mod = text_modality_from_text(txt, 'small_molecule')
    if new_mod and new_mod != 'small_molecule':
        reclassified[new_mod] += 1

print("\nTrials that would now be reclassified:")
for mod, count in reclassified.most_common():
    print(f"  {mod:25} | {count}")
print(f"\nTotal newly classifiable: {sum(reclassified.values())}")
print(f"Remaining small_molecule (correct or unclear): {len(base_only_sm) - sum(reclassified.values())}")

# ── 3. False positive check — only matters for base_only (no mesh) trials ────
# Text matcher only runs in production when mesh is absent. Testing it against
# mesh-assigned trials is misleading — those won't reach step 3 in the pipeline.
print("\n=== FALSE POSITIVE CHECK (base_only trials only) ===")
print("NOTE: biologic→cell_therapy is EXPECTED — CAR-T trials often tagged as BIOLOGICAL by sponsors.")
print("      Flag only nonsensical flips (e.g. radiopharmaceutical→cell_therapy).\n")
for mod in ['cell_therapy', 'gene_therapy', 'radiopharmaceutical', 'biologic']:
    base_only_mod = [
        t for t in data['trials']
        if t.get('is_drug_trial')
        and t.get('modality') == mod
        and not t.get('intervention_meshes')
    ]
    wrong = []
    for t in base_only_mod[:200]:
        txt = " ".join((t.get('interventions_text') or []) + [t.get('title') or ''])
        new_mod = text_modality_from_text(txt, mod)
        if new_mod != mod:
            wrong.append((t['nct_id'], new_mod, (t.get('interventions_text') or ['?'])[0][:50]))
    if wrong:
        print(f"\n  {mod} → unexpected ({len(wrong)} of {min(200,len(base_only_mod))}):")
        for nct, nm, iv in wrong[:5]:
            print(f"    {nct} → {nm} | {iv}")
    else:
        print(f"  {mod}: OK ({min(200,len(base_only_mod))} base_only trials, no unexpected reclassifications)")
