# analytics/modality_audit_writer.py

import json
import os
from pathlib import Path
from datetime import datetime
from collections import Counter
from typing import Iterable, Dict, Any


def write_modality_info_artifact(
    infos: Iterable[Dict[str, Any]],
    *,
    context: Dict[str, Any] | None = None,
    out_dir: str | None = None,
) -> str | None:
    """
    Persist all INFO entries from modality audit to disk.

    Parameters
    ----------
    infos
        Iterable of INFO dicts produced by modality_audit.
        Expected keys: nct_id, type, message.
    context
        Optional metadata (snapshot path, n_trials, etc.).
    out_dir
        Optional override for output directory.

    Returns
    -------
    str | None
        Path to written file, or None if nothing was written.
    """
    infos = list(infos)
    if not infos:
        return None

    # Allow environment override (CI / tests)
    out_dir = (
        out_dir
        or os.environ.get("ALEXIS_AUDIT_OUT_DIR")
        or "storage/audits/modality"
    )

    Path(out_dir).mkdir(parents=True, exist_ok=True)

    ts = datetime.now().isoformat(timespec="seconds").replace(":", "-")

    counts = Counter(i.get("type", "MISSING_TYPE") for i in infos)

    payload = {
        "created_at": ts,
        "context": context or {},
        "summary": {
            "infos_total": len(infos),
            "info_counts": dict(counts),
        },
        "infos": infos,
    }

    out_path = Path(out_dir) / f"modality_audit_infos_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return str(out_path)
