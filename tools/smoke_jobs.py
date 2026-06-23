"""Black-box smoke test for the ALEXIS Phase 2 job subsystem.

Usage:  python tools/smoke_jobs.py [--port 18093]

Exercises: catalog, start, SSE log streaming to completion, run listing, and
cancel. Exit 0 on full PASS, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import time

import httpx


PASS, FAIL = "PASS", "FAIL"
_results: list[tuple[str, str, str]] = []


def rec(name: str, ok: bool, detail: str = "") -> None:
    tag = PASS if ok else FAIL
    _results.append((tag, name, detail))
    print(f"  [{tag}] {name}{' - ' + detail if detail else ''}")


def consume_sse(base: str, run_id: str, timeout_s: float = 120.0):
    """Read the SSE log stream until the 'end' event. Returns (log_text, end_info)."""
    url = f"{base}/api/jobs/{run_id}/logs"
    log_chunks: list[str] = []
    end_info = None
    deadline = time.monotonic() + timeout_s
    with httpx.stream("GET", url, timeout=timeout_s) as r:
        event = None
        data_lines: list[str] = []
        for line in r.iter_lines():
            if time.monotonic() > deadline:
                break
            if line == "":  # dispatch on blank line
                if event == "log":
                    log_chunks.append("\n".join(data_lines))
                elif event == "end":
                    try:
                        end_info = json.loads("\n".join(data_lines))
                    except Exception:
                        end_info = {"status": "unknown"}
                    break
                event, data_lines = None, []
                continue
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].lstrip())
    return "\n".join(log_chunks), end_info


def poll_until_terminal(base: str, run_id: str, timeout_s: float = 120.0) -> dict:
    deadline = time.monotonic() + timeout_s
    last = {}
    while time.monotonic() < deadline:
        r = httpx.get(f"{base}/api/jobs/{run_id}", timeout=10)
        last = r.json()
        if last.get("status") in ("succeeded", "failed", "cancelled"):
            return last
        time.sleep(0.5)
    return last


def run(base: str) -> int:
    print(f"ALEXIS jobs smoke test against {base}")
    print("-" * 70)

    # 1. catalog
    r = httpx.get(f"{base}/api/jobs/catalog", timeout=10)
    jobs = (r.json() or {}).get("jobs", [])
    ids = [j["id"] for j in jobs]
    rec("GET /api/jobs/catalog", r.status_code == 200 and "self_test" in ids,
        f"ids={ids}")

    # 2. start self_test
    r = httpx.post(f"{base}/api/jobs", timeout=10, json={"job_id": "self_test"})
    run1 = r.json()
    rec("POST /api/jobs (self_test)",
        r.status_code == 200 and run1.get("status") in ("pending", "running")
        and run1.get("run_id"),
        f"status={r.status_code} run_status={run1.get('status')}")
    run_id = run1.get("run_id")

    # 3. stream logs to completion
    if run_id:
        log_text, end = consume_sse(base, run_id, timeout_s=90)
        rec("SSE stream reaches 'end'", bool(end), f"end={end}")
        rec("SSE captured log output", "[runner]" in log_text and len(log_text) > 50,
            f"log_bytes={len(log_text)}")
        rec("self_test succeeded", bool(end) and end.get("status") == "succeeded",
            f"end_status={(end or {}).get('status')} rc={(end or {}).get('returncode')}")
        rec("log shows portability PASS", "PASS" in log_text or "checks passed" in log_text,
            f"has_PASS={'PASS' in log_text}")

    # 4. run shows up in the list as succeeded
    r = httpx.get(f"{base}/api/jobs", timeout=10)
    runs = (r.json() or {}).get("runs", [])
    match = next((x for x in runs if x.get("run_id") == run_id), None)
    rec("GET /api/jobs lists the run", match is not None and match.get("status") == "succeeded",
        f"found={match is not None} status={(match or {}).get('status')}")

    # 5. cancel: start a long job and cancel it mid-run
    r = httpx.post(f"{base}/api/jobs", timeout=10, json={"job_id": "smoke_classifier"})
    run2 = r.json()
    rid2 = run2.get("run_id")
    rec("POST /api/jobs (smoke_classifier)", r.status_code == 200 and rid2 is not None,
        f"status={r.status_code}")
    if rid2:
        time.sleep(1.5)  # let it get going
        rc = httpx.post(f"{base}/api/jobs/{rid2}/cancel", timeout=15)
        rec("POST cancel returns cancelled", rc.status_code == 200
            and rc.json().get("status") == "cancelled",
            f"status={rc.status_code} run_status={rc.json().get('status')}")
        final = poll_until_terminal(base, rid2, timeout_s=30)
        rec("cancelled job is terminal", final.get("status") == "cancelled",
            f"final={final.get('status')} rc={final.get('returncode')}")

    # 6. error paths
    r = httpx.post(f"{base}/api/jobs", timeout=10, json={"job_id": "does_not_exist"})
    rec("POST unknown job_id -> 400", r.status_code == 400, f"status={r.status_code}")
    r = httpx.get(f"{base}/api/jobs/deadbeef", timeout=10)
    rec("GET unknown run -> 404", r.status_code == 404, f"status={r.status_code}")

    print("-" * 70)
    failed = [x for x in _results if x[0] == FAIL]
    print(f"{len(_results) - len(failed)}/{len(_results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18093)
    args = ap.parse_args()
    raise SystemExit(run(f"http://127.0.0.1:{args.port}"))
