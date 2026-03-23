"""
Backfill modality_source and therapeutic_area_source into an existing
master DB JSON.

modality_source:  Re-runs text_modality_from_text() for trials where MeSH
                  failed or was absent, matching the classifier's real logic.
therapeutic_area_source:  100 % derivable from existing serialized fields.

Memory: ~400 MB (JSON dict only, no trial reconstruction).

Usage:
    python pipelines/backfill_source_fields.py [path/to/master.json]
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from policy.text_modality_policy_v2 import text_modality_from_text

# Literal values from policy/ta_policy.py — avoid heavy import chain
_TA_NON_DISEASE = "Non-disease drug study"
_TA_UNASSIGNED  = "Unassigned drug study"


# ── Derivation helpers ──────────────────────────────────────────────

def _backfill_modality_source(t: dict) -> str | None:
    """Derive modality_source for a serialized trial dict."""
    if not t.get("is_drug_trial"):
        return None

    mesh_available = bool(t.get("intervention_meshes"))
    mesh_failed    = "mesh_available_but_not_used" in (t.get("info_flags") or [])

    # Path 1: MeSH resolved cleanly
    if mesh_available and not mesh_failed:
        return "mesh_tree"

    # Path 2 vs 3: re-run text matcher to distinguish text / intervention_type
    text_blob = " ".join((t.get("interventions_text") or []) + [t.get("title") or ""])
    text_hit  = text_modality_from_text(text_blob, t.get("modality"))

    return "text" if text_hit else "intervention_type"


def _backfill_ta_source(t: dict) -> str | None:
    """Derive therapeutic_area_source from existing serialized fields."""
    if not t.get("is_drug_trial"):
        return None

    ta         = t.get("therapeutic_area")
    ta_detected = t.get("therapeutic_areas_detected") or []

    if ta_detected:
        return "mesh_evidence"
    if ta == _TA_NON_DISEASE:
        return "enabling_signal"
    if ta == _TA_UNASSIGNED:
        return "unassigned_fallback"
    if ta:
        return "text_matching"
    return None


# ── Main ────────────────────────────────────────────────────────────

def main():
    snapshot_path = Path(
        sys.argv[1] if len(sys.argv) > 1
        else "storage/snapshots/clinical_trials_v2/active_universe/master_DB_2025_Q4.json"
    )
    output_path = snapshot_path.with_name(
        snapshot_path.stem + "_with_sources.json"
    )

    print(f"Loading {snapshot_path} ...")
    t0 = time.time()
    with open(snapshot_path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    trials = data["trials"]
    print(f"  Loaded {len(trials):,} trials in {time.time() - t0:.1f}s")

    # ── Backfill ────────────────────────────────────────────────────
    mod_counts = {"mesh_tree": 0, "text": 0, "intervention_type": 0, "skipped": 0}
    ta_counts  = {
        "mesh_evidence": 0, "text_matching": 0,
        "enabling_signal": 0, "unassigned_fallback": 0, "skipped": 0,
    }

    t0 = time.time()
    for t in trials:
        ms = _backfill_modality_source(t)
        ts = _backfill_ta_source(t)
        t["modality_source"]          = ms
        t["therapeutic_area_source"]  = ts

        mod_counts[ms or "skipped"] += 1
        ta_counts[ts or "skipped"]  += 1

    elapsed = time.time() - t0
    print(f"  Backfilled in {elapsed:.1f}s")

    print(f"\n=== Modality Source ===")
    for k, v in mod_counts.items():
        print(f"  {k:25} | {v:>7,}")

    print(f"\n=== TA Source ===")
    for k, v in ta_counts.items():
        print(f"  {k:25} | {v:>7,}")

    # ── Save ────────────────────────────────────────────────────────
    print(f"\nSaving to {output_path} ...")
    t0 = time.time()
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"  Saved in {time.time() - t0:.1f}s")
    print(f"  File size: {output_path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
