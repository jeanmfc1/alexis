"""
pipelines/generate_anzctr_viz.py
──────────────────────────────────
Build the ANZCTR portion of the dashboard payload.

Orchestrates the four aw* analytics functions and returns one dict with
keys aw1..aw4 that slot into the main payload.

The diff (update_type on each trial) is read from the latest enriched
file in storage/anzctr_changelogs/. If no enriched file exists, all
trials are marked as update_type="existing" -- the monthly widgets will
show empty "new this period" sections.
"""

from __future__ import annotations
import json
from pathlib import Path

# ROOT only puts the repo on sys.path so core.*/analytics.* imports resolve when
# this file is run directly. Data dirs come from core.paths so they honour the
# user's data folder (data_root) and work in a frozen build -- deriving them from
# __file__ would point inside the read-only bundle when packaged. Mirrors the
# pattern in generate_weekly_viz.py.
import sys
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import snapshots_dir, storage_dir

ANZCTR_SNAP_DIR = snapshots_dir() / "anzctr"
ANZCTR_ENR_DIR  = storage_dir() / "anzctr_changelogs"
ANZCTR_XLSX     = storage_dir() / "TrialDetails ANZCTR" / "TrialDetails65.xlsx"


def _newest(dir_path: Path, pattern: str) -> Path | None:
    if not dir_path.exists():
        return None
    files = list(dir_path.glob(pattern))
    if not files:
        return None
    files.sort(key=lambda p: p.name, reverse=True)
    return files[0]


def _load_snapshot(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_enriched_trials(enriched_path: Path | None,
                          fallback_trials: list) -> list:
    if enriched_path and enriched_path.exists():
        snap = _load_snapshot(enriched_path)
        return snap.get("trials", [])
    return [dict(t, update_type="existing", update_categories=[])
            for t in fallback_trials]


def _load_prior_snapshots(current_path: Path, n: int = 8) -> list[dict]:
    """
    Load up to n prior ANZCTR snapshots for baseline computation.

    Prefers synthetic snapshots over real ones on the same date
    (synthetic use consistent corpus completeness + classifier version
    across the timeline, backfilled via backfill_anzctr_snapshots.py).
    """
    if not ANZCTR_SNAP_DIR.exists():
        return []
    candidates = [
        f for f in ANZCTR_SNAP_DIR.glob("*_anzctr_v1*.json")
        if f != current_path
    ]

    import re
    by_date: dict[str, list[Path]] = {}
    for f in candidates:
        m = re.match(r"(\d{4}-\d{2}-\d{2})_anzctr_v1", f.name)
        if not m:
            continue
        by_date.setdefault(m.group(1), []).append(f)

    picked: list[Path] = []
    for d, files in by_date.items():
        synth = [f for f in files if "_synth" in f.name]
        picked.append(synth[0] if synth else files[0])

    picked.sort(key=lambda p: p.name, reverse=True)
    picked = picked[:n]

    loaded = [_load_snapshot(p) for p in picked]
    synth_n = sum(1 for p in picked if "_synth" in p.name)
    real_n  = len(picked) - synth_n
    print(f"    (using {synth_n} synthetic + {real_n} real prior snapshot(s))")
    return loaded


def build_anzctr_payload() -> dict:
    """Entry point -- returns dict with keys aw1..aw4 and anzctr_metadata."""
    current_path = _newest(ANZCTR_SNAP_DIR, "*_anzctr_v1.json")

    if current_path is None:
        return {
            "aw1": {"available": False, "reason": "no ANZCTR snapshot found"},
            "aw2": {"available": False, "reason": "no ANZCTR snapshot found"},
            "aw3": {"available": False, "reason": "no ANZCTR snapshot found"},
            "aw4": {"available": False, "reason": "no ANZCTR snapshot found"},
            "anzctr_metadata": {"available": False},
        }

    print(f"  ANZCTR snapshot: {current_path.name}")
    current_snap = _load_snapshot(current_path)

    date_prefix = current_path.stem.split("_anzctr_v1")[0]
    enriched_path = _newest(
        ANZCTR_ENR_DIR, f"anzctr_enriched_{date_prefix}*.json"
    )
    if enriched_path is None:
        enriched_path = _newest(ANZCTR_ENR_DIR, "anzctr_enriched_*.json")
    if enriched_path:
        print(f"  ANZCTR enriched: {enriched_path.name}")
    else:
        print("  ANZCTR enriched: none (new-trial widgets will be empty)")

    enriched_trials = _load_enriched_trials(enriched_path,
                                            current_snap.get("trials", []))

    prior_snaps = _load_prior_snapshots(current_path, n=8)
    print(f"  ANZCTR prior snapshots: {len(prior_snaps)}")

    # -- run the four analytics ------------------------------------------
    from analytics.bd_aw1  import aw1_foreign_sponsor_fih_table
    from analytics.mk_aw1  import aw2_anzctr_ta_momentum
    from analytics.sci_aw1 import aw3_anzctr_ta_modality_matrix
    from analytics.ops_aw1 import aw4_anzctr_pipeline_health

    all_trials = current_snap.get("trials", [])
    aw1 = aw1_foreign_sponsor_fih_table(enriched_trials, all_trials=all_trials)
    aw2 = aw2_anzctr_ta_momentum(enriched_trials, prior_snaps)
    aw3 = aw3_anzctr_ta_modality_matrix(enriched_trials, prior_snaps)
    aw4 = aw4_anzctr_pipeline_health(current_snap,
                                     xlsx_path=str(ANZCTR_XLSX))

    print(f"  aw1 FIH rows:        {len(aw1.get('rows', []) if aw1.get('available') else []):,}")
    print(f"  aw2 TAs:             {len(aw2.get('items', []))}")
    print(f"  aw3 new drug trials: {aw3.get('grand_total', 0):,}")
    print(f"  aw4 corpus total:    {aw4['counts']['current_total']:,}")

    return {
        "aw1": aw1,
        "aw2": aw2,
        "aw3": aw3,
        "aw4": aw4,
        "anzctr_metadata": {
            "available":     True,
            "snapshot_file": current_path.name,
            "enriched_file": enriched_path.name if enriched_path else None,
            "as_of":         current_snap.get("metadata", {}).get("as_of"),
            "classifier":    current_snap.get("metadata", {}).get("classifier"),
            "prior_used":    len(prior_snaps),
        },
    }


if __name__ == "__main__":
    import pprint
    payload = build_anzctr_payload()
    pprint.pprint(payload["anzctr_metadata"])
    aw1 = payload["aw1"]
    print(f"aw1 rows:  {len(aw1.get('rows', [])) if aw1.get('available') else 'unavailable'}")
    print(f"aw3 total: {payload['aw3'].get('grand_total', 0)}")
