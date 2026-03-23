# ALEXIS Handoff 2 — Modality and TA Analysis
## Use after Task 2 finishes running

---

## What this session is for

Compare ALEXIS's rule-based modality and therapeutic area classifications against an independent LLM evaluation (Haiku) to identify systematic misclassifications and improve the pipeline.

---

## Background

ALEXIS classifies 38,977 active drug/interventional trials from ClinicalTrials.gov Q4 2025. The modality and TA pipeline uses MeSH terms, intervention names, and keyword patterns to assign:
- `modality` — drug class (single value)
- `therapeutic_area` — disease area (single value in ALEXIS, but LLM may assign multiple)

An independent Haiku evaluation was run on all 38,977 trials from scratch — no ALEXIS classifications used as input. This version includes `modality_evidence` and `ta_evidence` direct quote fields for auditability.

---

## IMPORTANT — verify Task 2 ran with evidence fields

The final version of `run_task2.py` includes `modality_evidence` and `ta_evidence` fields. Confirm by checking one entry:

```python
import json
d = json.load(open(r"C:\ALEXIS_eval\cache_task2.json"))
sample = next(v for v in d.values() if "error" not in v)
print(list(sample.keys()))
# Should include: modality_evidence, ta_evidence
```

If those fields are missing, the old version ran. Rerun with the updated `run_task2.py` before proceeding.

---

## File locations

| File | Path |
|---|---|
| LLM modality/TA results | `C:\ALEXIS_eval\llm_modality_ta_eval_Q4.json` |
| LLM task 2 summary | `C:\ALEXIS_eval\llm_eval_summary_task2.json` |
| Task 2 cache | `C:\ALEXIS_eval\cache_task2.json` |
| Master DB (ALEXIS classifications) | `\\wsl.localhost\Ubuntu\home\jeanmfc\projects\ALEXIS\storage\snapshots\clinical_trials_v2\active_universe\master_DB_2025_Q4_patched.json` |
| Batch files (trial text) | `C:\ALEXIS_eval\batches\batch_*.json` (1,949 files, 20 trials each) |

---

## LLM evaluation schema (Task 2)

Each trial in `llm_modality_ta_eval_Q4.json`:

```json
{
  "nct_id": "NCT...",
  "modality": "small_molecule",
  "modality_evidence": "exact phrase from trial text that determined modality",
  "therapeutic_areas": ["Oncology"],
  "ta_evidence": "exact phrase from trial text that determined therapeutic area",
  "confidence": "high|medium|low",
  "modality_reasoning": "1 sentence",
  "ta_reasoning": "1 sentence"
}
```

Key difference from Task 1: LLM may assign **multiple** therapeutic areas. ALEXIS assigns only one.

---

## Modality vocabulary

| Value | Definition |
|---|---|
| small_molecule | Small organic molecule drug |
| monoclonal_antibody | Naked mAb, bispecific antibody |
| biologic | Protein therapeutic, enzyme, cytokine, fusion protein (NOT mAb, NOT ADC) |
| adc | Antibody-drug conjugate |
| cell_therapy | CAR-T, TCR-T, NK cell, dendritic cell, stem cell |
| gene_therapy | Viral vector, CRISPR, gene editing |
| oligonucleotide | siRNA, antisense, mRNA, aptamer |
| vaccine | Prophylactic or therapeutic vaccine |
| radiopharmaceutical | Radiolabeled compound for therapy or imaging |
| combination | Fixed combination of two distinct modality classes |
| other | Does not fit any above |

---

## TA vocabulary

Oncology, Infectious Disease, Immunology / Inflammation, Cardiovascular, Neurology / CNS, Metabolic / Endocrine, Rare / Genetic, Respiratory, Gastrointestinal / Hepatic, Musculoskeletal, Dermatology, Hematology, Ophthalmology, Psychiatry, Urology, Non-disease drug study, Other

---

## What to do — step by step

### Step 0 — Verify evidence fields are real (do this first)

Before any analysis, confirm Haiku actually read the trial text rather than hallucinating.
Check every single evidence quote across all trials:

```python
import json, glob

# Build index of all trial texts from batch files
print("Building batch index...")
batch_index = {}
for bf in glob.glob(r"C:\ALEXIS_eval\batches\batch_*.json"):
    batch = json.load(open(bf, encoding="utf-8"))
    batch_index.update(batch)
print(f"Indexed {len(batch_index)} trials")

# Load LLM results
llm = {r["nct_id"]: r for r in json.load(open(r"C:\ALEXIS_eval\llm_modality_ta_eval_Q4.json"))}

mod_found     = 0
mod_not_found = 0
ta_found      = 0
ta_not_found  = 0
empty         = 0
examples_not_found = []

for nct_id, r in llm.items():
    trial_text = batch_index.get(nct_id, "").lower()

    # Check modality evidence
    mod_ev = r.get("modality_evidence", "").strip()
    if not mod_ev or len(mod_ev) < 10:
        empty += 1
    elif mod_ev.lower() in trial_text:
        mod_found += 1
    else:
        mod_not_found += 1
        if len(examples_not_found) < 10:
            examples_not_found.append({
                "nct_id":   nct_id,
                "field":    "modality_evidence",
                "modality": r.get("modality"),
                "evidence": mod_ev
            })

    # Check TA evidence
    ta_ev = r.get("ta_evidence", "").strip()
    if not ta_ev or len(ta_ev) < 10:
        empty += 1
    elif ta_ev.lower() in trial_text:
        ta_found += 1
    else:
        ta_not_found += 1
        if len(examples_not_found) < 20:
            examples_not_found.append({
                "nct_id":   nct_id,
                "field":    "ta_evidence",
                "ta":       r.get("therapeutic_areas"),
                "evidence": ta_ev
            })

mod_total = mod_found + mod_not_found
ta_total  = ta_found + ta_not_found

print(f"\nEvidence verification across ALL trials:")
print(f"  Modality evidence found:    {mod_found}/{mod_total} ({mod_found/mod_total*100:.1f}%)")
print(f"  Modality evidence missing:  {mod_not_found}/{mod_total} ({mod_not_found/mod_total*100:.1f}%)")
print(f"  TA evidence found:          {ta_found}/{ta_total} ({ta_found/ta_total*100:.1f}%)")
print(f"  TA evidence missing:        {ta_not_found}/{ta_total} ({ta_not_found/ta_total*100:.1f}%)")
print(f"  Empty/too short (skipped):  {empty}")

if examples_not_found:
    print(f"\nFirst {len(examples_not_found)} evidence quotes NOT found in trial text:")
    for ex in examples_not_found:
        print(f"  {ex['nct_id']} | {ex['field']} | '{ex['evidence']}'")

# Save full not-found list
not_found_full = []
for nct_id, r in llm.items():
    trial_text = batch_index.get(nct_id, "").lower()
    for field in ["modality_evidence", "ta_evidence"]:
        ev = r.get(field, "").strip()
        if ev and len(ev) >= 10 and ev.lower() not in trial_text:
            not_found_full.append({
                "nct_id":   nct_id,
                "field":    field,
                "value":    r.get("modality") if field == "modality_evidence" else r.get("therapeutic_areas"),
                "evidence": ev
            })

with open(r"C:\ALEXIS_eval\evidence_not_found_task2.json", "w") as f:
    json.dump(not_found_full, f, indent=1)
print(f"\nFull not-found list saved to C:\\ALEXIS_eval\\evidence_not_found_task2.json")
```

**Interpretation:**
- >85% found → evidence is real, proceed with analysis
- 60-85% found → partial hallucination, treat evidence as indicative not definitive
- <60% found → significant hallucination problem, do not use results until Task 2 is rerun

If evidence rate is low, check whether the script that ran Task 2 was the version WITH evidence fields (`modality_evidence` and `ta_evidence` in the output schema). If it was the old version without those fields, rerun with the updated `run_task2.py`.

---

### Step 1 — Load and align

Load both files and join on nct_id. Compute:

```python
modality_match = llm["modality"] == alexis["modality"]
ta_match       = alexis["therapeutic_area"] in llm["therapeutic_areas"]
```

Print:
- Total modality agreements and disagreements
- Total TA agreements and disagreements
- Confidence distribution (high/medium/low) for disagreements vs agreements

### Step 2 — Modality disagreement analysis

Group modality disagreements by (alexis_modality, llm_modality) pair. For each pair:
- How many trials?
- What does the evidence field say?
- Is this a systematic ALEXIS error or LLM error?

Known boundary cases to watch:
- `biologic` vs `monoclonal_antibody` — ALEXIS may call naked mAbs as biologic
- `combination` vs single modality — LLM more likely to catch fixed-dose combinations
- `oligonucleotide` vs `gene_therapy` — mRNA vaccines sometimes misclassified
- `adc` vs `monoclonal_antibody` — ADC payload sometimes not recognized

For each systematic pattern: determine whether ALEXIS or LLM is correct by reading trial text in batch files.

### Step 3 — TA disagreement analysis

TA comparison is asymmetric because LLM can assign multiple TAs but ALEXIS assigns one.

Three cases:
1. **Hard disagreement**: ALEXIS TA not in LLM therapeutic_areas at all → likely ALEXIS error
2. **Multi-TA miss**: LLM assigned multiple TAs, ALEXIS only got one → ALEXIS may be incomplete
3. **LLM overcall**: LLM assigned extra TAs that don't seem justified by evidence field → LLM error

Focus on hard disagreements first. Group by (alexis_ta, llm_primary_ta) to find systematic patterns.

### Step 4 — Multi-TA analysis

Find all trials where LLM assigned 2+ therapeutic areas. For each:
- What combination did LLM assign?
- What did ALEXIS assign?
- Is the multi-TA assignment justified by the evidence field?

Common legitimate multi-TA patterns:
- Oncology + Rare / Genetic (e.g. rare pediatric cancers)
- Infectious Disease + Immunology / Inflammation (e.g. HIV immunology)
- Hematology + Oncology (e.g. leukemia)
- Metabolic / Endocrine + Cardiovascular (e.g. diabetes with CV outcomes)

Decide whether ALEXIS should support multi-TA assignments or keep single TA.

### Step 5 — Verify evidence fields

For a random sample of 20 disagreements, verify the evidence field contains a real quote from the trial text:

```python
import json, glob

batch_index = {}
for bf in glob.glob(r"C:\ALEXIS_eval\batches\batch_*.json"):
    batch = json.load(open(bf))
    batch_index.update(batch)

# For a trial, check if evidence appears in trial text
nct_id = "NCT..."
trial_text = batch_index.get(nct_id, "")
evidence = llm_result["modality_evidence"]
print(evidence in trial_text)  # Should be True
```

If evidence fields are frequently not found in trial text → LLM hallucinated, results are unreliable.

### Step 6 — Update ALEXIS pipeline

After analysis, identify which changes to make:
- Modality classification rule fixes
- TA classification rule fixes
- Whether to add multi-TA support to ALEXIS

Commit changes to GitHub.

---

## LLM stats (Task 2 — check against actual final output)

- Total evaluated: ~38,977
- Valid results with evidence fields: TBD (check after final run)
- Modality distribution: TBD
- Multi-TA trials: TBD
- Confidence distribution: TBD
