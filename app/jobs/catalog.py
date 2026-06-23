"""Declarative catalog of runnable background jobs.

Each entry describes a pipeline the GUI can launch as a subprocess. The argv
is built lazily (``sys.executable`` resolved at call time) so it is correct
whether launched from a source checkout or, later, a frozen build.

NOTE (frozen builds): in a PyInstaller one-folder exe ``sys.executable`` is
ALEXIS.exe and ``python -m pipelines.x`` will not work. Phase 3 packaging adds
a CLI dispatch (e.g. ``ALEXIS.exe --run-pipeline <id>``); the catalog here is
the single place that mapping needs to change.
"""

from __future__ import annotations

import sys


# Each entry: id, label, description, category, long_running, ready, produces,
# and `args` = the argv tail appended after sys.executable. cwd is app_root()
# (set by the runner), so module/script paths resolve from the repo root.
_CATALOG: list[dict] = [
    {
        "id": "generate_weekly",
        "label": "Generate weekly dashboard",
        "description": "Auto-pick the newest snapshot/changelog/enriched/master-DB "
                       "and rebuild the weekly dashboard HTML.",
        "category": "generate",
        "long_running": True,
        "ready": True,
        "produces": "alexis_weekly_dashboard_live.html",
        "args": ["-m", "pipelines.generate_weekly_viz", "--auto", "--no-open"],
    },
    {
        "id": "self_test",
        "label": "Run portability self-test",
        "description": "Fast check that paths resolve and the rule-based classifier "
                       "works end-to-end on this machine.",
        "category": "diagnostic",
        "long_running": False,
        "ready": True,
        "produces": None,
        "args": ["tools/verify_portability.py"],
    },
    {
        "id": "smoke_classifier",
        "label": "Classifier + model self-test",
        "description": "Full self-test: also loads the MeSH tables and the sklearn "
                       "models to confirm they unpickle.",
        "category": "diagnostic",
        "long_running": True,
        "ready": True,
        "produces": None,
        "args": ["tools/verify_portability.py", "--full"],
    },
    {
        "id": "classify_chictr",
        "label": "Classify ChiCTR -> snapshot",
        "description": "Run the intl drug + TA classifiers over the scraped ChiCTR "
                       "checkpoint and build an ALEXIS snapshot.",
        "category": "classify",
        "long_running": True,
        "ready": True,
        "produces": "ChiCTR snapshot",
        "args": ["-m", "pipelines.classify_chictr_to_snapshot"],
    },
    {
        "id": "classify_anzctr",
        "label": "Classify ANZCTR -> snapshot",
        "description": "Run the intl drug + TA classifiers over the flattened ANZCTR "
                       "data and build an ALEXIS snapshot.",
        "category": "classify",
        "long_running": True,
        "ready": True,
        "produces": "ANZCTR snapshot",
        "args": ["-m", "pipelines.classify_anzctr_to_snapshot"],
    },
]

_BY_ID = {e["id"]: e for e in _CATALOG}

# Public (JSON-ready) keys to expose to the API/UI.
_PUBLIC_KEYS = ("id", "label", "description", "category",
                "long_running", "ready", "produces")


def get_catalog() -> list[dict]:
    """Return the catalog as JSON-ready dicts (no argv internals)."""
    return [{k: e[k] for k in _PUBLIC_KEYS} for e in _CATALOG]


def get_entry(job_id: str) -> dict | None:
    """Return the full catalog entry (including args) or None."""
    return _BY_ID.get(job_id)


def build_argv(job_id: str) -> list[str]:
    """Build the full argv for a job. Raises KeyError if job_id is unknown."""
    entry = _BY_ID[job_id]
    return [sys.executable, *entry["args"]]
