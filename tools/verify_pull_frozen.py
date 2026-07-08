"""Verify a real pull completes (with multiprocessing) against a running server.

Runs pull_window days=1 to COMPLETION (no cancel), then inspects the job log for
the parallel-worker line, completion, save, and any crash markers. ASCII-only
output so it never trips a cp1252 console. Exit 0 only on a clean success.

Usage:  python tools/verify_pull_frozen.py --port 18170
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import httpx

CRASH = ["Traceback", "UnicodeEncodeError", "charmap", "failed to extract",
         "failed to open archive", "NoneType", "BrokenPipe",
         "ModuleNotFoundError", "[err] pipeline"]

# Markers that utils/parallel_processor.py prints when it abandons the Pool and
# runs single-process. Their presence means a silent single-core regression.
SINGLE_PROC = ["falling back to single process", "parallel processing unavailable"]


def run(base: str) -> int:
    info = httpx.get(f"{base}/api/info", timeout=15).json()
    print(f"frozen={info.get('is_frozen')} python={info.get('python')}")

    started = httpx.post(f"{base}/api/jobs", timeout=15,
                         json={"job_id": "pull_window", "params": {"days": 1}}).json()
    rid = started["run_id"]
    print(f"started pull_window days=1 run_id={rid}")

    s = {}
    t0 = time.monotonic()
    for _ in range(150):  # bounded: 150 * 3s = 7.5 min max
        time.sleep(3)
        s = httpx.get(f"{base}/api/jobs/{rid}", timeout=15).json()
        if s.get("status") in ("succeeded", "failed", "cancelled"):
            break
    elapsed = time.monotonic() - t0
    status = s.get("status")
    log = ""
    if s.get("log_file"):
        try:
            log = Path(s["log_file"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass

    workers = None
    m = re.search(r"with (\d+) parallel workers", log)
    if m:
        workers = int(m.group(1))
    completed = "Classification completed" in log
    saved = "Saved snapshot" in log
    crash = next((c for c in CRASH if c in log), None)
    # Catch a SILENT single-core fallback: utils/parallel_processor drops to
    # _sequential() (printing one of these) when num_workers<=1 or the Pool
    # raises. A frozen build MUST stay multi-core, so the fallback is a failure.
    single_core = next((p for p in SINGLE_PROC if p in log), None)

    print(f"status={status} rc={s.get('returncode')} elapsed={elapsed:.0f}s")
    print(f"parallel_workers={workers}")
    print(f"classification_completed={completed}")
    print(f"snapshot_saved={saved}")
    print(f"crash_marker={crash}")
    print(f"single_core_fallback={single_core}")

    # Require genuine multiprocessing: the worker line must be present with K>1
    # AND no single-process fallback marker. (Process-count 2->K+2 is the gold
    # standard; these log assertions are the cheap automated equivalent.)
    ok = (status == "succeeded" and completed and saved and crash is None
          and single_core is None
          and workers is not None and workers > 1)
    print("VERDICT=" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18170)
    args = ap.parse_args()
    raise SystemExit(run(f"http://127.0.0.1:{args.port}"))
