# ALEXIS — Session Handoff (Desktop App + Operator Console)

**Updated:** 2026-06-24 · **Author:** Jean Custodio (assembled by Claude Code)
**Purpose:** Standalone context to resume ALEXIS in a fresh session. Assumes zero prior context. The earlier classifier-era handoff is `ALEXIS_handoff.md` (Feb–Apr 2026, still accurate for the ML/pipeline internals). **This document covers the June 2026 work: turning ALEXIS into a packaged Windows desktop app.**

---

## 0. TL;DR — Current State

- ALEXIS is now a **native Windows desktop app** (pywebview + FastAPI), packaged as `ALEXIS.exe` (PyInstaller one-folder, ~25 MB + `_internal`).
- Four tabs: **Dashboards** (view generated HTML dashboards), **Classifier** (paste a trial → modality + therapeutic area, no models needed), **Pipelines** (run every data pipeline as background jobs with live logs), **Settings** (data folder).
- All classification/analytics code is unchanged and reused; the desktop layer lives in a new `app/` package + `core/paths.py`.
- **Multiprocessing classification works in the packaged exe** (verified: 7 workers). The parallelism is deliberately preserved — **do not change it** (see §8).
- **GitHub:** repo `jeanmfc1/alexis`, branch `chore/cleanup` merged to `main` via PR #1 and PR #2. `origin/main` head = `8adad46`.
- **Uncommitted at handoff time:** a "Pull last 3 weeks (get started)" onboarding bootstrap (`pull_recent_weeks` job + `pulse_window_v1 --weeks N`) — implemented, pending a `--weeks 1` functional test → commit → rebuild. Files: `pipelines/pulse_window_v1.py`, `app/jobs/catalog.py`, `app/web/{app.js,index.html}`.
- **Build output:** `C:\ALEXIS_build\dist\ALEXIS\ALEXIS.exe` (one-folder). Build with the spec (see §5).
- **The exe is currently in a "fresh new-user" state** (config cleared on purpose); see §6.

---

## 1. What ALEXIS Is

Internal clinical-trial intelligence platform (IQVIA Laboratories). Ingests trials from ClinicalTrials.gov/AACT (US) plus ChiCTR (China) and ANZCTR (Australia); classifies each by **drug modality** and **therapeutic area (TA)**; renders four persona dashboards (Business Development / Marketing / Operations / Scientific). Python; data stored as JSON snapshots.

---

## 2. Environments

| | Path | Python | Role |
|---|---|---|---|
| Repo (WSL) | `\\wsl.localhost\Ubuntu\home\jeanmfc\projects\ALEXIS` | 3.12 `.venv` (stale/incomplete) | source of truth |
| Build/run Python | Windows Store `python3.11` (sklearn 1.6.1, pandas 2.2.3, pyarrow 22.0.0) | 3.11.9 | runs the app + builds the exe |

- The repo lives on the WSL filesystem, accessed from Windows via the `\\wsl.localhost\...` UNC path. **Native Windows Python can read it** (verified).
- Run the app / build with **`py -3.11`** (NOT the WSL `.venv`, which is sklearn 1.8.0 and would break the pkl models).
- **The build process is `python3.11.exe`, not `python.exe`** — checking `Get-Process python.exe` finds nothing and gives false "nothing running". Always match `python3.11` and `ALEXIS`.

---

## 3. Architecture

### The app (`app/` package — new this session)
```
app/
  __main__.py        # `py -3.11 -m app` entry; handles --run-pipeline dispatch + freeze_support
  main.py            # run(): pywebview window on main thread; uvicorn in a daemon thread (127.0.0.1, ephemeral port)
                     #        ensure_streams() (utf-8 stdout for windowed exe); get_window() for native dialogs
  server.py          # create_app(): FastAPI factory, CORS loopback-only, body-size guard, static mounts, routers
  api/
    classify.py      # POST /api/classify_trial          (pure-python classifier)
    dashboards.py    # GET  /api/dashboards               (lists viz/*_live.html)
    settings.py      # GET/POST /api/settings, /api/info, /api/health, POST /api/browse_folder (native folder picker)
    jobs.py          # GET /api/jobs/catalog, POST /api/jobs, GET /api/jobs/{id}, /cancel, SSE /logs, /options/{provider}
  jobs/
    catalog.py       # declarative list of pipelines: single jobs, PARAM jobs (forms), CHAINS. + needs/hint text
    providers.py     # resolves param 'select'/'folder' options (aact_folders, snap:<kind>) newest-first
    runner.py        # subprocess runner: params->argv, chains (sequential, one log), cancel (CTRL_BREAK), per-run logs
    registry.py      # thread-safe in-memory run store
    dispatch.py      # frozen --run-pipeline dispatch (runpy) so jobs work in the exe
    services/classifier_service.py  # classify_one(payload) -> dict (builds ClinicalTrialSignalV2, runs 3 classifiers)
  web/
    index.html, app.css, app.js   # dark control-panel UI (vanilla JS, no framework); reuses the viz palette
    vendor/ (fonts copy)
core/
  paths.py           # SINGLE SOURCE OF TRUTH for paths (see below)
packaging/
  run_alexis.py      # PyInstaller entry: ensure_streams() + multiprocessing.freeze_support() BEFORE app.main:main
  alexis.spec        # one-folder, windowed; excludes *.tests; bundles viz/classifiers/policy/app-web/mesh? (see spec)
  alexis.iss         # Inno Setup installer (NOT yet compiled)
  build.ps1          # build helper
  alexis.ico         # benzene-ring app icon (tools/make_icon.py generates it)
tools/
  verify_portability.py, smoke_app.py, smoke_jobs.py, smoke_all_jobs.py, verify_pull_frozen.py,
  vendor_fonts.py, localize_dashboards.py, make_icon.py, run_app.py
```

### `core/paths.py` (read this first)
- `app_root()` — bundled, read-only assets: `sys._MEIPASS` when frozen, else repo root.
- `data_root()` — user's mutable data tree. Resolution: `ALEXIS_HOME` env var → `alexis_config.json` `data_dir` → default `%LOCALAPPDATA%\ALEXIS`. **`ALEXIS_HOME` overrides the config** (used by tests; real users don't set it).
- Accessors: `storage_dir(), snapshots_dir(), changelogs_dir(), raw_weekly_dir(), downloads_dir(), logs_dir()` (under data_root); `mesh_dir(), models_dir(), viz_dir(), policy_dir()` (under app_root, bundled).
- New-user helpers: `data_dir_is_valid()` (any existing dir — relaxed), `init_data_dir()` (creates storage skeleton), `data_dir_has_data()` (snapshots/master present?), `set_data_dir()` (writes config + inits), `config_path()`, `normalize_user_path()` (/mnt/c → C:\).

### Classifier (single-trial, no pkls)
`classifiers/{trial_modality_v2, therapeutic_area, drug_non_drug_v2}.py` + `policy/*` + MeSH JSON in `storage/mesh/`. `is_drug_trial_v2` reads `trial.interventions_all` (the service populates BOTH `interventions` and `interventions_all`). The sklearn `.pkl` models are used ONLY by the bulk intl pipelines (`classify_chictr/anzctr_to_snapshot`).

### Dashboards
`pipelines/generate_*_viz.py` read template `viz/alexis_weekly_dashboard.html`, concatenate `viz/*.jsx`, inject an `ALEXIS_DATA` JSON blob, write `viz/*_live.html` (self-contained React/Recharts via **vendored** libs in `viz/vendor/` — offline). The template uses the **classic JSX runtime** pragma and the **full weekly component set** (both were bugs causing blank dashboards — fixed).

---

## 4. Data Model & Pipelines

Data dir layout (under `data_root()`):
```
storage/snapshots/clinical_trials_v2/
  last_update/       # weekly US pulls (pulse_window / weekly_pulse)
  reclassified/      # reclassified snapshots
  chictr/  anzctr/   # international snapshots
  active_universe/   # master_DB_<year>_Q<n>.json (big) + AACT export folders (contain studies.txt)
storage/changelogs/  # changelog_* + enriched_* (weekly diffs)
downloads/           # drop AACT export zips here
logs/                # per-job logs
```

**Pipelines exposed as Pipelines-tab jobs** (`app/jobs/catalog.py`):
- US: `pull_weekly` (last 7 days), `pull_window` (custom date range: --days / --from/--to), **`pull_recent_weeks` (--weeks N, NEW bootstrap — pending commit)**, `enrich_weekly` (changelogs), `build_master` (from AACT folder; PARAM with a Browse/folder picker; ~200k trials, 30–60 min).
- China: `scrape_chictr` (Playwright), `scrape_chictr_details`, `classify_chictr`, `backfill_chictr`, `diff_chictr` (two-snapshot picker).
- Australia: `ingest_anzctr`, `classify_anzctr`, `backfill_anzctr`, `diff_anzctr`.
- Dashboards: `generate_weekly`, `generate_full` (all tabs).
- Maintenance: `reclassify_snapshot`, `patch_adc`, `backfill_source_fields`.
- Diagnostics: `self_test`.
- **Chains** (one-click, run steps in order): `refresh_weekly`, `refresh_chictr`, `refresh_anzctr`.

Most pipelines are non-interactive. `build_master_from_aact.py`, `generate_dashboard.py`, `generate_quarterly_viz.py`, `pulse_window_v1.py` got `--auto`/flag modes so they run without prompts. Trend charts use a **~3-week rolling average**, so a fresh data folder needs ~3 weekly snapshots before trends populate (hence `pull_recent_weeks`).

---

## 5. Build & Run

**Run from source (fast dev loop, full multi-core):**
```
cd <repo>
py -3.11 -m app                 # opens the desktop window
py -3.11 -m app --headless --port 18099   # browser/smoke mode (no window)
```

**Build the exe** (ALWAYS: app closed, no other build running, check `python3.11` procs are 0 first):
```
py -3.11 -m PyInstaller packaging/alexis.spec --noconfirm \
    --distpath C:/ALEXIS_build/dist --workpath C:/ALEXIS_build/work
```
Output: `C:\ALEXIS_build\dist\ALEXIS\ALEXIS.exe` (keep the whole folder — the exe loads `_internal`). ~3 min build (test modules excluded), ~25 MB exe.

**Build discipline (learned the hard way):**
- ONE build at a time. Never rebuild while the exe is open (PyInstaller rewrites `dist/` → "Access is denied" / "failed to extract archive" in the running app).
- Kill stray builds: `Get-Process python3.11,ALEXIS | Stop-Process -Force`. Stop background bash tasks with `TaskStop`.
- For test launches, use ONE bash command with `trap '<kill ALEXIS>' EXIT` and **bounded** wait-loops (`for i in $(seq 1 30); do ...; sleep 2; done`) — never unbounded `until` (orphans + spins forever).

**Tests** (against a running server):
```
py -3.11 tools/verify_portability.py --full   # paths/models/classifier (5/5)
py -3.11 tools/smoke_app.py --port <p>         # endpoints (15/15)
py -3.11 tools/smoke_jobs.py --port <p>        # job lifecycle (12/12)
py -3.11 tools/verify_pull_frozen.py --port <p># real pull completes w/ multiprocessing
```

**Installer:** `packaging/alexis.iss` (Inno Setup) is written but **not compiled** (`ISCC.exe packaging\alexis.iss`). It bootstraps the Edge WebView2 runtime + first-run data-folder picker.

**Shareable zip:** `C:\ALEXIS_build\ALEXIS.zip` — currently **stale/failing** (Windows Defender quarantines the fresh archive containing an unsigned exe). Not needed to run locally; for distribution, use 7-Zip or add a Defender exclusion.

---

## 6. New-User Onboarding (current behaviour)

A brand-new user with no data:
1. Default data folder is `%LOCALAPPDATA%\ALEXIS` (auto). The app shows a **3-state banner**:
   - no folder/invalid → "Choose a data folder (an empty one is fine)";
   - valid but **empty** → "Get started: Pull last 3 weeks (no download)";
   - has data → hidden.
2. **Browse** buttons (native pywebview folder dialog via `POST /api/browse_folder`) on the data-folder setting AND the AACT folder param. Any empty folder is accepted; `set_data_dir` creates the `storage/` skeleton.
3. Each pipeline card shows a **NEEDS** note; a "How this works" intro sits atop Pipelines.

**The exe was deliberately reset to a fresh new-user state** at handoff (config + `%LOCALAPPDATA%\ALEXIS` cleared). To point it at the real repo data: Settings → Browse/paste `\\wsl.localhost\Ubuntu\home\jeanmfc\projects\ALEXIS` → Save (or set `ALEXIS_HOME`).

---

## 7. Git / GitHub State

- Repo: `https://github.com/jeanmfc1/alexis`. Working branch: `chore/cleanup`.
- Merged to `main`: PR #1 (cleanup → desktop app → operator console) and PR #2 (date-range pull, multiprocessing-in-exe fix, icon, faster builds, data-folder UX, new-user onboarding). `origin/main` head `8adad46`.
- **Security:** a GitHub PAT was found embedded in `.git/config` and scrubbed; the remote is now a clean URL. User re-ran `gh auth login` (keyring). The old token should be revoked on GitHub if not already.
- **Uncommitted at handoff:** the `pull_recent_weeks` / `--weeks` bootstrap (see §0). Also long-standing **pre-existing WIP** that is intentionally untouched: `collectors/clinicaltrials/clinicaltrials_fetch.py`, `config/settings.py`, and new `analytics/*_aw1.py`, `pipelines/*anzctr*`, `viz/*_aw1.jsx` (Jean's ANZCTR work — do NOT commit without checking).

---

## 8. Key Decisions & Hard-Won Lessons

- **DO NOT change the classification execution model.** Multiprocessing (`utils/parallel_processor.py` + the raw `Pool` in `chunk_reclassify_modality_snapshot_v2.py`) is deliberately tuned; single-threading the full DB is unacceptable. When the frozen exe crashed during classification, the fix was packaging-level, not parallelism:
  - `multiprocessing.freeze_support()` first thing in `packaging/run_alexis.py` (workers re-launch the exe; without it → "failed to extract archive" storm).
  - `ensure_streams()` BEFORE `freeze_support()` — windowed-exe workers have `sys.stdout/stderr = None`; without streams they crash in `_bootstrap` ("'NoneType' has no attribute 'write'") and pop error dialogs.
  - utf-8 stdio: `PYTHONUTF8=1` in the child env (`runner._child_env`) + `ensure_streams` reconfigures existing streams to utf-8 (windowed pipes default to cp1252 → unicode like `→`/box chars crash).
  - `disable_windowed_traceback=True` in the spec (no crash dialogs ever).
- **Build perf:** the spec filters `*.tests` submodules of sklearn/scipy/pandas (`_no_tests`), cutting Analysis from ~15 min to ~3 and the exe from ~42 MB to ~25 MB. Keep it.
- **Blank dashboards** were two bugs: missing weekly components (generate_weekly only injected 4 of 7) and Babel defaulting to the automatic JSX runtime (emits an unresolvable `import`). Fixed with the full component set + a `@jsxRuntime classic` pragma in the template.
- **Offline:** React/ReactDOM/Recharts/prop-types/Babel + Google fonts are vendored under `viz/vendor/` (and `app/web/vendor/` for the shell) so nothing needs the network.

(These lessons are also in this session's memory files: `alexis-preserve-multiprocessing`, `alexis-windows-build-ops`.)

---

## 9. Verification Status

Verified in the **packaged exe**: app boots (`is_frozen=true`), classifier works (Enhertu→adc/Oncology), dashboards render offline, `pull_window --days 1` completes with **7 parallel workers** (~92 s, snapshot saved, no crashes), jobs + chains start/stream/cancel cleanly, new-user empty folder accepted + initialised. Source-mode UI verified via screenshots (Pipelines intro, NEEDS notes, AACT folder picker with Browse, setup banner).

Not yet verified end-to-end: the `--weeks N` bootstrap loop (test in flight at handoff), `generate_full` to completion in the exe, the Inno installer, the international (ChiCTR/ANZCTR) chains in the exe.

---

## 10. Open Items / Next Steps

1. **Finish the `pull_recent_weeks` bootstrap:** confirm `--weeks 1` saved a snapshot, commit (`pipelines/pulse_window_v1.py`, `app/jobs/catalog.py`, `app/web/{app.js,index.html}`), rebuild, push + merge.
2. **Update `SETUP.md`** to the new from-scratch onboarding (choose any folder → Pull last 3 weeks → Generate).
3. **Shareable distribution:** fix the zip (7-Zip / Defender exclusion) or compile the Inno installer; consider **code-signing** to kill SmartScreen/AV warnings.
4. **Exercise the intl chains** (ChiCTR needs `playwright install chromium`; ANZCTR needs the Excel export) once in the exe.
5. Optional: a proper full-coverage sweep of every job in the exe (harness exists: `tools/smoke_all_jobs.py`, but it cancels heavy jobs — run it gently, not while distracted, since cancelling multiprocessing jobs is noisy).

---

## 11. Quick Reference

- Run: `py -3.11 -m app` · Build: `py -3.11 -m PyInstaller packaging/alexis.spec --noconfirm --distpath C:/ALEXIS_build/dist --workpath C:/ALEXIS_build/work`
- Exe: `C:\ALEXIS_build\dist\ALEXIS\ALEXIS.exe` · Data (Jean): `\\wsl.localhost\Ubuntu\home\jeanmfc\projects\ALEXIS`
- Process check: `Get-Process python3.11,ALEXIS` (NOT python.exe). Kill: `... | Stop-Process -Force`.
- GitHub: `gh pr ...` (re-auth done) · branch `chore/cleanup` → `main`.

*Confirm file/process/git state before acting — this app has a lot of moving parts and the build is sensitive to concurrent runs.*
