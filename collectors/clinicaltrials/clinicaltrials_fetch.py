from tqdm import tqdm

import requests
from datetime import date
from typing import Any, Dict, List, Optional

from tqdm import tqdm

from config.settings import (
    CLINICALTRIALS_API_BASE,
    CLINICALTRIALS_PAGE_SIZE,
)


def fetch_studies_raw(
    updated_from: date,
    updated_to: date,
    condition_query: Optional[str] = None,
    page_size: int = CLINICALTRIALS_PAGE_SIZE,
    max_studies: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Design A fetch: window drives fetch.
    Pulls multiple pages using nextPageToken/pageToken until exhausted
    or until max_studies is reached.
    """

    window_expr = f"AREA[LastUpdatePostDate]RANGE[{updated_from.isoformat()},{updated_to.isoformat()}]"

    base_params = {
        "query.term": window_expr,
        "pageSize": page_size,
        "countTotal": "true",
        "format": "json",
    }

    # Only include condition filter when explicitly provided
    if condition_query:
        base_params["query.cond"] = condition_query

    studies: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    page_count = 0

    # Progress bar: total is max_studies if provided, otherwise unknown (still useful)
    pbar = tqdm(
        total=None,  # will be set after first response using API totalCount
        desc="Fetching ClinicalTrials.gov",
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
