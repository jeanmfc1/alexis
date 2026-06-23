"""Black-box smoke test for the running ALEXIS MVP server.

Usage:
    python tools/smoke_app.py [--port 18091]

Hits every endpoint, validates response shapes, and exercises the
intentional 400/404/413 paths. Exit 0 on full PASS, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import httpx


PASS, FAIL = "PASS", "FAIL"
_results: list[tuple[str, str, str]] = []


def _record(name: str, ok: bool, detail: str = "") -> None:
    tag = PASS if ok else FAIL
    _results.append((tag, name, detail))
    print(f"  [{tag}] {name}{' - ' + detail if detail else ''}")


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except Exception:
        return None


def run(base: str) -> int:
    print(f"ALEXIS smoke test against {base}")
    print("-" * 70)

    # 1. health
    r = httpx.get(f"{base}/api/health", timeout=10)
    _record("GET /api/health", r.status_code == 200 and _safe_json(r) == {"ok": True, "version": "0.1.0-mvp"},
            f"status={r.status_code} body={r.text[:60]}")

    # 2. settings GET
    r = httpx.get(f"{base}/api/settings", timeout=10)
    body = _safe_json(r) or {}
    keys = {"data_dir", "is_valid", "is_frozen", "app_root", "default_data_dir", "config_path"}
    _record("GET /api/settings shape", r.status_code == 200 and keys.issubset(body),
            f"keys present: {sorted(set(body) & keys)}")

    # 3. info GET
    r = httpx.get(f"{base}/api/info", timeout=10)
    body = _safe_json(r) or {}
    _record("GET /api/info", r.status_code == 200 and "python" in body and "viz_dir" in body,
            f"python={body.get('python')} viz_dir={body.get('viz_dir')}")

    # 4. dashboards GET
    r = httpx.get(f"{base}/api/dashboards", timeout=10)
    body = _safe_json(r) or {}
    avail = body.get("available") or []
    ids = [d.get("id") for d in avail]
    _record("GET /api/dashboards", r.status_code == 200 and len(avail) >= 1,
            f"ids={ids} viz_dir={body.get('viz_dir')}")

    # 5. classify_trial happy path - ADC (Enhertu)
    r = httpx.post(f"{base}/api/classify_trial", timeout=15, json={
        "title": "A Study of Trastuzumab Deruxtecan in HER2-Positive Breast Cancer",
        "brief_summary": "Antibody-drug conjugate trastuzumab deruxtecan.",
        "conditions": ["HER2-positive breast cancer"],
        "interventions": ["Trastuzumab deruxtecan"],
        "intervention_type": "DRUG",
        "phase": "PHASE2",
    })
    body = _safe_json(r) or {}
    _record(
        "POST /api/classify_trial (ADC)",
        r.status_code == 200
        and body.get("is_drug_trial") is True
        and body.get("modality") == "adc"
        and body.get("therapeutic_area") == "Oncology"
        and body.get("modality_color") == "#EC4899",
        f"status={r.status_code} mod={body.get('modality')} ta={body.get('therapeutic_area')} color={body.get('modality_color')}",
    )

    # 6. classify_trial happy path - mAb (Keytruda)
    r = httpx.post(f"{base}/api/classify_trial", timeout=15, json={
        "title": "Pembrolizumab in Advanced NSCLC",
        "interventions": "Pembrolizumab\nKeytruda",
        "conditions": "Non-Small Cell Lung Cancer, NSCLC",
        "intervention_type": "DRUG",
        "phase": "PHASE3",
    })
    body = _safe_json(r) or {}
    _record(
        "POST /api/classify_trial (mAb, string-split inputs)",
        r.status_code == 200
        and body.get("modality") == "monoclonal_antibody"
        and body.get("modality_color") == "#6366F1"
        and body.get("echo", {}).get("n_conditions") == 2
        and body.get("echo", {}).get("n_interventions") == 2,
        f"mod={body.get('modality')} echo={body.get('echo')}",
    )

    # 7. classify_trial 400 - missing title
    r = httpx.post(f"{base}/api/classify_trial", timeout=10, json={"interventions": ["x"]})
    body = _safe_json(r) or {}
    _record("POST /api/classify_trial 400 missing title", r.status_code == 400 and "title" in (body.get("error") or "").lower(),
            f"status={r.status_code} error={body.get('error')}")

    # 8. classify_trial 400 - missing interventions
    r = httpx.post(f"{base}/api/classify_trial", timeout=10, json={"title": "x"})
    body = _safe_json(r) or {}
    _record("POST /api/classify_trial 400 missing interventions", r.status_code == 400,
            f"status={r.status_code} error={body.get('error')}")

    # 9. classify_trial 400 - dict in interventions (must NOT silently iterate)
    r = httpx.post(f"{base}/api/classify_trial", timeout=10, json={
        "title": "x", "interventions": {"a": 1, "b": 2},
    })
    body = _safe_json(r) or {}
    _record(
        "POST /api/classify_trial 400 rejects dict for interventions",
        r.status_code == 400 and "interventions" in (body.get("error") or ""),
        f"status={r.status_code} error={body.get('error')}",
    )

    # 10. settings 400 - relative path
    r = httpx.post(f"{base}/api/settings", timeout=10, json={"data_dir": "relative/path"})
    body = _safe_json(r) or {}
    _record(
        "POST /api/settings 400 rejects relative path",
        r.status_code == 400 and "absolute" in (body.get("error") or "").lower(),
        f"status={r.status_code} error={body.get('error')}",
    )

    # 11. settings 400 - non-existent dir
    nonexistent = "C:" + chr(92) + "NoSuchDir12345_" + chr(92) + "alexis"
    r = httpx.post(f"{base}/api/settings", timeout=10, json={"data_dir": nonexistent})
    body = _safe_json(r) or {}
    _record(
        "POST /api/settings 400 rejects non-existent dir",
        r.status_code == 400 and "exist" in (body.get("error") or "").lower(),
        f"status={r.status_code} error={(body.get('error') or '')[:80]}",
    )

    # 12. root /
    r = httpx.get(f"{base}/", timeout=10)
    is_html = r.status_code == 200 and "<!DOCTYPE HTML" in r.text[:120].upper()
    _record("GET / (index.html)", is_html, f"status={r.status_code} bytes={len(r.text)}")

    # 13. /dashboards static mount - existing file
    r = httpx.get(f"{base}/dashboards/alexis_weekly_dashboard.html", timeout=10)
    _record("GET /dashboards/<existing>", r.status_code == 200 and len(r.text) > 1000,
            f"status={r.status_code} bytes={len(r.text)}")

    # 14. /dashboards traversal must NOT escape mount (Starlette resolves this to 404)
    r = httpx.get(f"{base}/dashboards/../core/paths.py", timeout=10, follow_redirects=False)
    _record("GET /dashboards traversal rejected",
            r.status_code in (400, 404),
            f"status={r.status_code}")

    # 15. payload-size guard (>1 MiB)
    big = "x" * (1024 * 1024 + 1024)
    r = httpx.post(f"{base}/api/classify_trial", timeout=10,
                   content=json.dumps({"title": "x", "interventions": [big]}),
                   headers={"content-type": "application/json"})
    _record("POST oversize body 413",
            r.status_code == 413,
            f"status={r.status_code}")

    print("-" * 70)
    failed = [r for r in _results if r[0] == FAIL]
    print(f"{len(_results) - len(failed)}/{len(_results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18091)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    raise SystemExit(run(f"http://{args.host}:{args.port}"))
