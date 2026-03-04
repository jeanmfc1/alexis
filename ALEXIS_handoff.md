# ALEXIS Dashboard — Handoff Document

## Project Overview

ALEXIS is a clinical trial classification system at IQVIA that processes ClinicalTrials.gov / AACT data to assign therapeutic areas and drug modalities to trials. This handoff covers the **analytics dashboard pipeline** — a Python aggregation script that generates a self-contained HTML dashboard.

---

## Files

### `/analytics/generate_weekly_viz.py`
Interactive Python script run manually each week. Prompts the user to select files, computes all visualization data, injects it as JSON into the HTML template, and writes `alexis_weekly_dashboard_live.html`.

**Run with:** `python generate_weekly_viz.py` from the analytics directory.

### `/analytics/alexis_weekly_dashboard.html`
The template file. Contains a React + Babel app (no build step, runs in browser). Has a single placeholder `/* __ALEXIS_DATA_PLACEHOLDER__ */` where the Python script injects data. **This is the file you edit.** Never edit the `_live.html` directly.

### `/analytics/alexis_weekly_dashboard_live.html`
Auto-generated output. Opens directly in browser. **Do not edit.**

---

## Data Sources

| Source | Path pattern | Used for |
|--------|-------------|----------|
| Weekly snapshot | `storage/snapshots/clinical_trials_v2/reclassified/YYYY-MM-DD_YYYY-MM-DD_v1.json` | Main data, all questions |
| Enriched changelog | `storage/changelogs/enriched_YYYY-MM-DD_YYYY-MM-DD_v1.json` | New vs existing split, per-trial detail |
| Changelog | `storage/changelogs/YYYY-MM-DD_YYYY-MM-DD_v1.json` | High-level counts (new_active_registrations etc.) |
| Master DB | `storage/master_DB_YYYY_QN.json` | Baseline for heat/comparison |
| Prior snapshots | Same pattern, 3 weeks back | Rolling averages for wq7 and wq10 |

### Snapshot structure
```json
{
  "metadata": { "window_start", "window_end", "as_of", "run_id" },
  "trials": [ ...ClinicalTrialSignalV2 objects... ],
  "summary": {
    "drug_trial_counts": { "drug_trials": int },
    "ta_modality_counts_true_drugs": { "TA": { "modality": count } },
    "drug_info_overview": { "drug_trials_total": int },
    "drug_study_intent": { "disease": int, "non_disease": int },
    "non_disease_study_categories": { "category": count }
  }
}
```

### Enriched file structure
```json
{
  "metadata": { "drug_only": true },
  "trials": [
    { ...all ClinicalTrialSignalV2 fields...,
      "update_type": "new" | "existing",
      "update_categories": [...],
      "field_diffs": [...] }
  ]
}
```

### Trial fields used by the dashboard
- `nct_id`, `title`, `phase`, `sponsor_name`, `sponsor_class`
- `therapeutic_area`, `modality`, `is_drug_trial`
- `update_type` (from enriched), `field_diffs` (from enriched)

---

## Python Script Architecture

### Interactive startup flow
```
pick_snapshot()          → user selects weekly snapshot
pick_changelog()         → auto-matches by date, user confirms
pick_enriched()          → auto-matches enriched file by date
pick_master_db()         → user selects master DB JSON
                           returns (summary_dict, filename_str)
pick_prior_snapshots()   → shows 3 most recent prior snapshots
                           user presses Enter to use all (DEFAULT = use all)
                           for each: loads enriched silently, falls back to snapshot summary
                           returns list of prior_week dicts (oldest first)
```

### Silent helpers (no user prompt)
- `_extract_window_dates(filename)` — extracts `(win_start, win_end)` from any dated filename
- `_load_enriched_silent(win_start, win_end)` — finds matching enriched file, returns `{ta_mod, mod_totals, drug_new_total, phase_counts, source, filename}` or `None`
- `_load_changelog_counts_silent(win_start, win_end)` — finds matching changelog, returns `{new_active_all, new_inactive, existing_business, existing_metadata}` or `{}`

### Prior week dict structure
Each entry in `prior_weeks` list:
```python
{
  "window_label":   "2026-02-13 → 2026-02-20",
  "ta_mod":         {"Oncology": {"small_molecule": 45, ...}, ...},
  "ta_totals":      {"Oncology": 78, ...},        # derived
  "mod_totals":     {"small_molecule": 120, ...}, # derived
  "drug_new_total": 234,
  "phase_counts":   {"PHASE1": 12, "PHASE2": 34, ...},  # {} if summary fallback
  "source":         "enriched" | "snapshot_summary",
  "filename":       "enriched_2026-02-13_2026-02-20_v1.json",
  # merged from changelog (may be absent):
  "new_active_all": 528,
  "new_inactive":   204,
  "existing_business": 1250,
  "existing_metadata": 543,
}
```

### Visualization functions
| Function | Team | Status | Source |
|----------|------|--------|--------|
| `wq1_sponsor_action_table()` | BD | ✅ Live | enriched_trials |
| `wq2..wq3` | BD | 🔲 Stub | — |
| `wq4_social_stat_cards()` | Marketing | ✅ Live | snap_summary |
| `wq5..wq6` | Marketing | 🔲 Stub | — |
| `wq7_ta_modality_matrix()` | Scientific | ✅ Live | enriched_trials + prior_weeks |
| `wq8..wq9` | Scientific | 🔲 Stub | — |
| `wq10_velocity_dashboard()` | Operations | ✅ Live | enriched_trials + prior_weeks |
| `wq11..wq12` | Operations | 🔲 Stub | — |

---

## HTML Dashboard Architecture

**React + Babel, single-file, no build step.** Opens directly in any browser.

### CSS variables (dark theme)
```css
--bg: #0D1117    --surf2: #161B22    --surf3: #1C2128
--text: #E6EDF3  --muted: #8B949E   --dim: #484F58
--border: #21262D  --border2: #30363D
--cyan: #38BDF8  --green: #22C55E
--fm: 'JetBrains Mono'  --fb: system-ui  --fh: system-ui
```

### Key shared utilities (defined once at top of script)
```js
const fmt = n => n?.toLocaleString() ?? "—"
const humanMod = s => s.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())
const parseMasterDbLabel = filename => // extracts "2025 Q4" from "master_DB_2025_Q4.json"
const modColor = mod => // returns hex color per modality
const heatToColor = heat => // returns {bg, border, glow} based on heat value -1..+1
const MODALITY_ABBR = { small_molecule: "SM", monoclonal_antibody: "mAb", ... }
const PHASE_ORDER = { PHASE3: 1, PHASE2: 3, PHASE1: 5, ... }
const PHASE_COLORS = { PHASE3: "#22C55E", PHASE2: "#38BDF8", PHASE1: "#A78BFA", ... }
```

### Component tree
```
App
├── Header (sticky — window dates, RECLASSIFIED badge, generated_at)
├── ViewToggle  ← Weekly Pulse (left/default) | Quarterly/Yearly (right)
├── TeamTabs    ← BD | Marketing | Scientific | Operations
└── View content
    ├── WeeklyBD({ data, color })        → Card(wq1), Placeholder(wq2,wq3)
    ├── WeeklyMarketing({ data, color }) → Card(wq4), Placeholder(wq5,wq6)
    ├── WeeklyScientific({ data, color })→ Card(wq7), Placeholder(wq8,wq9)
    ├── WeeklyOperations({ data, color })→ Card(wq10), Placeholder(wq11,wq12)
    └── QuarterlyView (all Placeholders)
```

### Card component
Collapsible wrapper — shows question ID, business question text, viz type badge. `defaultOpen` prop keeps it expanded on load.

### Placeholder component
Dimmed non-interactive card for questions not yet implemented.

### TEAM_CFG
Each team has a color config object:
```js
{ accent, mid, soft, tab }
// e.g. Operations: { accent:"#F59E0B", mid:"#FBBF24", soft:"rgba(245,158,11,0.08)", tab:"amber" }
```

---

## wq7 — TA × Modality Bubble Matrix (Scientific)

**What it shows:** New drug trial registrations this window as a bubble matrix. Bubble size = count. Color = heat (deviation from rolling average).

**Heat formula:**
```
prior_avg_pct[ta][mod] = mean(prior_week[ta][mod] / prior_week.drug_new_total)
heat = (this_week_pct - prior_avg_pct) / max(prior_avg_pct, 0.001)
clamped to [-1, +1]
```
- `heat ≥ 0.15` → red (hotter than average)
- `heat ≤ -0.15` → blue (cooler than average)
- Otherwise → neutral grey
- Falls back to master DB comparison if no prior weeks loaded
- `heat = +1` (max red) for cells never seen in prior weeks

**Interaction:**
- Click bubble → opens sidebar panel below the chart showing stats + trial list
- Click same bubble again (or ✕) → closes sidebar
- Inline row expansion (the original row-push behavior) still works alongside the sidebar
- **No hover tooltip** — removed

**Python output keys:**
```python
{ available, has_heat, heat_mode,  # "rolling_avg"|"master_db"|"none"
  prior_weeks_used, prior_window_labels,
  rows, columns, cells,            # cells keyed "TA||modality"
  row_totals, col_totals, grand_total, week_total, db_total }
```

**Cell structure:**
```python
{ ta, mod, count, baseline_n, prior_avg_count,
  heat,        # float -1..+1 or None
  heat_label,  # "▲ 87% above 3-week avg" (pre-computed in Python)
  trials: [{ nct_id, title, phase }] }
```

---

## wq10 — Velocity Dashboard (Operations)

**What it shows:** 2×2 grid of tiles tracking new drug trial velocity.

| Tile | Content |
|------|---------|
| 1 | Sparkline of new drug registrations over 4 weeks + pace vs avg |
| 2 | Diverging bar: top 3 / bottom 3 **TAs** by % change vs prior avg |
| 3 | Diverging bar: top 3 / bottom 3 **Modalities** by % change vs prior avg |
| 4 | Phase 1 intake rate — arc gauge + sparkline of % over 4 weeks |

**Diverging bar logic:**
- Bars are split at a true center zero line
- Gainers grow **right** (amber), decliners grow **left** (blue)
- Filtered: `Unassigned drug study`, `Unknown`, `Non-disease`, `Other` excluded from TA bars

**Phase 1 intake:**
- Counts `PHASE1 + EARLY_PHASE1 + PHASE1/PHASE2` as % of new drug trials
- Prior avg only available if enriched files exist for prior weeks (not summary fallback)
- SVG arc gauge with average marker (amber dot on track)

**HTML sub-components:** `MiniSparkline`, `DivergingBars`, `Phase1Gauge`, `WQ10VelocityDashboard`

---

## Known Issue — Dark Screen on `_live.html`

**Symptom:** `alexis_weekly_dashboard_live.html` shows only a dark screen.

**Most likely cause:** A JSX syntax error introduced in the last round of edits (wq10 diverging bars rewrite + wq7 sidebar conversion). The browser console will show the exact error.

**To debug:**
1. Open `alexis_weekly_dashboard_live.html` in Chrome
2. Open DevTools → Console
3. Look for `SyntaxError` or `ReferenceError` — it will point to a line number
4. The most likely culprits are:
   - `DivergingBars` component — `const Row = ({ b }) =>` defined inside function body, `LABEL_W` used inside `Row` before it's defined as `const LABEL_W = 110` (should be fine as closure, but verify)
   - The wq7 sidebar panel — the `openCell === tooltip.key` check references `tooltip.key` which was added in the click handler but verify it's set correctly
   - Brace/paren mismatch from the tooltip replacement

**Quick fix approach:**
- Check brace balance in `DivergingBars` and `WQ7BubbleMatrix` components
- The script brace count was 1047 open = 1047 close (balanced) but JSX template literals can fool simple counts

---

## Remaining Work

### Stubs to implement
- `wq2` — BD: Sponsor watchlist (top movers week-over-week)
- `wq3` — BD: Competitive intelligence feed
- `wq5` — Marketing: Trending modalities/TAs chart
- `wq6` — Marketing: Conference snapshot
- `wq8` — Scientific: Classification gap report
- `wq9` — Scientific: MeSH quality waterfall
- `wq11` — Operations: Complexity waffle chart
- `wq12` — Operations: Phase 1 intake list (individual trial cards)

### Quarterly view
All 12 quarterly questions (sq1–sq12) are placeholders. Require master DB as primary source.

---

## Config Constants in generate_weekly_viz.py

```python
ROOT          = Path(__file__).parent.parent
SNAPSHOT_DIRS = [
    ROOT / "storage/snapshots/clinical_trials_v2/reclassified",
    ROOT / "storage/snapshots/clinical_trials_v2/last_update",
]
CHANGELOG_DIR  = ROOT / "storage/changelogs"
MASTER_DB_DIRS = [ROOT / "storage", ROOT / "storage/master_db"]
TEMPLATE       = ROOT / "analytics/alexis_weekly_dashboard.html"
OUTPUT         = ROOT / "analytics/alexis_weekly_dashboard_live.html"
PLACEHOLDER    = "/* __ALEXIS_DATA_PLACEHOLDER__ */"
RARE_MODALITY_PCT = 0.5   # used by wq7 legacy logic
```

---

## ALEXIS_DATA payload structure (injected into HTML)

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
  wq1, wq2, ..., wq12  // output of each wqN function
}
```
