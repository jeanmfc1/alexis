"""Coverage sweep: run EVERY catalog pipeline against a running ALEXIS server.

For each job: start it, then either let it complete or (for heavy jobs) confirm
it gets past startup into real work without a crash, then cancel. Classifies:

  PASS    - completed rc 0, or ran cleanly then was cancelled (heavy jobs)
  FAIL    - crash marker in log (traceback / charmap / extract / import / perm)
            or terminal rc != 0 for a job expected to complete
  PREREQ  - failed only due to a missing prerequisite (e.g. Playwright), cleanly

Usage:  python tools/smoke_all_jobs.py --port 18160
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import httpx

CRASH_MARKERS = ["Traceback", "UnicodeEncodeError", "charmap",
                 "failed to extract", "failed to open archive",
                 "ModuleNotFoundError", "ImportError",
                 "Permission denied", "[err] pipeline"]
PREREQ_MARKERS = ["playwright", "Playwright", "No module named 'playwright'",
                  "Executable doesn't exist", "BrowserType.launch"]
# Lines that prove the pipeline reached real work (not just startup).
PROGRESS_MARKERS = ["Window:", "Raw studies", "Processing", "Classifying",
                    "Building", "Reading", "STEP", "snapshot", "wrote",
                    "MeSH cache", "trials", "Saved", "[ok]", "rows", "Loaded",
                    "Backfill", "Diff", "chain", "patch", "PASS"]


def _read_log(path: str | None) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _has(markers, text) -> str | None:
    for m in markers:
        if m in text:
            return m
    return None


def run(base: str) -> int:
    httpx_to = 20.0
    cat = {e["id"]: e for e in httpx.get(f"{base}/api/jobs/catalog", timeout=httpx_to).json()["jobs"]}

    # Resolve newest two snapshots for the diff jobs.
    def opts(provider):
        try:
            return httpx.get(f"{base}/api/jobs/options/{provider}", timeout=httpx_to).json()["options"]
        except Exception:
            return []
    chictr = [o["value"] for o in opts("snap:chictr")]
    anzctr = [o["value"] for o in opts("snap:anzctr")]
    au = [o["value"] for o in opts("snap:active_universe")]

    # (job_id, params, mode, timeout_s)
    #   mode "complete": must reach rc 0 within timeout
    #   mode "runs":     ok if it completes rc0 OR runs cleanly then we cancel
    #   mode "prereq":   a clean missing-dependency failure is acceptable
    plan = [
        ("self_test",              {}, "complete", 120),
        ("pull_window",            {"days": 1}, "complete", 240),
        ("pull_weekly",            {}, "runs", 60),
        ("enrich_weekly",          {}, "runs", 90),
        ("build_master",           {"aact_dir": (opts("aact_folders")[0]["value"] if opts("aact_folders") else "")}, "runs", 75),
        ("scrape_chictr",          {"limit": 3}, "prereq", 60),
        ("scrape_chictr_details",  {}, "prereq", 45),
        ("classify_chictr",        {}, "runs", 75),
        ("backfill_chictr",        {}, "runs", 90),
        ("diff_chictr",            {"prior": chictr[1] if len(chictr) > 1 else "", "current": chictr[0] if chictr else ""}, "runs", 90),
        ("ingest_anzctr",          {}, "runs", 90),
        ("classify_anzctr",        {}, "runs", 75),
        ("backfill_anzctr",        {}, "runs", 90),
        ("diff_anzctr",            {"prior": anzctr[1] if len(anzctr) > 1 else "", "current": anzctr[0] if anzctr else ""}, "runs", 90),
        ("generate_weekly",        {}, "complete", 180),
        ("generate_full",          {}, "runs", 150),
        ("reclassify_snapshot",    {"snapshot": au[0] if au else ""}, "runs", 60),
        ("patch_adc",              {}, "runs", 120),
        ("backfill_source_fields", {}, "runs", 90),
        ("refresh_weekly",         {}, "runs", 40),   # chain
        ("refresh_chictr",         {}, "runs", 40),   # chain
        ("refresh_anzctr",         {}, "runs", 40),   # chain
    ]

    results = []
    print(f"ALEXIS full job sweep ({len(plan)} jobs) against {base}")
    print("=" * 78)
    for job_id, params, mode, timeout_s in plan:
        if job_id not in cat:
            results.append((job_id, "MISSING", "not in catalog"))
            print(f"  [MISSING] {job_id}")
            continue
        try:
            run_rec = httpx.post(f"{base}/api/jobs", timeout=httpx_to,
                                 json={"job_id": job_id, "params": params}).json()
        except Exception as e:
            results.append((job_id, "FAIL", f"start error: {e}"))
            print(f"  [FAIL] {job_id}: could not start ({e})")
            continue
        rid = run_rec.get("run_id")
        if not rid:
            results.append((job_id, "FAIL", f"no run_id: {run_rec}"))
            print(f"  [FAIL] {job_id}: {run_rec}")
            continue

        deadline = time.monotonic() + timeout_s
        status, rc, logf = "running", None, None
        while time.monotonic() < deadline:
            time.sleep(2)
            s = httpx.get(f"{base}/api/jobs/{rid}", timeout=httpx_to).json()
            status, rc, logf = s.get("status"), s.get("returncode"), s.get("log_file")
            if status in ("succeeded", "failed", "cancelled"):
                break

        log = _read_log(logf)
        crash = _has(CRASH_MARKERS, log)
        prereq = _has(PREREQ_MARKERS, log)
        progressed = _has(PROGRESS_MARKERS, log) is not None

        # cancel if still running
        if status == "running":
            try:
                httpx.post(f"{base}/api/jobs/{rid}/cancel", timeout=httpx_to)
            except Exception:
                pass

        # classify outcome
        if crash and not (prereq and mode == "prereq"):
            verdict, note = "FAIL", f"crash: {crash}"
        elif status == "succeeded":
            verdict, note = "PASS", "completed rc0"
        elif status == "failed":
            if mode == "prereq" and prereq:
                verdict, note = "PREREQ", f"needs: {prereq}"
            else:
                verdict, note = "FAIL", f"rc={rc}; tail={log.strip().splitlines()[-1][:80] if log.strip() else 'no log'}"
        elif status in ("running", "cancelled"):
            if mode == "complete":
                verdict, note = "FAIL", "did not complete in time"
            elif progressed:
                verdict, note = "PASS", "ran cleanly (cancelled heavy job)"
            else:
                verdict, note = "WARN", "no crash but no clear progress"
        else:
            verdict, note = "WARN", f"status={status}"

        results.append((job_id, verdict, note))
        print(f"  [{verdict}] {job_id}: {note}")

    print("=" * 78)
    tally = {}
    for _, v, _n in results:
        tally[v] = tally.get(v, 0) + 1
    print("SUMMARY:", ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    fails = [r for r in results if r[1] in ("FAIL", "MISSING")]
    return 1 if fails else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18160)
    args = ap.parse_args()
    raise SystemExit(run(f"http://127.0.0.1:{args.port}"))
