# ALEXIS Dashboard — Handoff

## What This Is

ALEXIS is a clinical trial classification system (IQVIA) that processes ClinicalTrials.gov / AACT data to assign therapeutic areas and drug modalities to trials. This handoff covers the **weekly analytics dashboard pipeline** — Python computation → JSON payload → self-contained HTML dashboard (React + Babel, no build step).

---

## File Structure (post-refactor)

```
ALEXIS/
├── analytics/          ← Python compute modules (import from here)
│   ├── shared.py       ← constants, helpers, file-picker functions
│   ├── bd_wq1.py       ← wq1: Sponsor action table  [LIVE]
│   ├── bd_wq2.py       ← wq2: Sponsor watchlist     [STUB]
│   ├── bd_wq3.py       ← wq3: Competitive intel     [STUB]
│   ├── mk_wq1.py       ← wq4: Social stat cards     [LIVE]
│   ├── mk_wq2.py       ← wq5: Trending modalities   [STUB]
│   ├── mk_wq3.py       ← wq6: Conference snapshot   [STUB]
│   ├── sci_wq1.py      ← wq7: TA×Mod bubble matrix  [LIVE]
│   ├── sci_wq2.py      ← wq8: Classification gaps   [STUB]
│   ├── sci_wq3.py      ← wq9: MeSH quality waterfall[STUB]
│   ├── ops_wq1.py      ← wq10: Velocity dashboard   [LIVE]
│   ├── ops_wq2.py      ← wq11: Complexity waffle    [STUB]
│   └── ops_wq3.py      ← wq12: Phase 1 intake list  [STUB]
├── viz/
│   ├── alexis_weekly_dashboard.html  ← TEMPLATE — edit this, never the _live file
│   ├── bd_wq1.jsx      ← React component for wq1
│   ├── mk_wq1.jsx      ← React component for wq4
│   ├── sci_wq1.jsx     ← React component for wq7
│   └── ops_wq1.jsx     ← React component for wq10
├── pipelines/
│   └── generate_weekly_viz.py  ← Orchestrator: prompts user, calls all wqN, injects JSON, writes _live.html
└── utils/
    ├── mesh_lookup.py
    └── parallel_processor.py
```

**Note on wqN naming:** JSON payload keys follow the original numbering (`wq1`, `wq4`, `wq7`, `wq10`). The filenames use team-relative numbering (`bd_wq1`, `mk_wq1`, etc.) — these are different things.

**Run:** `python pipelines/generate_weekly_viz.py` from `~/projects/ALEXIS`

**Output:** `viz/alexis_weekly_dashboard_live.html` — do not edit; regenerate from template.

---

## Config (in `pipelines/generate_weekly_viz.py`)

```python
ROOT          = Path(__file__).parent.parent  # ALEXIS/
SNAPSHOT_DIRS = [ROOT/"storage/snapshots/clinical_trials_v2/reclassified",
                 ROOT/"storage/snapshots/clinical_trials_v2/last_update"]
CHANGELOG_DIR  = ROOT/"storage/changelogs"
MASTER_DB_DIRS = [ROOT/"storage", ROOT/"storage/master_db"]
TEMPLATE       = ROOT/"viz/alexis_weekly_dashboard.html"
OUTPUT         = ROOT/"viz/alexis_weekly_dashboard_live.html"
PLACEHOLDER    = "/* __ALEXIS_DATA_PLACEHOLDER__ */"
```

---

## Data Sources

| Source | Path pattern | Used for |
|--------|-------------|----------|
| Weekly snapshot | `snapshots/.../YYYY-MM-DD_YYYY-MM-DD_v1.json` | All questions |
| Enriched changelog | `changelogs/enriched_YYYY-MM-DD_YYYY-MM-DD_v1.json` | new/existing split, trial detail |
| Changelog | `changelogs/YYYY-MM-DD_YYYY-MM-DD_v1.json` | High-level counts |
| Master DB | `storage/master_DB_YYYY_QN.json` | Baseline for heat/comparison |
| Prior snapshots (3) | Same pattern, prior weeks | Rolling avgs for wq7, wq10 |

### Snapshot structure
```json
{
  "metadata": { "window_start", "window_end", "as_of", "run_id" },
  "trials": [ ...ClinicalTrialSignalV2... ],
  "summary": {
    "drug_trial_counts": { "drug_trials": int },
    "ta_modality_counts_true_drugs": { "TA": { "modality": count } },
    "drug_info_overview": { "drug_trials_total": int },
    "drug_study_intent": { "disease": int, "non_disease": int },
    "non_disease_study_categories": { "category": count }
  }
}
```

### Enriched trial fields (extends ClinicalTrialSignalV2)
`update_type`: `"new"` | `"existing"` · `update_categories`: list · `field_diffs`: list

### Trial fields used by dashboard
`nct_id`, `title`, `phase`, `sponsor_name`, `sponsor_class`, `therapeutic_area`, `modality`, `modality_source`, `is_drug_trial`, `update_type`, `field_diffs`, `overall_status`, `first_posted_date`, `therapeutic_areas_detected`, `info_flags`, `intervention_meshes`

---

## Interactive Startup Flow (`shared.py`)

```
pick_snapshot()         → user selects weekly snapshot
pick_changelog()        → auto-matches by date, user confirms
pick_enriched()         → auto-matches enriched file by date
pick_master_db()        → user selects master DB JSON
pick_prior_snapshots()  → shows 3 most recent prior snapshots
                          Enter = use all (default)
                          for each: loads enriched silently, falls back to snapshot summary
                          returns list of prior_week dicts (oldest first)
```

### Silent helpers
- `_extract_window_dates(filename)` → `(win_start, win_end)`
- `_load_enriched_silent(win_start, win_end)` → `{ta_mod, mod_totals, drug_new_total, phase_counts, source, filename}` or `None`
- `_load_changelog_counts_silent(win_start, win_end)` → `{new_active_all, new_inactive, existing_business, existing_metadata}` or `{}`

### Prior week dict structure
```python
{
  "window_label":      "2026-02-13 → 2026-02-20",
  "ta_mod":            {"Oncology": {"small_molecule": 45, ...}, ...},
  "ta_totals":         {"Oncology": 78, ...},      # derived
  "mod_totals":        {"small_molecule": 120, ...},
  "drug_new_total":    234,
  "phase_counts":      {"PHASE1": 12, ...},        # {} if summary fallback
  "source":            "enriched" | "snapshot_summary",
  "filename":          "enriched_2026-02-13_2026-02-20_v1.json",
  # from changelog (may be absent):
  "new_active_all": 528, "new_inactive": 204,
  "existing_business": 1250, "existing_metadata": 543,
}
```

---

## ALEXIS_DATA Payload (injected into HTML)

```js
ALEXIS_DATA = {
  generated_at,        // ISO timestamp
  snapshot_file,       // filename string
  is_reclassified,     // bool
  metadata,            // snapshot metadata dict
  snap_summary,        // full summary{} from snapshot
  changelog,           // { total_trials, new_active_registrations,
                       //   new_inactive_updates, existing_with_business_changes,
                       //   existing_metadata_only, category_counts }
  enriched_counts,     // { available, new, existing, total }
  master_db_meta,      // { available, drug_trials, rare_pct, filename }
  prior_weeks_meta,    // [{ window_label, source, drug_new_total }]
  wq1, wq4, wq7, wq10 // live question outputs (wq2,3,5,6,8,9,11,12 = null stubs)
}
```

---

## HTML Dashboard Architecture

**React + Babel, single-file, no build step.** Opens directly in any browser.

### CSS variables (dark theme)
```css
--bg:#0D1117  --surf2:#161B22  --surf3:#1C2128
--text:#E6EDF3  --muted:#8B949E  --dim:#484F58
--border:#21262D  --border2:#30363D
--cyan:#38BDF8  --green:#22C55E  --amber:#F59E0B  --red:#EF4444
--fm:'JetBrains Mono'  --fb:system-ui  --fh:system-ui
```

### Shared utilities (defined once in template)
```js
const fmt = n => n?.toLocaleString() ?? "—"
const humanMod = s => s.replace(/_/g," ").replace(/\b\w/g,c=>c.toUpperCase())
const parseMasterDbLabel = filename  // extracts "2025 Q4" from "master_DB_2025_Q4.json"
const modColor = mod       // hex color per modality
const heatToColor = heat   // {bg,border,glow} for heat value -1..+1
const MODALITY_ABBR = { small_molecule:"SM", monoclonal_antibody:"mAb", ... }
const PHASE_ORDER   = { PHASE3:1, PHASE2:3, PHASE1:5, ... }
const PHASE_COLORS  = { PHASE3:"#22C55E", PHASE2:"#38BDF8", PHASE1:"#A78BFA", ... }
```

### Component tree
```
App
├── Header (sticky — window dates, RECLASSIFIED badge, generated_at)
├── ViewToggle  ← Weekly Pulse | Quarterly/Yearly
├── TeamTabs    ← BD | Marketing | Scientific | Operations
└── View content
    ├── WeeklyBD({ data, color })         → Card(wq1), Placeholder(wq2,wq3)
    ├── WeeklyMarketing({ data, color })  → Card(wq4), Placeholder(wq5,wq6)
    ├── WeeklyScientific({ data, color }) → Card(wq7), Placeholder(wq8,wq9)
    ├── WeeklyOperations({ data, color }) → Card(wq10), Placeholder(wq11,wq12)
    └── QuarterlyView (all Placeholders)
```

**Card** — collapsible wrapper, shows question ID + business question text + viz type badge. `defaultOpen` prop keeps expanded on load.  
**Placeholder** — dimmed non-interactive card for unimplemented questions.

### TEAM_CFG
```js
{ accent, mid, soft, tab }
// e.g. Operations: { accent:"#F59E0B", mid:"#FBBF24", soft:"rgba(245,158,11,0.08)", tab:"amber" }
```

---

## wq1 — Sponsor Action Table (BD)
**Source:** `enriched_trials` (new registrations only)
**Shows:** Table of sponsors with new trials this week — name, class, count, TAs, phases, representative titles.

### Main table
Sortable columns: SPONSOR, NEW (count), MODALITY MIX (badges), TOP PHASE, SCORE, PRIORITY.
Scrollable container (`maxHeight:840`, sticky header). Priority = Σ modality_weight × phase_weight. Labels: HIGH ≥ 12, MED ≥ 4, LOW < 4.

### Expanded trial sub-table
Click any sponsor row → expands to show individual trials. Each sponsor has independent sort state (`subSort` keyed by sponsor name). Horizontal scrollbar via `overflowX:"auto"` + `maxWidth:0` on parent `<td>`.

**9 columns:** NCT ID (linked to CT.gov), TITLE, STATUS, MODALITY, MOD. EVIDENCE, TA, TA EVIDENCE, PHASE, 1ST POSTED.

**Status color-coding:**
- Green = Recruiting, Enrolling by Invitation
- Amber = Active Not Recruiting
- Muted = Not Yet Recruiting
- Red = Completed, Terminated, Withdrawn, Suspended
- Dead trials (completed/terminated/withdrawn/suspended) rendered at 55% opacity

**Modality evidence (`modality_source`):** Shows how the modality was determined — `mesh_tree` (MeSH descriptor hierarchy), `text` (regex on drug names), or `intervention_type` (CT.gov structured type). Set by `assign_trial_modality_v2()` in the classifier. For pre-existing data without `modality_source`, `bd_wq1.py` derives it from `info_flags` as a fallback.

**TA evidence:** Shows `therapeutic_areas_detected` — all TAs found via MeSH ancestry before primary selection.

**Note on "new" trials with COMPLETED status:** "New" means first appearance in the weekly CT.gov data feed (`update_type == "new"`), not "just started." Sponsors often register trials retroactively (e.g. for journal publication). ~21% of new registrations may be already completed.

---

## wq4 — Social Stat Cards (Marketing)
**Source:** `snap_summary`  
**Shows:** KPI cards — total drug trials, new this week, TA breakdown, modality breakdown, disease vs non-disease split.

---

## wq7 — TA × Modality Bubble Matrix (Scientific)

**Shows:** New drug trial registrations as bubble matrix. Bubble size = count. Color = heat vs rolling average.

### Heat formula
```
prior_avg_pct[ta][mod] = mean(prior_week[ta][mod] / prior_week.drug_new_total)
heat = (this_week_pct - prior_avg_pct) / max(prior_avg_pct, 0.001)
clamped to [-1, +1]
```
- `heat ≥ 0.15` → red (hotter) · `heat ≤ -0.15` → blue (cooler) · else → neutral grey
- Falls back to master DB comparison if no prior weeks
- New cells (never in prior weeks) → `heat = +1`

### Interaction
- Click bubble → sidebar panel below chart (stats + trial list)
- Click same bubble or ✕ → close sidebar
- No hover tooltip (removed)

### Python output
```python
{ available, has_heat, heat_mode,         # "rolling_avg"|"master_db"|"none"
  prior_weeks_used, prior_window_labels,
  rows, columns, cells,                   # cells keyed "TA||modality"
  row_totals, col_totals, grand_total, week_total, db_total }
```

### Cell structure
```python
{ ta, mod, count, baseline_n, prior_avg_count,
  heat,        # float -1..+1 or None
  heat_label,  # "▲ 87% above 3-week avg" (pre-computed)
  trials: [{ nct_id, title, phase }] }
```

---

## wq10 — Velocity Dashboard (Operations)

**Shows:** 2×2 tile grid tracking new drug trial velocity.

| Tile | Content |
|------|---------|
| 1 | Sparkline of new drug registrations (4 weeks) + pace vs avg |
| 2 | Diverging bar: top 3 / bottom 3 **TAs** by % change vs prior avg |
| 3 | Diverging bar: top 3 / bottom 3 **Modalities** by % change vs prior avg |
| 4 | Phase 1 intake rate — SVG arc gauge + sparkline (4 weeks) |

**Diverging bars:** Split at center-zero. Gainers grow right (amber), decliners grow left (blue). Excludes: `Unassigned drug study`, `Unknown`, `Non-disease`, `Other` from TA bars.

**Phase 1 intake:** Counts `PHASE1 + EARLY_PHASE1 + PHASE1/PHASE2` as % of new drug trials. Prior avg only if enriched files exist for prior weeks.

**Sub-components:** `MiniSparkline`, `DivergingBars`, `Phase1Gauge`, `WQ10VelocityDashboard`

---

## Classifier: Modality Source Tracking

`classifiers/trial_modality_v2.py` → `assign_trial_modality_v2(trial)` now sets `trial.modality_source` alongside `trial.modality`:

| Source | Meaning |
|--------|---------|
| `mesh_tree` | Resolved via MeSH descriptor tree numbers or ancestor signals (highest quality) |
| `text` | Matched via legacy regex patterns on intervention names / trial title |
| `intervention_type` | Fell back to CT.gov structured `intervention.type` field (lowest specificity) |

This field is persisted in enriched JSON after re-running the classifier pipeline. For data generated before this change, `bd_wq1.py` derives the source from `info_flags` as a backward-compatible fallback.

---

## Remaining Work (Priority Order)

1. **wq2** — BD: Sponsor watchlist (top movers week-over-week)
3. **wq3** — BD: Competitive intelligence feed
4. **wq5** — Marketing: Trending modalities/TAs chart
5. **wq6** — Marketing: Conference snapshot
6. **wq8** — Scientific: Classification gap report
7. **wq9** — Scientific: MeSH quality waterfall
8. **wq11** — Operations: Complexity waffle chart
9. **wq12** — Operations: Phase 1 intake list (individual trial cards)
10. **Quarterly view** — sq1–sq12 (all placeholders, master DB as primary source)

---

## Adding a New Question (Pattern)

1. Implement `wqN_function()` in the matching `analytics/XX_wqM.py` — return a dict
2. Import and call it in `pipelines/generate_weekly_viz.py`, assign to `payload["wqN"]`
3. Write a JSX component in `viz/XX_wqM.jsx` — reads `data.wqN`
4. Copy the JSX into the HTML template inside the correct `WeeklyXX` component
5. Replace the `<Placeholder>` for that question with a `<Card>` wrapping your component
