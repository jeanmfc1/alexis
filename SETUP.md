# ALEXIS — Setup & User Guide

ALEXIS is a desktop app for clinical-trial intelligence: it classifies trials by
drug **modality** and **therapeutic area**, generates the BD / Marketing /
Operations / Scientific dashboards, and runs the data pipelines — all from one
window.

There are two audiences below: **Just want to use it?** start at Part 1.
**Building or developing it?** jump to Part 3.

---

## Part 1 — Install & run (for anyone)

1. **Run the installer** `ALEXIS-Setup.exe` and follow the prompts. It installs
   to your user profile (no admin rights needed) and adds an **ALEXIS** shortcut
   to the Start Menu (and your desktop if you tick the box).
   - If your PC doesn't already have Microsoft's *Edge WebView2* component, the
     installer adds it automatically. (It's what draws the app window.)
2. **Launch ALEXIS** from the Start Menu. The first launch takes ~10 seconds.
3. **Point it at your data folder** (first run only):
   - Go to the **Settings** tab.
   - Click **Change data folder…** and choose the folder that contains your
     ALEXIS `storage` folder (the one with `storage/snapshots`, `storage/mesh`,
     etc.). Click **Save**. The badge turns **valid**.
   - That's it — your choice is remembered.

You never need a terminal, Python, or the internet to use ALEXIS.

---

## Part 2 — Using the app

The left sidebar has four sections:

- **Dashboards** — open the generated BD / Marketing / Ops / Scientific
  dashboards in a frame. Click **Open** on any card. They work fully offline.
- **Classifier** — paste a single trial (title + at least one intervention) and
  get its modality, therapeutic area, and drug-trial flag instantly. Use
  **Load example** to try it with a known trial (e.g. Enhertu → ADC, oncology).
- **Jobs** — run the pipelines in the background and watch their logs live:
  - *Generate weekly dashboard* rebuilds the weekly view from your newest data.
  - *Classify ChiCTR / ANZCTR → snapshot* runs the international classifiers.
  - *Self-tests* confirm everything is wired correctly on your machine.
  - Each run streams to the console; click **Cancel** to stop one early. When a
    dashboard job finishes, the Dashboards list refreshes automatically.
- **Settings** — your data folder, plus where config and logs live.

If the top-left status dot goes red ("offline"), the app's internal service
stopped — close and reopen ALEXIS.

---

## Part 3 — Run from source (developers)

Requires **Windows Python 3.11** (the classifier models are pinned to
scikit-learn 1.6.1).

```powershell
cd <repo>
py -3.11 -m pip install -r requirements-app.txt
py -3.11 -m app                 # opens the desktop window
py -3.11 -m app --headless      # serves on a localhost port for a browser
```

Self-checks:

```powershell
py -3.11 tools\verify_portability.py --full   # paths, mesh, models, classifier
py -3.11 tools\smoke_app.py                    # every API endpoint
py -3.11 tools\smoke_jobs.py                   # the job runner + live logs
```

In source mode the "data folder" defaults to the repo itself, so the app finds
`storage/` automatically.

---

## Part 4 — Build the .exe and installer

```powershell
cd <repo>
py -3.11 -m pip install -r requirements-app.txt   # includes pyinstaller
.\packaging\build.ps1
# -> C:\ALEXIS_build\dist\ALEXIS\ALEXIS.exe   (one-folder build)

# smoke test the frozen build:
& 'C:\ALEXIS_build\dist\ALEXIS\ALEXIS.exe' --headless --port 18099
```

Then make the installer with **Inno Setup 6.1+**:

```powershell
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' packaging\alexis.iss
# -> packaging\Output\ALEXIS-Setup.exe
```

What ships inside the exe vs. what stays external:

| Bundled in the exe (read-only)          | Comes from your data folder        |
|-----------------------------------------|------------------------------------|
| App code, web UI, dashboard template    | `storage/snapshots/…` (the trials) |
| Vendored React/Recharts/fonts (offline) | `storage/mesh/…` (~120 MB lookups) |
| Classifier models (`*.pkl`, ~61 MB)     | `storage/changelogs/…`             |

This keeps the installer small; the multi-GB data stays in your folder.

---

## Part 5 — Troubleshooting

- **Blank app window** → the Edge WebView2 runtime is missing. Install it from
  https://developer.microsoft.com/microsoft-edge/webview2/ and relaunch.
- **Settings says the data folder is "invalid"** → pick a folder that directly
  contains a `storage` subfolder.
- **Dashboards list is empty** → generate one from the **Jobs** tab
  ("Generate weekly dashboard"), or confirm your data folder has snapshots.
- **A classify job fails immediately** → those need the MeSH data and models;
  make sure your data folder has `storage/mesh`. Open the job's console for the
  exact error.
- **Logs** live in `…\ALEXIS\logs\` under your data folder; config is
  `alexis_config.json` in `%LOCALAPPDATA%\ALEXIS`.
- **Windows SmartScreen warning** on the unsigned installer → "More info" →
  "Run anyway". Code-signing removes this (see below).

---

## Notes / future work

- The exe is currently **unsigned**; signing it (and the installer) removes the
  SmartScreen prompt for end users.
- Scraping jobs (ChiCTR/ANZCTR collection) need Playwright:
  `py -3.11 -m pip install playwright && py -3.11 -m playwright install chromium`.
