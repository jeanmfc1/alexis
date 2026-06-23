"""Declarative catalog of runnable background jobs.

Each entry names either a ``module`` (run like ``python -m <module>``) or a
``script`` (a path under the app root), plus the ``argv`` tail. The runner
turns this into a real command:

* Source checkout -> [sys.executable, "-m", module, *argv]
                  or [sys.executable, script, *argv]
* Frozen exe      -> [sys.executable, "--run-pipeline", job_id]
  (``sys.executable`` is ALEXIS.exe; ``-m`` does not work in a one-file/one-dir
  freeze, so the exe re-launches itself and app.__main__ dispatches via runpy.)
"""

from __future__ import annotations

import sys

from core.paths import is_frozen


# module XOR script. argv = the tail appended after the module/script.
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
        "module": "pipelines.generate_weekly_viz",
        "script": None,
        "argv": ["--auto", "--no-open"],
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
        "module": None,
        "script": "tools/verify_portability.py",
        "argv": [],
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
        "module": None,
        "script": "tools/verify_portability.py",
        "argv": ["--full"],
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
        "module": "pipelines.classify_chictr_to_snapshot",
        "script": None,
        "argv": [],
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
        "module": "pipelines.classify_anzctr_to_snapshot",
        "script": None,
        "argv": [],
    },
]

_BY_ID = {e["id"]: e for e in _CATALOG}

_PUBLIC_KEYS = ("id", "label", "description", "category",
                "long_running", "ready", "produces")


def get_catalog() -> list[dict]:
    """Return the catalog as JSON-ready dicts (no run internals)."""
    return [{k: e[k] for k in _PUBLIC_KEYS} for e in _CATALOG]


def get_entry(job_id: str) -> dict | None:
    return _BY_ID.get(job_id)


def build_argv(job_id: str) -> list[str]:
    """Build the launch argv for a job. Raises KeyError if job_id is unknown.

    In a frozen build, re-launch the exe with ``--run-pipeline <id>`` so
    app.__main__ can dispatch it via runpy (``-m`` is unavailable when frozen).
    """
    entry = _BY_ID[job_id]
    if is_frozen():
        return [sys.executable, "--run-pipeline", job_id]
    if entry.get("module"):
        return [sys.executable, "-m", entry["module"], *entry.get("argv", [])]
    if entry.get("script"):
        return [sys.executable, entry["script"], *entry.get("argv", [])]
    raise ValueError(f"catalog entry {job_id} has neither module nor script")
