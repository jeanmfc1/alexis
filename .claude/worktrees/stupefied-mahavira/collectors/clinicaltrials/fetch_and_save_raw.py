"""
One-time fetcher — downloads all active studies and saves raw JSON.
Usage:
    python fetch_and_save_raw.py
    python fetch_and_save_raw.py --output my_raw.json
"""

import json
import argparse
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from tqdm import tqdm
import requests

from config.settings import (
    CLINICALTRIALS_API_BASE,
    CLINICALTRIALS_PAGE_SIZE,
)

ACTIVE_STATUSES = [
    "RECRUITING",
    "ACTIVE_NOT_RECRUITING",
    "NOT_YET_RECRUITING",
    "ENROLLING_BY_INVITATION",
]


def fetch_active_studies_raw(
    page_size: int = CLINICALTRIALS_PAGE_SIZE,
    max_studies: Optional[int] = None,
) -> List[Dict[str, Any]]:
    base_params = {
        "filter.overallStatus": "|".join(ACTIVE_STATUSES),
        "pageSize": page_size,
        "countTotal": "true",
        "format": "json",
    }

    studies: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    page_count = 0

    pbar = tqdm(
        total=None,
        desc="Fetching active ClinicalTrials.gov studies",
        unit="study",
        dynamic_ncols=True,
        mininterval=0.2,
    )

    try:
        while True:
            params = dict(base_params)
            if page_token:
                params["pageToken"] = page_token

            r = requests.get(CLINICALTRIALS_API_BASE, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()

            if pbar.total is None:
                total_count = data.get("totalCount")
                if isinstance(total_count, int):
                    pbar.total = total_count

            batch = data.get("studies", []) or []
            studies.extend(batch)

            page_count += 1
            pbar.update(len(batch))
            pbar.set_postfix(pages=page_count, last=len(batch), total=len(studies))

            if max_studies is not None and len(studies) >= max_studies:
                return studies[:max_studies]

            page_token = data.get("nextPageToken")
            if not page_token:
                return studies
    finally:
        pbar.close()


def main():
    parser = argparse.ArgumentParser(description="Fetch and save all active ClinicalTrials.gov studies as raw JSON")
    parser.add_argument(
        "--output",
        default=None,
        help="Output path (default: raw_active_YYYYMMDD.json)"
    )
    args = parser.parse_args()

    output_path = Path(args.output or f"raw_active_{date.today().strftime('%Y%m%d')}.json")

    print(f"Fetching all active studies...")
    raw = fetch_active_studies_raw()

    print(f"Saving {len(raw)} studies to {output_path}...")
    output_path.write_text(json.dumps(raw))
    print(f"✓ Done → {output_path}")


if __name__ == "__main__":
    main()
