"""
pipelines/generate_chictr_viz.py
────────────────────────────────
Build the ChiCTR portion of the dashboard payload.

Orchestrates the four cw* analytics functions and returns one dict with
keys cw1..cw4 that slot into the main payload.

The diff (update_type on each trial) is read from the latest enriched
file in storage/chictr_changelogs/. If no enriched file exists, all
trials are marked as update_type="existing" -- the weekly widgets will
show empty "new this week" sections.
"""

from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent

CHICTR_SNAP_DIR  = ROOT / "storage" / "snapshots" / "clinical_trials_v2" / "chictr"
CHICTR_ENR_DIR   = ROOT / "storage" / "chictr_changelogs"
CHICTR_CHECKPOINT = ROOT / "storage" / "chictr_details_checkpoint.jsonl"


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
    # Fall back: treat every trial in the current snapshot as "existing"
    # so widgets degrade gracefully rather than crashing.
    return [dict(t, update_type="existing", update_categories=[])
            for t in fallback_trials]


def _load_prior_snapshots(current_path: Path, n: int = 4) -> list[dict]:
    all_files = sorted(
        CHICTR_SNAP_DIR.glob("*_chictr_v1.json"),
        key=lambda p: p.name, reverse=True,
    )
    priors = [f for f in all_files if f != current_path][:n]
    return [_load_snapshot(p) for p in priors]


def build_chictr_payload() -> dict:
    """Entry point — returns dict with keys cw1..cw4 and chictr_metadata."""
    current_path = _newest(CHICTR_SNAP_DIR, "*_chictr_v1.json")

    if current_path is None:
        return {
            "cw1": {"available": False, "reason": "no ChiCTR snapshot found"},
            "cw2": {"available": False, "reason": "no ChiCTR snapshot found"},
            "cw3": {"available": False, "reason": "no ChiCTR snapshot found"},
            "cw4": {"available": False, "reason": "no ChiCTR snapshot found"},
            "chictr_metadata": {"available": False},
        }

    print(f"  ChiCTR snapshot: {current_path.name}")
    current_snap = _load_snapshot(current_path)

    enriched_path = _newest(
        CHICTR_ENR_DIR, f"chictr_enriched_{current_path.stem.split('_chictr_v1')[0]}*.json"
    )
    if enriched_path is None:
        # Try any enriched file that matches current date prefix more loosely
        enriched_path = _newest(CHICTR_ENR_DIR, "chictr_enriched_*.json")
    if enriched_path:
        print(f"  ChiCTR enriched: {enriched_path.name}")
    else:
        print("  ChiCTR enriched: none (new-trial widgets will be empty)")

    enriched_trials = _load_enriched_trials(enriched_path,
                                            current_snap.get("trials", []))

    prior_snaps = _load_prior_snapshots(current_path, n=4)
    print(f"  ChiCTR prior snapshots: {len(prior_snaps)}")

    # -- run the four analytics ------------------------------------------
    from analytics.bd_cw1  import cw1_china_sponsor_action_table
    from analytics.mk_cw1  import cw2_china_ta_momentum
    from analytics.sci_cw1 import cw3_china_ta_modality_matrix
    from analytics.ops_cw1 import cw4_china_pipeline_health

    cw1 = cw1_china_sponsor_action_table(enriched_trials)
    cw2 = cw2_china_ta_momentum(enriched_trials, prior_snaps)
    cw3 = cw3_china_ta_modality_matrix(enriched_trials, prior_snaps)
    cw4 = cw4_china_pipeline_health(current_snap,
                                    checkpoint_path=str(CHICTR_CHECKPOINT))

    print(f"  cw1 sponsors:        {len(cw1):,}")
    print(f"  cw2 TAs:             {len(cw2.get('items', []))}")
    print(f"  cw3 new drug trials: {cw3.get('grand_total', 0):,}")
    print(f"  cw4 corpus total:    {cw4['counts']['current_total']:,}")

    return {
        "cw1": cw1,
        "cw2": cw2,
        "cw3": cw3,
        "cw4": cw4,
        "chictr_metadata": {
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
    payload = build_chictr_payload()
    pprint.pprint(payload["chictr_metadata"])
    print(f"cw1 rows:  {len(payload['cw1']) if isinstance(payload['cw1'], list) else 'n/a'}")
    print(f"cw3 total: {payload['cw3'].get('grand_total', 0)}")
