# ALEXIS packaged-app (.exe) — status, real problems, and missing context

**Written:** 2026-06-24 by Claude Code (the session that kept getting the build wrong).
**Purpose:** hand-off to another session. Plain English. Read top to bottom.

Terms used below:
- **Packaged app / frozen build / the .exe** = `ALEXIS.exe`, the single Windows program PyInstaller bundles from the source code.
- **`app_root`** = where the *program's bundled code* lives. When packaged this is the `_internal` folder next to the .exe.
- **`data_root`** = where the *user's data* lives. When packaged this is a **local Windows folder** (default `%LOCALAPPDATA%\ALEXIS`, or whatever the user picks in Settings). **`app_root` and `data_root` are DIFFERENT folders in the packaged app.** In a plain source checkout they happen to be the same folder (the repo), which is why these bugs are invisible until you package it.

---

## 0. The one correction that matters most

I earlier claimed the packaged app had silently dropped to **single-core** classification (which would violate the project's #1 rule). **That claim was WRONG.** I tested it on the live packaged app:

- During a pull, `ALEXIS.exe` process count went **2 → 9** (parent + 7 workers) and held for the whole classification, log said *"Processing 3280 trials with 7 parallel workers."*

**Multiprocessing is fine. Do NOT change the parallelism.** This matches your own observation ("I've seen it use many cores").

Why the audit got it wrong: it reasoned (without running it) that the worker function is defined in the `__main__` module and therefore can't be reconstructed in spawned worker processes. It missed that the dispatcher runs pipelines via `runpy.run_module(..., alter_sys=True)`, which gives the pipeline a real importable module identity, so `multiprocessing`'s spawn machinery *can* rebuild it in workers. Lesson: the multiprocessing findings were **theory**; the path findings below are **observed fact**. Treat them differently.

**Consequence:** the audit's two "high-severity multiprocessing" findings are both suspect:
- "pulls run single-core" — **refuted empirically** (7 workers ran).
- "`reclassify_snapshot` hard-crashes" — **same flawed premise, so probably also false, but NOT directly tested.** Someone should actually run `reclassify_snapshot` in the packaged app before changing a single line of its parallelism.

---

## 1. The bug you originally reported — FIXED

The "Refresh weekly US data" chain crashed at step 2 with
`ImportError: can't find '__main__' module in '...\_internal\pipelines\backfill_enriched_weekly.py'`.

- **Cause:** the job dispatcher ran "script" jobs with `runpy.run_path(<path inside the bundle>)`. PyInstaller's bundle makes that call hunt for a non-existent `__main__` sub-module. Every `script:`-type job hit this; only `enrich_weekly` sits in a chain, so that's what you saw.
- **Fix (done, verified in the packaged app):** [app/jobs/dispatch.py](app/jobs/dispatch.py) now runs those jobs by *module name* (`runpy.run_module`), the same mechanism the working "module" jobs already use, with a file-exec fallback for the one script bundled as a data file (`tools/verify_portability.py`). Verified: `enrich_weekly` now loads and runs (`rc=0`).

The "date range / 3 weeks / master DB missing" symptoms were just a **stale .exe** — the current source already has those jobs; a correct rebuild shows all of them.

---

## 2. The REAL remaining problem — "wrong data location" when packaged (confirmed)

Several pipelines look for data **inside the program folder (`app_root`/`_internal`) instead of the user's data folder (`data_root`).** This is invisible in a source run (same folder) but **breaks in the packaged app**, where the two folders differ — and it's worse now that we know the real deployment uses a **local data folder**, because then the program folder may even be read-only (e.g. under `Program Files`).

I **directly observed** this: running `enrich_weekly` in the packaged app printed
`Pulse dir: C:\ALEXIS_build\dist\ALEXIS\_internal\storage\...\last_update` and found **0 pulses**, because it looked inside the bundle instead of the data folder.

Two underlying mechanisms:

**(A) Relative paths** like `Path("storage/...")` — resolved against the process *working directory*, which the job runner sets to the bundle ([app/jobs/runner.py:55](app/jobs/runner.py) `cwd=str(app_root())`).
**(B) Paths built from the code's own location** — `ROOT = Path(__file__).parent.parent`; when packaged, `__file__` is inside the bundle, so `ROOT` becomes `_internal`.

### Confirmed affected jobs (from the audit; path logic is deterministic)

| Job | File | Mechanism |
|---|---|---|
| `pull_weekly` (+`refresh_weekly`) | pipelines/weekly_pulse_clinical_v2.py:331 | (A) relative `base_dir` for snapshot save — writes pull into the bundle |
| `enrich_weekly` (+`refresh_weekly`) | pipelines/backfill_enriched_weekly.py:46 | (B) `ROOT`-from-`__file__` for pulse/master/changelog dirs |
| `reclassify_snapshot` | pipelines/chunk_reclassify_modality_snapshot_v2.py:52,432 | (A) relative checkpoint dir + relative `--out` default |
| `build_master` | pipelines/build_master_from_aact.py:1052 | (A) relative MeSH path → MeSH IDs silently go blank |
| `generate_full`/`refresh_anzctr` | pipelines/generate_anzctr_viz.py:19 | (B) — Australia dashboard tab reads from bundle (**Jean's WIP file**) |
| `generate_full`/`refresh_chictr` | pipelines/generate_chictr_viz.py:19 | (B) — China dashboard tab reads from bundle (**Jean's WIP file**) |
| `ingest_anzctr` (+`refresh_anzctr`) | pipelines/ingest_anzctr_xlsx.py:24 | (A) relative xlsx/parquet defaults (**Jean's WIP file**) |
| `backfill_anzctr` (+`refresh_anzctr`) | pipelines/backfill_anzctr_snapshots.py:22 | (A) relative snapshot dir (**Jean's WIP file**) |
| `backfill_chictr` | pipelines/backfill_chictr_snapshots.py:39 | (A) relative snapshot dir |
| `diff_anzctr` | pipelines/diff_anzctr_snapshots.py:118 | (A) relative `--out-dir` default |
| `diff_chictr` | pipelines/diff_chictr_snapshots.py:275 | (A) relative `--out-dir` default |
| `patch_adc` | pipelines/patch_adc_modality.py:26 | (B) `ROOT`-from-`__file__` |
| `backfill_source_fields` | pipelines/backfill_source_fields.py:74 | (A) relative default master path |

Jobs already correct (use `core.paths`, the shared accessor that resolves `data_root`): `pull_window`, `pull_recent_weeks`, `generate_weekly`, `generate_full`'s own paths, `build_master` (except MeSH), `classify_*`.

### The clean fix (recommended approach for the other session)
- **One high-leverage change:** make the job runner set the child working directory to **`data_root()`** instead of `app_root()` ([app/jobs/runner.py:55](app/jobs/runner.py)), with a fallback to `app_root()` if `data_root` doesn't exist yet. That single change fixes every **(A) relative-path** job at once. I checked: **no pipeline reads a *bundled* asset (viz template, models, policy) via a relative path**, so this is safe.
- **Per-file `core.paths` edits** for the **(B) `__file__`-based** jobs: `backfill_enriched_weekly` (started — see §4), `patch_adc`, `generate_anzctr_viz`, `generate_chictr_viz`. Copy the pattern already used in `generate_weekly_viz.py` (use `Path(__file__)` only to fix the import path; get data dirs from `core.paths.snapshots_dir()/changelogs_dir()/storage_dir()`).
- **`enrich_weekly` also shells out** via `sys.executable -m analytics.update_categorizer`; in the packaged app `sys.executable` is `ALEXIS.exe`, which can't run `-m`. Needs a packaged-safe path (see §4).

---

## 3. The problems *I* was having (so the next session avoids them)

1. **I can't build cleanly in this environment.** The repo is on a WSL network path (`\\wsl.localhost\...`). Through my shell (Git Bash → PowerShell) the backslashes get mangled (JSON + shell escaping), and Windows tools dislike a network-path "current directory." That produced several dead builds before I switched to forward-slash paths.
2. **The build's working directory is load-bearing, and I didn't know it.** The packaging spec calls `collect_submodules('pipelines')`, which only works if the repo is importable at build time. I ran the build from `C:\ALEXIS_build` (to dodge problem #1), which silently produced builds **missing the entire `pipelines` package** — they "succeeded" but were hollow. Fixed by setting `PYTHONPATH=<repo>`, but **the project already has `packaging/build.ps1` which does this correctly (`Set-Location $Root` + a scikit-learn version check), and I bypassed it.** The next session should just use `build.ps1` from the repo root.
3. **Builds are slow (~3–4 min) and serialized** (can't rebuild while the app is open), so every wrong iteration was expensive.
4. **I over-claimed "fixed" before verifying in the packaged form**, twice. The only trustworthy check is running the actual `.exe`.

---

## 4. Exact state of the working tree right now (uncommitted)

- **`app/jobs/dispatch.py`** — fully fixed, verified in the packaged app. Good to keep.
- **`pipelines/backfill_enriched_weekly.py`** — **half-edited, currently inconsistent.** I changed its data paths to `core.paths` (good) and made `_run_categorizer` call `ALEXIS.exe --run-module analytics.update_categorizer` when packaged — **but I did NOT yet add a `--run-module` handler to `app/__main__.py`.** So as it stands, in the packaged app the enrich step's sub-process call would fail. **Either** add the `--run-module` handler to [app/__main__.py](app/__main__.py) (next to the existing `--run-pipeline` handler, ~line 44) **or** revert the `_run_categorizer` change and run `update_categorizer` in-process. I stopped before finishing this.
- **Memory:** added `comm-plain-english` (you asked for plain-English replies).
- **Builds in `C:\ALEXIS_build\dist`:** the newest good one is from ~10:22 and contains **only** the dispatch fix (not the path fixes). Build from the repo root with `build.ps1` to get a clean one.
- **Everything else** (Jean's ANZCTR/ChiCTR WIP, etc.) is untouched by me.

---

## 5. Your answers (decisions locked in)

1. **Scope = everything**, including the in-progress China/Australia files (`generate_anzctr_viz.py`, `generate_chictr_viz.py`, `ingest_anzctr_xlsx.py`, `backfill_anzctr_snapshots.py`).
2. **Build duty:** you build & test; the assistant produces correct, reviewed code changes.
3. **Data folder = a local Windows folder** (default `%LOCALAPPDATA%\ALEXIS`). **Important for testing:** verify against a **local** data folder, NOT the WSL repo path — the bugs only show when `app_root` ≠ `data_root`, which a local folder guarantees and the UNC repo (what I tested against) partly masked.
4. **Multi-core = works** (confirmed both by you and by the 7-worker test). Don't touch parallelism.

---

## 6. What I'd still want to know / watch (open context gaps)

- **Is `data_root` ever read-only in practice?** (e.g. app installed under `Program Files`, data under `%LOCALAPPDATA%`.) Affects whether wrong-location writes *fail loudly* or *just go to the wrong place silently*.
- **Does `reclassify_snapshot` actually run in the packaged app?** (Direct test needed — the audit's crash claim is unverified and probably wrong, same as the pull claim.)
- **Should the verifier `tools/verify_pull_frozen.py` be hardened?** It only checks for the "starting N workers" line; if a real single-core fallback ever happened it wouldn't notice. Worth a small fix so future checks aren't fooled.
- **Confirm `build.ps1` is the canonical build path** and that the scikit-learn 1.6.x pin still holds on the build machine.

---

## 7. UPDATE (2026-06-24, later) — fixes APPLIED, ready to build & test

All the code changes below are **done and committed to the working tree** (not git-committed). I verified them in **source mode only** — I did **not** build the `.exe` (that's your side: `you build, I test`).

### Files changed
| File | Change |
|---|---|
| `app/jobs/runner.py` | **The linchpin.** Child working dir is now `data_root()` (fallback `app_root()` if it doesn't exist) via new `_run_cwd()`, instead of `app_root()`. Fixes EVERY relative-path (A) job at once: `pull_weekly`, `reclassify_snapshot`, `build_master` (MeSH), `ingest_anzctr`, `backfill_anzctr`, `backfill_chictr`, `diff_anzctr`, `diff_chictr`, `backfill_source_fields`. |
| `app/__main__.py` | Added `--run-module <mod> [args]` handler next to `--run-pipeline` (runpy, `run_name="__main__"`). Lets the packaged enrich step run `analytics.update_categorizer` as a fresh subprocess. |
| `pipelines/backfill_enriched_weekly.py` | (B) data dirs now via `core.paths`; `_run_categorizer` uses `ALEXIS.exe --run-module` when frozen. (`update_categorizer` confirmed non-interactive — no `input()`.) |
| `pipelines/patch_adc_modality.py` | (B) `SNAPSHOT_BASE`/`cl_dir` via `core.paths`. |
| `pipelines/generate_anzctr_viz.py` | (B) ANZCTR dirs via `core.paths` (copied `generate_weekly_viz.py` pattern). |
| `pipelines/generate_chictr_viz.py` | (B) ChiCTR dirs via `core.paths`. |
| `tools/verify_pull_frozen.py` | Hardened: now FAILS unless `workers > 1` AND the log has no single-process fallback marker. |
| `app/jobs/dispatch.py` | (earlier) the original crash fix — already verified in the packaged app. |
| `pipelines/classify_chictr_to_snapshot.py` | Fixed **3.12-only f-string syntax** (lines 668/673: `f"...{str(phase or "None")}..."`). It compiles in the WSL 3.12 `.venv` but is a `SyntaxError` under the 3.11 build, so PyInstaller dropped it as an "invalid module" → `classify_chictr`/`refresh_chictr` failed with `No module named pipelines.classify_chictr_to_snapshot`. A repo-wide 3.11 compile sweep (841 files) found this was the ONLY such file; now 0. |
| `packaging/build.ps1` | (versioned builds) + **compile-check gate**: `compileall` under 3.11 before PyInstaller, so any future 3.12-syntax file fails the build loudly instead of being silently dropped. |

No per-file edits were needed for the (A) jobs — the runner-CWD change covers them.

### Verified in source mode (green) — `C:\ALEXIS_build\verify_edits.py`
With `ALEXIS_HOME=C:\ALEXIS_test_data` (so `app_root` ≠ `data_root`, mimicking frozen): all 7 files compile; all (B) constants and the runner CWD resolve under `data_root`, none under `app_root`.

### What YOU still need to test in the packaged `.exe` (I cannot, by design)
Build with `packaging\build.ps1` **from the repo root**, then point the data folder at a **local** path (e.g. `C:\ALEXIS_data`, via Settings→Browse or `ALEXIS_HOME`) and confirm:

> Builds are now **versioned**: each lands in `C:\ALEXIS_build\dist\<timestamp>_<sha>\ALEXIS\ALEXIS.exe` and never overwrites a prior one. `C:\ALEXIS_build\dist\latest\ALEXIS\ALEXIS.exe` (a junction) always points at the newest; `dist\builds.log` lists them.

1. `pull_weekly` → snapshot lands in `C:\ALEXIS_data\storage\snapshots\...\last_update\` (NOT in `...\dist\latest\ALEXIS\_internal\storage\`).
2. `enrich_weekly` then finds those pulses (no more "0 pulses"); changelog/enriched files land in `C:\ALEXIS_data\storage\changelogs\`.
3. Full `refresh_weekly` chain produces a populated weekly dashboard.
4. `reclassify_snapshot` runs (still 7 workers — confirm parallelism) and writes output to the data folder.
5. Re-run `tools/verify_pull_frozen.py` — should still PASS (now also proving multi-core).

### Loose ends / do not forget
- **Mixed uncommitted tree:** my fixes sit alongside the other session's validated-but-uncommitted work (the `pull_recent_weeks` "Pull last 3 weeks" bootstrap in `pulse_window_v1.py`/`catalog.py`/`app.js`/`index.html`, plus `generate_weekly_viz.py`/`generate_quarterly_viz.py` path fixes, plus `HANDOFF.md`). Review/commit together.
- **Throwaway test artifacts (outside the repo):** `C:\ALEXIS_test_data\` (a ready local data folder for your test) and `C:\ALEXIS_build\verify_edits.py` (re-runnable source-mode check). Delete or reuse.
- **Encoding:** the enrich `--run-module` subprocess inherits `PYTHONUTF8=1` from the runner env, so the `✓`/`×` prints stay safe. Don't introduce a dispatch path that bypasses the runner env.
- **Parallelism: still untouched.** Confirmed working (7 workers); the audit's single-core claim was false.
