# ALEXIS Handoff 1 — Biomarker Analysis
## Start here while Task 2 runs in the background

---

## What this session is for

Compare ALEXIS's rule-based biomarker classifications against an independent LLM evaluation (Haiku) to improve `biomarker_policy.py` — specifically the keyword dictionary, pattern triggers, and exclusion logic.

---

## Background

ALEXIS classifies 38,977 active drug/interventional trials from ClinicalTrials.gov Q4 2025. The biomarker pipeline (`policy/biomarker_policy.py`) uses regex patterns to determine:
- Is this trial biomarker-relevant to a bioanalytical CRO (IQVIA Biosciences)?
- What specific targets are present and what is their role?

An independent Haiku evaluation was run on all 38,977 trials from scratch — no ALEXIS classifications used as input.

---

## File locations

| File | Path |
|---|---|
| LLM biomarker results | `C:\ALEXIS_eval\llm_biomarker_eval_Q4.json` |
| LLM task 1 summary | `C:\ALEXIS_eval\llm_eval_summary_task1.json` |
| Task 1 cache | `C:\ALEXIS_eval\cache_task1.json` |
| Master DB (ALEXIS classifications) | `\\wsl.localhost\Ubuntu\home\jeanmfc\projects\ALEXIS\storage\snapshots\clinical_trials_v2\active_universe\master_DB_2025_Q4_patched.json` |
| Biomarker policy | `\\wsl.localhost\Ubuntu\home\jeanmfc\projects\ALEXIS\policy\biomarker_policy.py` |
| Batch files (trial text) | `C:\ALEXIS_eval\batches\batch_*.json` (1,949 files, 20 trials each) |

---

## LLM evaluation schema (Task 1)

Each trial in `llm_biomarker_eval_Q4.json`:

```json
{
  "nct_id": "NCT...",
  "relevant": true,
  "reasoning": "1-2 sentences explaining why relevant or not",
  "targets": [
    {
      "target": "exact name from known list",
      "role": "inclusion|exclusion|measurement",
      "result_use": "clinical|bioanalytical",
      "safety_lab": false,
      "evidence": "exact phrase from trial text"
    }
  ],
  "novel_targets": [
    {
      "name": "target name or description",
      "role": "inclusion|exclusion|measurement",
      "result_use": "clinical|bioanalytical",
      "evidence": "exact phrase from trial text"
    }
  ]
}
```

Key fields:
- `relevant` — LLM's independent judgment (true/false)
- `evidence` — direct quote from trial text that triggered the classification
- `novel_targets` — targets LLM identified that are NOT in ALEXIS's known list

---

## ALEXIS biomarker fields in master DB

Each trial in master DB has:
- `biomarker_relevant` — True/False (from rules)
- `biomarker_confidence` — "high" | "medium"
- `biomarker_reason` — which pattern triggered
- `biomarker_targets` — list of matched known targets
- `pk_only` — True if trial is pure pharmacokinetic

---

## Known target list (82 targets in ALEXIS)

PD-L1, PD-1, CTLA-4, LAG-3, TIM-3, HER2, EGFR, KRAS, NRAS, BRAF, ALK, ROS1, MET, FGFR, NTRK, RET, BRCA, ESR1, PR, PIK3CA, TMB, MSI-H, MRD, ctDNA, CTC, CD19, CD20, CD22, CD38, CD79b, CD3, CD33, CD47, CD30, CD123, CD34, BCMA, BCL-2, FLT3, IDH1, IDH2, JAK2, JAK1, ADA, PD-L1 CDx, HER2 CDx, IL-6, IL-17, TNF, VEGF, VEGFR, mTOR, CDK4/6, PARP, AR, CRP, ANA, anti-dsDNA, Complement, IgE, Eosinophil, HbA1c, PSA, Insulin, GLP-1, Glucagon, NT-proBNP, BNP, Troponin, TTR, HbF, Platelet, UACR, eGFR, DSA, HLA, p-tau, Amyloid-b, HBsAg, HCV RNA, HIV RNA, HBV DNA

---

## What to do — step by step

### Step 0 — Verify evidence fields are real (do this first)

Load both files and join on nct_id. Compute for each trial:

```python
agreement       = (llm["relevant"] == alexis["biomarker_relevant"])
llm_only        = llm["relevant"] and not alexis["biomarker_relevant"]  # false negatives
alexis_only     = alexis["biomarker_relevant"] and not llm["relevant"]  # false positives
```

Print counts for all four categories.

### Step 2 — False negatives (LLM relevant, ALEXIS missed)

For each trial where `llm_only = True`:
- Read the `evidence` field — what exact phrase triggered LLM?
- Check if that phrase is covered by any pattern in `biomarker_policy.py`
- If not → candidate for new pattern or new target

Group by evidence phrase to find systematic gaps.

### Step 3 — False positives (ALEXIS relevant, LLM said not)

For each trial where `alexis_only = True`:
- Read `biomarker_reason` from ALEXIS — which pattern triggered?
- Read LLM `reasoning` — why did it say not relevant?
- Group by trigger pattern to find overcalling patterns

Known overcalling patterns from prior 1,000-trial evaluation:
- `pharmacokinetic` without biomarker co-signal (already fixed in policy v2 — verify fixed)
- `immunolog` as disease exclusion criterion
- `marker` in imaging context (RANO, RECIST)
- `assay` in diagnostic/microbial context
- `biomarker` in title when trial measures step count or PROs

### Step 4 — Novel targets

Pull all `novel_targets` from LLM output. Count frequency. Top candidates from prior spot-check:

| Target | Count seen | Add to ALEXIS? |
|---|---|---|
| Ki67 | 3+ | Yes — proliferation marker, common in oncology |
| Tumor-infiltrating lymphocytes (TILs) | 3+ | Yes |
| IGHV mutation status | 3+ | Yes — CLL standard |
| Regulatory T cells (Treg) | 4+ | Yes |
| TP53 mutation status | 3+ | Partial — check if covered by existing patterns |
| Testosterone | 3+ | Yes — endocrine/urology |
| PTEN | 2+ | Yes |
| C-peptide | 4+ | Yes — pancreatic function |
| Microbiome composition | 4+ | Discuss with Bo — new category |
| CA19-9 | 2+ | Yes — tumor marker |
| Chimerism | 2+ | Yes — transplant biomarker |

For each novel target to add: write the regex pattern and metadata entry for `biomarker_policy.py`.

### Step 5 — Update biomarker_policy.py

After analysis, update the policy file with:
1. New entries in `BIOMARKER_TARGETS` dict
2. New/expanded patterns for existing targets
3. Tightened exclusion patterns in `CONTEXT_UPGRADEABLE`
4. New entries in `TARGET_METADATA`

Commit to GitHub with message: `biomarker_policy: v3 — LLM evaluation improvements Q4 2025`

---

## Known LLM evaluation biases to keep in mind

- **Inclusion-only genetic tests**: LLM sometimes flags trials where KRAS/NPM1/FLT3 mutation is only an enrollment criterion with no ongoing measurement — these may be false positives from LLM
- **Chimerism**: LLM incorrectly excluded some chimerism trials — if you see chimerism in LLM=not relevant, ALEXIS is likely correct
- **Safety labs**: LLM sometimes includes ALT/AST/CBC as biomarkers when they are routine safety monitoring — check `safety_lab` field
- **Overall LLM accuracy**: ~80% on 20-trial spot check vs manual review

---

## Step 0 — Verify evidence fields are real (do this first)

Before any analysis, confirm Haiku actually read the trial text rather than hallucinating.
Check every single evidence quote across all 38,977 trials:

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
llm = {r["nct_id"]: r for r in json.load(open(r"C:\ALEXIS_eval\llm_biomarker_eval_Q4.json"))}

found       = 0
not_found   = 0
empty       = 0
total       = 0
examples_not_found = []

for nct_id, r in llm.items():
    if not r.get("relevant"):
        continue
    trial_text = batch_index.get(nct_id, "").lower()
    for t in r.get("targets", []) + r.get("novel_targets", []):
        evidence = t.get("evidence", "").strip()
        if not evidence or len(evidence) < 10:
            empty += 1
            continue
        total += 1
        if evidence.lower() in trial_text:
            found += 1
        else:
            not_found += 1
            if len(examples_not_found) < 20:
                examples_not_found.append({
                    "nct_id":   nct_id,
                    "target":   t.get("target") or t.get("name"),
                    "evidence": evidence
                })

print(f"\nEvidence verification across ALL relevant trials:")
print(f"  Total evidence quotes checked: {total}")
print(f"  Found in trial text:           {found} ({found/total*100:.1f}%)")
print(f"  NOT found in trial text:       {not_found} ({not_found/total*100:.1f}%)")
print(f"  Empty/too short (skipped):     {empty}")

if examples_not_found:
    print(f"\nFirst {len(examples_not_found)} evidence quotes NOT found in trial text:")
    for ex in examples_not_found:
        print(f"  {ex['nct_id']} | {ex['target']}")
        print(f"    Evidence: '{ex['evidence']}'")

# Save full not-found list
not_found_full = []
for nct_id, r in llm.items():
    if not r.get("relevant"):
        continue
    trial_text = batch_index.get(nct_id, "").lower()
    for t in r.get("targets", []) + r.get("novel_targets", []):
        evidence = t.get("evidence", "").strip()
        if evidence and len(evidence) >= 10 and evidence.lower() not in trial_text:
            not_found_full.append({
                "nct_id":   nct_id,
                "target":   t.get("target") or t.get("name"),
                "evidence": evidence
            })

with open(r"C:\ALEXIS_eval\evidence_not_found.json", "w") as f:
    json.dump(not_found_full, f, indent=1)
print(f"\nFull not-found list saved to C:\\ALEXIS_eval\\evidence_not_found.json")
```

**Interpretation:**
- >85% found → evidence is real, proceed with analysis
- 60-85% found → partial hallucination, treat evidence as indicative not definitive
- <60% found → significant hallucination problem, flag before using results

---

## LLM final stats (Task 1)

- Total evaluated: 38,977
- Valid results: 38,977 (0 errors)
- Relevant: 23,283 (59.7%)
- ALEXIS relevant: 9,779 (25.1%)
- Note: LLM relevance rate (59.7%) is much higher than ALEXIS (25.1%) — expect significant false positive analysis
- Expected agreement: ~80% based on prior 1,000-trial evaluation
