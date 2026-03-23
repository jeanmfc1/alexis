# ALEXIS Handoff 2 — Modality and TA Analysis
## Use after Task 2 finishes running with evidence fields confirmed

---

## Who and what

**Jean** works at IQVIA building **ALEXIS** (Automated Lexicon-based Clinical Intelligence System), a clinical trial classification pipeline processing ClinicalTrials.gov/AACT data to assign therapeutic areas, drug modalities, and biomarker relevance to 38,977 active drug/interventional trials from the Q4 2025 universe.

This session compares ALEXIS's rule-based modality and TA classifications against an independent LLM evaluation (Haiku) to identify systematic misclassifications and improve the pipeline.

---

## Environment

- **OS**: Windows with WSL2 (Ubuntu)
- **Editor**: VS Code connected to WSL
- **ALEXIS project root (WSL)**: `/home/jeanmfc/projects/ALEXIS/`
- **ALEXIS project root (Windows UNC)**: `\\wsl.localhost\Ubuntu\home\jeanmfc\projects\ALEXIS\`
- **Python**: runs in WSL for ALEXIS pipeline work
- **Eval files**: live on Windows at `C:\ALEXIS_eval\` (accessible from WSL as `/mnt/c/ALEXIS_eval/`)
- **GitHub**: ALEXIS is version controlled, commit changes after updates

---

## File locations

| File | Path |
|---|---|
| LLM modality/TA results | `C:\ALEXIS_eval\llm_modality_ta_eval_Q4.json` |
| LLM task 2 cache | `C:\ALEXIS_eval\cache_task2.json` |
| LLM task 2 summary | `C:\ALEXIS_eval\llm_eval_summary_task2.json` |
| Evidence not found (generated in Step 0) | `C:\ALEXIS_eval\evidence_not_found_task2.json` |
| Batch files (raw trial text) | `C:\ALEXIS_eval\batches\batch_*.json` (1,949 files, 20 trials each, dict of {nct_id: trial_text}) |
| Master DB (ALEXIS Q4 2025 patched) | `\\wsl.localhost\Ubuntu\home\jeanmfc\projects\ALEXIS\storage\snapshots\clinical_trials_v2\active_universe\master_DB_2025_Q4_patched.json` |
| ALEXIS modality/TA pipeline | `\\wsl.localhost\Ubuntu\home\jeanmfc\projects\ALEXIS\pipelines\` |
| Biomarker policy (for reference) | `\\wsl.localhost\Ubuntu\home\jeanmfc\projects\ALEXIS\policy\biomarker_policy.py` |

---

## IMPORTANT — verify Task 2 ran with evidence fields before anything else

Task 2 was run multiple times during development. The final version includes `modality_evidence` and `ta_evidence` direct quote fields. An earlier version without these fields also ran and may have populated the cache. Verify before proceeding:

```python
import json

cache = json.load(open(r"C:\ALEXIS_eval\cache_task2.json", encoding="utf-8"))
valid = {k: v for k, v in cache.items() if "error" not in v}
sample = next(iter(valid.values()))
print("Keys present:", list(sample.keys()))
print()
print("Has modality_evidence:", "modality_evidence" in sample)
print("Has ta_evidence:", "ta_evidence" in sample)
print()
# Show a sample entry
import json
print(json.dumps(sample, indent=2)[:500])
```

If `modality_evidence` and `ta_evidence` are missing, the old version ran. Do not proceed — rerun with the updated `run_task2.py` (Claude Code, OAuth token, uses `CLAUDE_CODE_OAUTH_TOKEN`).

---

## LLM evaluation schema (Task 2 — final version)

Each trial in `llm_modality_ta_eval_Q4.json`:

```json
{
  "nct_id": "NCT...",
  "modality": "small_molecule",
  "modality_evidence": "exact phrase copied verbatim from trial text",
  "therapeutic_areas": ["Oncology"],
  "ta_evidence": "exact phrase copied verbatim from trial text",
  "confidence": "high|medium|low",
  "modality_reasoning": "1 sentence",
  "ta_reasoning": "1 sentence"
}
```

Key differences from ALEXIS:
- LLM may assign **multiple** therapeutic areas — ALEXIS assigns only one
- LLM provides evidence quotes and reasoning for auditability
- LLM classified from raw trial text (title, summary, description, interventions, MeSH terms, conditions, outcomes, eligibility) — not from ALEXIS's existing fields

---

## ALEXIS master DB structure (relevant fields)

Each trial in `master_DB_2025_Q4_patched.json` under the `trials` key:

```json
{
  "nct_id": "NCT...",
  "modality": "small_molecule",
  "therapeutic_area": "Oncology",
  "biomarker_relevant": true,
  "biomarker_confidence": "high",
  "biomarker_reason": "\"HER2\" (HER2) in trial text",
  "biomarker_targets": [...],
  "pk_only": false,
  "title": "...",
  "phase": "PHASE3",
  ...
}
```

ALEXIS modality and TA are assigned by the rules-based pipeline using MeSH terms, intervention names, and keyword patterns.

---

## Modality vocabulary (shared between ALEXIS and LLM)

| Value | Definition |
|---|---|
| small_molecule | Small organic molecule drug |
| monoclonal_antibody | Naked mAb, bispecific antibody |
| biologic | Protein therapeutic, enzyme, cytokine, fusion protein — NOT mAb, NOT ADC |
| adc | Antibody-drug conjugate |
| cell_therapy | CAR-T, TCR-T, NK cell, dendritic cell, stem cell therapy |
| gene_therapy | Viral vector, CRISPR, gene editing, gene correction |
| oligonucleotide | siRNA, antisense, mRNA, aptamer |
| vaccine | Prophylactic or therapeutic vaccine |
| radiopharmaceutical | Radiolabeled compound for therapy or imaging |
| combination | Fixed combination of two distinct modality classes |
| other | Does not fit any above |

---

## TA vocabulary (shared between ALEXIS and LLM)

Oncology, Infectious Disease, Immunology / Inflammation, Cardiovascular, Neurology / CNS, Metabolic / Endocrine, Rare / Genetic, Respiratory, Gastrointestinal / Hepatic, Musculoskeletal, Dermatology, Hematology, Ophthalmology, Psychiatry, Urology, Non-disease drug study, Other

Note: **Non-disease drug study** = BABE, PK/PD, drug-drug interaction, healthy volunteer studies.

---

## LLM evaluation quality context

- **Overall accuracy**: ~80% on 20-trial spot check vs manual review (biomarker task; modality/TA expected similar)
- **GPT-5 comparison**: GPT-5 was tested on the same 20 trials and performed worse — it hallucinated biomarker endpoints by inferring from trial type rather than reading text. Haiku with mandatory evidence fields is more grounded.
- **Evidence field purpose**: forces Haiku to quote a real phrase from the trial text rather than infer from domain knowledge. If the quoted phrase actually appears in the trial text, the classification is grounded. If not, it may be hallucinated.
- **Known LLM biases for modality/TA**:
  - May assign `combination` when ALEXIS assigns a single modality — LLM is more likely to notice fixed-dose combinations
  - May assign multiple TAs when ALEXIS assigns one — not necessarily wrong
  - `biologic` vs `monoclonal_antibody` boundary is sometimes inconsistent
  - `oligonucleotide` vs `gene_therapy` for mRNA-based therapies

---

## Step 0 — Verify evidence text actually appears in raw trial text (do this first)

This is the most important step. For each trial, check that the `modality_evidence` and `ta_evidence` strings from the LLM output are literally present (substring match) in the raw trial text from the batch files. This confirms Haiku read the actual text rather than generating plausible-sounding but fabricated quotes.

```python
import json, glob

# Step 1: Build index of raw trial texts from batch files
print("Building batch index from raw trial texts...")
batch_index = {}
for bf in sorted(glob.glob(r"C:\ALEXIS_eval\batches\batch_*.json")):
    batch = json.load(open(bf, encoding="utf-8"))
    batch_index.update(batch)
print(f"Indexed {len(batch_index)} trials from batch files")

# Step 2: Load LLM Task 2 results
llm_results = json.load(open(r"C:\ALEXIS_eval\llm_modality_ta_eval_Q4.json", encoding="utf-8"))
llm = {r["nct_id"]: r for r in llm_results}
print(f"Loaded {len(llm)} LLM Task 2 results")

# Step 3: Check every evidence quote against raw trial text
mod_found     = 0
mod_not_found = 0
ta_found      = 0
ta_not_found  = 0
empty         = 0
not_found_list = []

for nct_id, r in llm.items():
    raw_text = batch_index.get(nct_id, "").lower()

    # Check modality_evidence
    mod_ev = r.get("modality_evidence", "").strip()
    if not mod_ev or len(mod_ev) < 10:
        empty += 1
    elif mod_ev.lower() in raw_text:
        mod_found += 1
    else:
        mod_not_found += 1
        not_found_list.append({
            "nct_id":   nct_id,
            "field":    "modality_evidence",
            "modality": r.get("modality"),
            "evidence": mod_ev,
            "reasoning": r.get("modality_reasoning", "")
        })

    # Check ta_evidence
    ta_ev = r.get("ta_evidence", "").strip()
    if not ta_ev or len(ta_ev) < 10:
        empty += 1
    elif ta_ev.lower() in raw_text:
        ta_found += 1
    else:
        ta_not_found += 1
        not_found_list.append({
            "nct_id":   nct_id,
            "field":    "ta_evidence",
            "ta":       r.get("therapeutic_areas"),
            "evidence": ta_ev,
            "reasoning": r.get("ta_reasoning", "")
        })

mod_total = mod_found + mod_not_found
ta_total  = ta_found + ta_not_found

print(f"\nEvidence verification — modality:")
print(f"  Found in raw trial text:    {mod_found}/{mod_total} ({mod_found/mod_total*100:.1f}%)")
print(f"  NOT found in raw text:      {mod_not_found}/{mod_total} ({mod_not_found/mod_total*100:.1f}%)")
print(f"\nEvidence verification — therapeutic area:")
print(f"  Found in raw trial text:    {ta_found}/{ta_total} ({ta_found/ta_total*100:.1f}%)")
print(f"  NOT found in raw text:      {ta_not_found}/{ta_total} ({ta_not_found/ta_total*100:.1f}%)")
print(f"\nEmpty/too short (skipped):    {empty}")

# Show first 10 failures
failures = [x for x in not_found_list]
print(f"\nFirst 10 evidence quotes NOT found in raw trial text:")
for ex in failures[:10]:
    print(f"  {ex['nct_id']} | {ex['field']}")
    print(f"    Evidence: '{ex['evidence']}'")
    print(f"    Reasoning: '{ex.get('reasoning', '')}'")
    print()

# Save full not-found list
with open(r"C:\ALEXIS_eval\evidence_not_found_task2.json", "w", encoding="utf-8") as f:
    json.dump(not_found_list, f, indent=1, ensure_ascii=False)
print(f"Full not-found list ({len(not_found_list)} entries) saved to:")
print(r"  C:\ALEXIS_eval\evidence_not_found_task2.json")
```

**Interpretation:**
- **>85% found** → evidence is real, proceed with full analysis
- **60–85% found** → partial hallucination. Use evidence as indicative but not definitive. Flag disagreements where evidence is not found before trusting LLM classification.
- **<60% found** → significant hallucination. Do not use Task 2 results. Rerun `run_task2.py` with the evidence version.

**If evidence rate is low**, check the cache keys first (see IMPORTANT section above). The old version of `run_task2.py` without evidence fields may have run.

---

## Step 1 — Load and align both datasets

```python
import json

# Load master DB
print("Loading master DB...")
master_raw = json.load(open(
    r"\\wsl.localhost\Ubuntu\home\jeanmfc\projects\ALEXIS\storage\snapshots\clinical_trials_v2\active_universe\master_DB_2025_Q4_patched.json",
    encoding="utf-8", errors="replace"
))
alexis = {t["nct_id"]: t for t in master_raw["trials"]}
print(f"ALEXIS: {len(alexis)} trials")

# Load LLM Task 2 results
llm_results = json.load(open(r"C:\ALEXIS_eval\llm_modality_ta_eval_Q4.json", encoding="utf-8"))
llm = {r["nct_id"]: r for r in llm_results}
print(f"LLM Task 2: {len(llm)} trials")

# Align
both = {nct_id for nct_id in alexis if nct_id in llm}
print(f"In both: {len(both)}")

# Compute agreements
mod_agree    = 0
mod_disagree = 0
ta_agree     = 0
ta_disagree  = 0

for nct_id in both:
    a = alexis[nct_id]
    l = llm[nct_id]

    if l.get("modality") == a.get("modality"):
        mod_agree += 1
    else:
        mod_disagree += 1

    # TA: ALEXIS assigns one, LLM may assign multiple
    # Agreement = ALEXIS TA appears anywhere in LLM therapeutic_areas list
    alexis_ta = a.get("therapeutic_area", "")
    llm_tas   = l.get("therapeutic_areas", [])
    if alexis_ta in llm_tas:
        ta_agree += 1
    else:
        ta_disagree += 1

print(f"\nModality: {mod_agree} agree ({mod_agree/len(both)*100:.1f}%), {mod_disagree} disagree")
print(f"TA:       {ta_agree} agree ({ta_agree/len(both)*100:.1f}%), {ta_disagree} disagree")
```

---

## Step 2 — Modality disagreement analysis

```python
from collections import Counter

mod_pairs = Counter()
mod_disagree_trials = []

for nct_id in both:
    a_mod = alexis[nct_id].get("modality", "unknown")
    l_mod = llm[nct_id].get("modality", "unknown")
    if a_mod != l_mod:
        mod_pairs[(a_mod, l_mod)] += 1
        mod_disagree_trials.append({
            "nct_id":           nct_id,
            "alexis_modality":  a_mod,
            "llm_modality":     l_mod,
            "confidence":       llm[nct_id].get("confidence"),
            "modality_evidence":llm[nct_id].get("modality_evidence", ""),
            "modality_reasoning":llm[nct_id].get("modality_reasoning", ""),
            "title":            alexis[nct_id].get("title", "")
        })

print("Top modality disagreement pairs (ALEXIS → LLM):")
for (a, l), count in mod_pairs.most_common(20):
    print(f"  {a:25} → {l:25} : {count}")
```

For each major disagreement pair, read 5-10 examples. Check whether the `modality_evidence` quote actually appears in the batch file text (from Step 0 index). Decide if ALEXIS or LLM is correct.

**Known boundary cases to watch:**
- `biologic` vs `monoclonal_antibody` — ALEXIS may misclassify naked mAbs as biologic
- `combination` vs single modality — LLM catches fixed-dose combinations more reliably
- `oligonucleotide` vs `gene_therapy` — mRNA therapies and viral vectors sometimes confused
- `adc` vs `monoclonal_antibody` — ADC payload sometimes not recognized by ALEXIS MeSH patterns
- `biologic` vs `vaccine` — protein subunit vaccines sometimes called biologic

---

## Step 3 — TA disagreement analysis

TA comparison is asymmetric — LLM can assign multiple TAs, ALEXIS assigns only one.

```python
ta_pairs = Counter()
ta_disagree_trials = []
multi_ta_trials = []

for nct_id in both:
    a_ta   = alexis[nct_id].get("therapeutic_area", "unknown")
    l_tas  = llm[nct_id].get("therapeutic_areas", [])
    l_primary = l_tas[0] if l_tas else "unknown"

    if len(l_tas) > 1:
        multi_ta_trials.append({
            "nct_id":  nct_id,
            "alexis_ta": a_ta,
            "llm_tas": l_tas,
            "ta_evidence": llm[nct_id].get("ta_evidence", ""),
            "ta_reasoning": llm[nct_id].get("ta_reasoning", ""),
            "title": alexis[nct_id].get("title", "")
        })

    if a_ta not in l_tas:
        ta_pairs[(a_ta, l_primary)] += 1
        ta_disagree_trials.append({
            "nct_id":       nct_id,
            "alexis_ta":    a_ta,
            "llm_tas":      l_tas,
            "confidence":   llm[nct_id].get("confidence"),
            "ta_evidence":  llm[nct_id].get("ta_evidence", ""),
            "ta_reasoning": llm[nct_id].get("ta_reasoning", ""),
            "title":        alexis[nct_id].get("title", "")
        })

print(f"Multi-TA trials (LLM assigned 2+): {len(multi_ta_trials)}")
print(f"TA hard disagreements:             {len(ta_disagree_trials)}")
print()
print("Top TA disagreement pairs (ALEXIS → LLM primary):")
for (a, l), count in ta_pairs.most_common(20):
    print(f"  {a:35} → {l:35} : {count}")
```

**Three disagreement types:**
1. **Hard disagreement** — ALEXIS TA not anywhere in LLM's therapeutic_areas list → likely ALEXIS error
2. **Multi-TA miss** — LLM assigned 2+ TAs, ALEXIS only got one → ALEXIS may be too narrow
3. **LLM overcall** — LLM added a TA not supported by the ta_evidence quote → LLM error

Focus on hard disagreements first. Always verify ta_evidence appears in the raw batch text before trusting LLM.

---

## Step 4 — Multi-TA analysis

```python
from collections import Counter

# Most common multi-TA combinations
combo_counts = Counter()
for t in multi_ta_trials:
    combo = tuple(sorted(t["llm_tas"]))
    combo_counts[combo] += 1

print(f"Total multi-TA trials: {len(multi_ta_trials)}")
print()
print("Most common TA combinations (LLM):")
for combo, count in combo_counts.most_common(20):
    print(f"  {count:5} × {' + '.join(combo)}")
```

Common legitimate multi-TA patterns to expect:
- Oncology + Rare / Genetic (rare pediatric cancers, hereditary tumor syndromes)
- Oncology + Hematology (leukemia, lymphoma)
- Infectious Disease + Immunology / Inflammation (HIV immune studies)
- Metabolic / Endocrine + Cardiovascular (diabetes with CV endpoints)
- Immunology / Inflammation + Dermatology (atopic dermatitis, psoriasis)

**Decision needed**: should ALEXIS support multi-TA assignments going forward? Currently it assigns one. If yes, the pipeline needs updating to output a list.

---

## Step 5 — Spot-check disagreements against raw trial text

For any disagreement where you're not sure whether ALEXIS or LLM is correct, read the raw trial text:

```python
# batch_index must already be built from Step 0
nct_id = "NCT..."
print(batch_index.get(nct_id, "NOT FOUND"))
```

Also check if the evidence quote actually appears:
```python
evidence = llm[nct_id].get("modality_evidence", "")
raw = batch_index.get(nct_id, "")
print(f"Evidence found in text: {evidence.lower() in raw.lower()}")
print(f"Evidence: '{evidence}'")
```

---

## Step 6 — Update ALEXIS pipeline

After identifying systematic patterns:

1. Fix modality classification rules in the relevant pipeline script
2. Fix TA classification rules
3. Decide whether to add multi-TA support
4. Rerun the full pipeline against `master_DB_2025_Q4_patched.json`
5. Commit to GitHub: `git commit -m "modality/TA pipeline: v2 — LLM evaluation improvements Q4 2025"`

---

## LLM Task 2 final stats

Check the actual summary file after run completes:

```python
import json
s = json.load(open(r"C:\ALEXIS_eval\llm_eval_summary_task2.json"))
print(json.dumps(s, indent=2))
```

Expected fields:
- `total_evaluated` — should be ~38,977
- `valid` — should be ~38,977 after final clean run
- `errors` — should be 0 or very low after final run
- `modality_distribution` — breakdown by modality
- `ta_distribution` — breakdown by TA (note: multi-TA means counts > 38,977)
- `multi_ta_trials` — count of trials with 2+ TAs
- `confidence_distribution` — high/medium/low breakdown

**Note on Task 2 run history**: Task 2 was run multiple times during development:
- First runs used OAuth token but hit rate limits (32% error rate)
- Final run added `modality_evidence` and `ta_evidence` fields to the prompt
- The `load_cache` function in the final script clears entries missing evidence fields so old-format results are automatically re-processed
- Always confirm evidence fields are present before trusting results (see Step 0)
