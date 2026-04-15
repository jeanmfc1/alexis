# pipelines/scrape_chictr.py
"""
ChiCTR scraper — server-side rendered HTML, no Selenium needed.
Paginates through search results, then fetches individual trial detail pages.

Usage:
    python pipelines/scrape_chictr.py                  # Phase I interventional, all statuses
    python pipelines/scrape_chictr.py --phase 9 13     # Phase I and Phase I+II only
    python pipelines/scrape_chictr.py --limit 100      # Cap at 100 trials (for testing)
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import argparse
import json
from pathlib import Path
from datetime import datetime


# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
BASE_URL = "https://www.chictr.org.cn/searchprojEN.html"
DETAIL_URL = "https://www.chictr.org.cn/showprojEN.html"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; research bot; contact: your@email.com)",
    "Accept-Language": "en-US,en;q=0.9",
}

# Phase values from the dropdown
PHASE_MAP = {
    "9":  "Phase I",
    "10": "Phase II",
    "11": "Phase III",
    "12": "Post-marketing",
    "13": "Phase I+II",
    "14": "Exploratory/Phase 0",
    "15": "Phase IV",
    "16": "Other/N/A",
    "70": "Phase II+III",
}

DELAY = 1.0  # seconds between requests — be polite


# ------------------------------------------------------------------
# Step 1: Paginate through the search results list
# ------------------------------------------------------------------
def build_search_url(page: int, phase: str = "", studytype: str = "1") -> str:
    """
    Build a search URL for a given page.
    studytype=1 = Interventional study (default)
    phase = studystage value, e.g. "9" for Phase I (empty = all phases)
    """
    params = {
        "page": page,
        "title": "",
        "officialname": "",
        "subjectid": "",
        "regstatus": "",
        "regno": "",
        "secondaryid": "",
        "applier": "",
        "studyleader": "",
        "createyear": "",
        "sponsor": "",
        "secsponsor": "",
        "sourceofspends": "",
        "studyailment": "",
        "studyailmentcode": "",
        "studytype": studytype,
        "studystage": phase,
        "studydesign": "",
        "recruitmentstatus": "",
        "gender": "",
        "agreetosign": "",
        "measure": "",
        "country": "",
        "province": "",
        "city": "",
        "institution": "",
        "institutionlevel": "",
        "intercode": "",
        "ethicalcommitteesanction": "",
        "whetherpublic": "",
        "minstudyexecutetime": "",
        "maxstudyexecutetime": "",
        "btngo": "btn",
    }
    param_str = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{BASE_URL}?{param_str}"


def get_total_count(soup: BeautifulSoup) -> int:
    """Extract total trial count from the results page."""
    el = soup.find("span", id="data-totalEN")
    if el:
        try:
            return int(el.text.strip().replace(",", ""))
        except ValueError:
            pass
    return 0


def parse_list_page(soup: BeautifulSoup) -> list[dict]:
    """Extract trial stubs from a search results page."""
    trials = []
    table = soup.find("table", class_="table1")
    if not table:
        return trials

    rows = table.find_all("tr")[1:]  # skip header row
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 5:
            continue

        # Registration number
        regno = cols[1].get_text(strip=True)

        # Title + sponsor
        title_cell = cols[2]
        title_link = title_cell.find("a")
        title = title_link.get_text(strip=True) if title_link else ""
        proj_id = ""
        if title_link and title_link.get("href"):
            href = title_link["href"]
            if "proj=" in href:
                proj_id = href.split("proj=")[-1].strip()

        sponsor_p = title_cell.find("p")
        sponsor = sponsor_p.get_text(strip=True) if sponsor_p else ""

        study_type = cols[3].get_text(strip=True)
        reg_date = cols[4].get_text(strip=True)

        trials.append({
            "regno": regno,
            "proj_id": proj_id,
            "title": title,
            "sponsor": sponsor,
            "study_type": study_type,
            "reg_date": reg_date,
        })

    return trials


def scrape_list(phase: str = "", studytype: str = "1", limit: int = None,
                delay: float = DELAY) -> list[dict]:
    """
    Paginate through all search results and return a list of trial stubs.
    """
    print(f"Starting list scrape — studytype={studytype}, phase='{phase}'")

    # Fetch page 1 to get total count
    url = build_search_url(page=1, phase=phase, studytype=studytype)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")

    total = get_total_count(soup)
    total_pages = (total + 9) // 10  # 10 per page, ceiling division
    print(f"Total trials: {total:,} across {total_pages:,} pages")

    if limit:
        max_pages = min(total_pages, (limit + 9) // 10)
        print(f"Limiting to {limit} trials ({max_pages} pages)")
    else:
        max_pages = total_pages

    all_trials = parse_list_page(soup)

    for page in range(2, max_pages + 1):
        if limit and len(all_trials) >= limit:
            break

        time.sleep(delay)
        url = build_search_url(page=page, phase=phase, studytype=studytype)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            trials = parse_list_page(soup)
            if not trials:
                print(f"  Page {page}: empty — stopping")
                break
            all_trials.extend(trials)
            if page % 50 == 0:
                print(f"  Page {page}/{max_pages} — {len(all_trials):,} trials so far")
        except Exception as e:
            print(f"  Page {page}: ERROR — {e}")
            time.sleep(delay * 3)
            continue

    if limit:
        all_trials = all_trials[:limit]

    print(f"List scrape complete: {len(all_trials):,} trial stubs")
    return all_trials


# ------------------------------------------------------------------
# Step 2: Fetch individual trial detail pages
# ------------------------------------------------------------------
def parse_detail_page(soup: BeautifulSoup, proj_id: str) -> dict:
    """
    Extract fields from a trial detail page (showprojEN.html?proj=N).
    The detail page uses a label/value table layout.
    """
    detail = {"proj_id": proj_id}

    # Detail pages use <td class="td1"> for labels, next <td> for values
    rows = soup.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) >= 2:
            label = cells[0].get_text(strip=True).rstrip(":")
            value = cells[1].get_text(strip=True)
            if label:
                detail[label] = value

    return detail


def scrape_details(stubs: list[dict], delay: float = DELAY,
                   checkpoint_path: str = "chictr_details_checkpoint.jsonl") -> list[dict]:
    """
    Fetch detail pages for each trial stub.
    Saves a checkpoint file so you can resume if interrupted.
    """
    checkpoint = Path(checkpoint_path)

    # Load existing checkpoint if present
    done_ids = set()
    results = []
    if checkpoint.exists():
        with open(checkpoint) as f:
            for line in f:
                rec = json.loads(line)
                done_ids.add(rec.get("proj_id"))
                results.append(rec)
        print(f"Resuming from checkpoint: {len(done_ids):,} already fetched")

    remaining = [s for s in stubs if s["proj_id"] not in done_ids]
    print(f"Fetching details for {len(remaining):,} trials...")

    with open(checkpoint, "a") as f:
        for i, stub in enumerate(remaining):
            proj_id = stub["proj_id"]
            if not proj_id:
                continue

            time.sleep(delay)
            try:
                url = f"{DETAIL_URL}?proj={proj_id}"
                resp = requests.get(url, headers=HEADERS, timeout=15)
                soup = BeautifulSoup(resp.text, "html.parser")
                detail = parse_detail_page(soup, proj_id)
                detail.update(stub)  # merge in list-level fields
                results.append(detail)
                f.write(json.dumps(detail) + "\n")

                if (i + 1) % 100 == 0:
                    print(f"  {i+1:,}/{len(remaining):,} detail pages fetched")

            except Exception as e:
                print(f"  proj={proj_id}: ERROR — {e}")
                time.sleep(delay * 3)
                continue

    print(f"Detail scrape complete: {len(results):,} trials")
    return results


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", nargs="*", default=["9", "13"],
                        help="Phase codes: 9=PhaseI, 10=PhaseII, 13=PhaseI+II (default: 9 13)")
    parser.add_argument("--studytype", default="1",
                        help="Study type code: 1=Interventional (default)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap total trials (useful for testing)")
    parser.add_argument("--list-only", action="store_true",
                        help="Only scrape the list, skip detail pages")
    parser.add_argument("--delay", type=float, default=DELAY,
                        help=f"Delay between requests in seconds (default: {DELAY})")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = Path("data/chictr")
    out_dir.mkdir(parents=True, exist_ok=True)

    all_stubs = []
    for phase in (args.phase or [""]):
        stubs = scrape_list(
            phase=phase,
            studytype=args.studytype,
            limit=args.limit,
            delay=args.delay,
        )
        all_stubs.extend(stubs)

    # Deduplicate by regno
    seen = set()
    unique_stubs = []
    for s in all_stubs:
        if s["regno"] not in seen:
            seen.add(s["regno"])
            unique_stubs.append(s)
    print(f"Unique trials after dedup: {len(unique_stubs):,}")

    # Save stubs
    stubs_path = out_dir / f"chictr_stubs_{timestamp}.parquet"
    pd.DataFrame(unique_stubs).to_parquet(stubs_path, index=False)
    print(f"Stubs saved → {stubs_path}")

    if not args.list_only:
        details = scrape_details(
            unique_stubs,
            delay=args.delay,
            checkpoint_path=str(out_dir / f"chictr_details_{timestamp}.jsonl"),
        )
        details_path = out_dir / f"chictr_details_{timestamp}.parquet"
        pd.DataFrame(details).to_parquet(details_path, index=False)
        print(f"Details saved → {details_path}")