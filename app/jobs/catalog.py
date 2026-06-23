"""Declarative catalog of runnable pipelines, parameter forms, and chains.

A catalog entry is one of:

* SINGLE job  -> ``module`` XOR ``script`` + ``argv`` (+ optional ``params``).
* CHAIN job   -> ``steps``: an ordered list of other job ids run in sequence.

PARAMS let the GUI render a small form. Each param:
    {name, label, type, flag, required, default, provider}
  type     : "select" | "text" | "date" | "int" | "bool"
  flag     : the CLI flag the value maps to (e.g. "--snapshot"). bool flags are
             emitted with no value when true.
  provider : for type "select", a key the backend resolves to a list of options
             (see app/jobs/providers.py), e.g. "aact_folders", "snap:chictr".

The runner turns this into a command. In a frozen build every job launches via
``ALEXIS.exe --run-pipeline <id> [--param ...]`` and app.__main__ dispatches it.
"""

from __future__ import annotations

import sys

from core.paths import is_frozen


CATALOG: list[dict] = [
    # ───────────────────────── One-click chains ─────────────────────────
    {
        "id": "refresh_weekly",
        "label": "Refresh weekly US data",
        "description": "Pull this week's ClinicalTrials.gov trials, compute what changed, "
                       "and rebuild the weekly dashboard.",
        "category": "chain",
        "ready": True, "long_running": True, "produces": "alexis_weekly_dashboard_live.html",
        "steps": ["pull_weekly", "enrich_weekly", "generate_weekly"],
    },
    {
        "id": "refresh_chictr",
        "label": "Refresh China (ChiCTR)",
        "description": "Classify the latest scraped ChiCTR data into a snapshot, backfill "
                       "history, and rebuild the full dashboard. (Scrape first if you need new data.)",
        "category": "chain",
        "ready": True, "long_running": True, "produces": "alexis_dashboard_live.html",
        "steps": ["classify_chictr", "backfill_chictr", "generate_full"],
    },
    {
        "id": "refresh_anzctr",
        "label": "Refresh Australia (ANZCTR)",
        "description": "Ingest the downloaded ANZCTR Excel, classify it, backfill history, "
                       "and rebuild the full dashboard.",
        "category": "chain",
        "ready": True, "long_running": True, "produces": "alexis_dashboard_live.html",
        "steps": ["ingest_anzctr", "classify_anzctr", "backfill_anzctr", "generate_full"],
    },

    # ───────────────────────── US trials (AACT / CT.gov) ─────────────────
    {
        "id": "pull_weekly",
        "label": "Pull this week's US trials",
        "description": "Fetch + classify the last 7 days from ClinicalTrials.gov into a weekly snapshot.",
        "category": "us", "ready": True, "long_running": True, "produces": "weekly snapshot",
        "module": "pipelines.weekly_pulse_clinical_v2", "argv": [],
    },
    {
        "id": "enrich_weekly",
        "label": "Compute weekly changes",
        "description": "Diff each weekly snapshot against the right master DB to mark genuinely-new trials.",
        "category": "us", "ready": True, "long_running": True, "produces": "changelog + enriched",
        "script": "pipelines/backfill_enriched_weekly.py", "argv": [],
    },
    {
        "id": "build_master",
        "label": "Build master database (from AACT)",
        "description": "Build the full master DB from a downloaded AACT export folder. "
                       "Run occasionally (e.g. quarterly).",
        "category": "us", "ready": True, "long_running": True, "produces": "master_DB_*.json",
        "module": "pipelines.build_master_from_aact",
        "argv": [],
        "params": [
            {"name": "aact_dir", "label": "AACT export folder", "type": "select",
             "flag": "--aact-dir", "provider": "aact_folders", "required": True},
            {"name": "out", "label": "Output name", "type": "text",
             "flag": "--out", "required": False, "default": "master_DB.json"},
            {"name": "fresh", "label": "Ignore checkpoints (start fresh)", "type": "bool",
             "flag": "--fresh", "default": False},
        ],
    },

    # ───────────────────────── China (ChiCTR) ───────────────────────────
    {
        "id": "scrape_chictr",
        "label": "Scrape ChiCTR (list pages)",
        "description": "Drive a browser to collect ChiCTR trial stubs. Needs Playwright; "
                       "can take a long time. Use the day window to limit it.",
        "category": "chictr", "ready": True, "long_running": True, "produces": "chictr stubs",
        "module": "pipelines.scrape_chictr_playwright",
        "argv": ["--headless"],
        "params": [
            {"name": "limit", "label": "Max trials (blank = all)", "type": "int",
             "flag": "--limit", "required": False},
        ],
    },
    {
        "id": "scrape_chictr_details",
        "label": "Scrape ChiCTR (detail pages)",
        "description": "Fetch the full detail page for each scraped stub. Needs Playwright.",
        "category": "chictr", "ready": True, "long_running": True, "produces": "chictr details",
        "module": "pipelines.scrape_chictr_details", "argv": ["--resume"],
    },
    {
        "id": "classify_chictr",
        "label": "Classify ChiCTR -> snapshot",
        "description": "Run the drug + TA classifiers over the scraped ChiCTR data into a snapshot.",
        "category": "chictr", "ready": True, "long_running": True, "produces": "ChiCTR snapshot",
        "module": "pipelines.classify_chictr_to_snapshot", "argv": [],
    },
    {
        "id": "backfill_chictr",
        "label": "Backfill ChiCTR history",
        "description": "Create synthetic prior snapshots so momentum/trend charts have a baseline.",
        "category": "chictr", "ready": True, "long_running": False, "produces": "synthetic snapshots",
        "module": "pipelines.backfill_chictr_snapshots", "argv": [],
    },
    {
        "id": "diff_chictr",
        "label": "Diff two ChiCTR snapshots",
        "description": "Compare two ChiCTR snapshots to produce the changelog + enriched file.",
        "category": "chictr", "ready": True, "long_running": False, "produces": "chictr changelog",
        "script": "pipelines/diff_chictr_snapshots.py", "argv": [],
        "params": [
            {"name": "prior", "label": "Prior snapshot", "type": "select",
             "flag": "--prior", "provider": "snap:chictr", "required": True, "default_index": 1},
            {"name": "current", "label": "Current snapshot", "type": "select",
             "flag": "--current", "provider": "snap:chictr", "required": True, "default_index": 0},
        ],
    },

    # ───────────────────────── Australia (ANZCTR) ───────────────────────
    {
        "id": "ingest_anzctr",
        "label": "Ingest ANZCTR Excel",
        "description": "Flatten the downloaded ANZCTR Excel export into a table for classification.",
        "category": "anzctr", "ready": True, "long_running": False, "produces": "anzctr_flat.parquet",
        "module": "pipelines.ingest_anzctr_xlsx", "argv": [],
    },
    {
        "id": "classify_anzctr",
        "label": "Classify ANZCTR -> snapshot",
        "description": "Run the drug + TA classifiers over the ANZCTR data into a snapshot.",
        "category": "anzctr", "ready": True, "long_running": True, "produces": "ANZCTR snapshot",
        "module": "pipelines.classify_anzctr_to_snapshot", "argv": [],
    },
    {
        "id": "backfill_anzctr",
        "label": "Backfill ANZCTR history",
        "description": "Create synthetic prior snapshots (monthly cadence) for trend baselines.",
        "category": "anzctr", "ready": True, "long_running": False, "produces": "synthetic snapshots",
        "module": "pipelines.backfill_anzctr_snapshots", "argv": [],
    },
    {
        "id": "diff_anzctr",
        "label": "Diff two ANZCTR snapshots",
        "description": "Compare two ANZCTR snapshots to produce the changelog + enriched file.",
        "category": "anzctr", "ready": True, "long_running": False, "produces": "anzctr changelog",
        "script": "pipelines/diff_anzctr_snapshots.py", "argv": [],
        "params": [
            {"name": "prior", "label": "Prior snapshot", "type": "select",
             "flag": "--prior", "provider": "snap:anzctr", "required": True, "default_index": 1},
            {"name": "current", "label": "Current snapshot", "type": "select",
             "flag": "--current", "provider": "snap:anzctr", "required": True, "default_index": 0},
        ],
    },

    # ───────────────────────── Dashboards ───────────────────────────────
    {
        "id": "generate_weekly",
        "label": "Generate weekly dashboard",
        "description": "Rebuild the weekly dashboard from the newest snapshot/enriched/master.",
        "category": "dashboard", "ready": True, "long_running": True,
        "produces": "alexis_weekly_dashboard_live.html",
        "module": "pipelines.generate_weekly_viz", "argv": ["--auto", "--no-open"],
    },
    {
        "id": "generate_full",
        "label": "Generate full dashboard (all tabs)",
        "description": "Rebuild the unified dashboard: weekly + quarterly + ChiCTR + ANZCTR tabs.",
        "category": "dashboard", "ready": True, "long_running": True,
        "produces": "alexis_dashboard_live.html",
        "module": "pipelines.generate_dashboard", "argv": ["--auto", "--no-open"],
    },

    # ───────────────────────── Maintenance ──────────────────────────────
    {
        "id": "reclassify_snapshot",
        "label": "Reclassify a snapshot",
        "description": "Re-run drug/TA/modality classification on a chosen snapshot.",
        "category": "maintenance", "ready": True, "long_running": True, "produces": "reclassified snapshot",
        "script": "pipelines/chunk_reclassify_modality_snapshot_v2.py", "argv": [],
        "params": [
            {"name": "snapshot", "label": "Snapshot to reclassify", "type": "select",
             "flag": "--snapshot", "provider": "snap:active_universe", "required": True},
        ],
    },
    {
        "id": "patch_adc",
        "label": "Patch ADC modality",
        "description": "Relabel antibody-drug-conjugate trials across snapshots (text signals).",
        "category": "maintenance", "ready": True, "long_running": False, "produces": None,
        "script": "pipelines/patch_adc_modality.py", "argv": [],
    },
    {
        "id": "backfill_source_fields",
        "label": "Backfill provenance fields",
        "description": "Add modality_source / therapeutic_area_source provenance to the master DB.",
        "category": "maintenance", "ready": True, "long_running": False, "produces": None,
        "script": "pipelines/backfill_source_fields.py", "argv": [],
    },

    # ───────────────────────── Diagnostics ──────────────────────────────
    {
        "id": "self_test",
        "label": "Run self-test",
        "description": "Confirm paths, models, and the classifier all work on this machine.",
        "category": "diagnostic", "ready": True, "long_running": False, "produces": None,
        "script": "tools/verify_portability.py", "argv": ["--full"],
    },
]

_BY_ID = {e["id"]: e for e in CATALOG}

_PUBLIC_KEYS = ("id", "label", "description", "category",
                "long_running", "ready", "produces")


def get_catalog() -> list[dict]:
    """JSON-ready entries for the UI, including param specs and chain steps."""
    out = []
    for e in CATALOG:
        d = {k: e.get(k) for k in _PUBLIC_KEYS}
        if e.get("params"):
            d["params"] = e["params"]
        if e.get("steps"):
            d["steps"] = e["steps"]
            d["is_chain"] = True
        out.append(d)
    return out


def get_entry(job_id: str) -> dict | None:
    return _BY_ID.get(job_id)


def is_chain(job_id: str) -> bool:
    e = _BY_ID.get(job_id)
    return bool(e and e.get("steps"))


def build_argv(job_id: str, params: dict | None = None) -> list[str]:
    """Build the launch argv for a SINGLE job (not a chain). Raises KeyError if unknown."""
    entry = _BY_ID[job_id]
    params = params or {}

    if is_frozen():
        argv = [sys.executable, "--run-pipeline", job_id]
    elif entry.get("module"):
        argv = [sys.executable, "-m", entry["module"], *entry.get("argv", [])]
    elif entry.get("script"):
        argv = [sys.executable, entry["script"], *entry.get("argv", [])]
    else:
        raise ValueError(f"catalog entry {job_id} has neither module nor script")

    argv += _param_argv(entry, params)
    return argv


def pipeline_argv(job_id: str, params: dict | None = None) -> list[str]:
    """argv for running the pipeline IN-PROCESS (frozen dispatch). No exe prefix."""
    entry = _BY_ID[job_id]
    params = params or {}
    base = list(entry.get("argv", []))
    return base + _param_argv(entry, params)


def _param_argv(entry: dict, params: dict) -> list[str]:
    extra: list[str] = []
    for spec in entry.get("params", []):
        name = spec["name"]
        flag = spec.get("flag")
        if not flag:
            continue
        val = params.get(name, spec.get("default"))
        if spec.get("type") == "bool":
            if val:
                extra.append(flag)
            continue
        if val in (None, ""):
            continue
        extra += [flag, str(val)]
    return extra
