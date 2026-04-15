# pipelines/scrape_chictr_details.py
"""
ChiCTR detail page scraper using Playwright.
Fetches showprojEN.html?proj=<proj_id> for each trial stub.

Input:  storage/chictr_playwright_stubs.parquet (or --stubs path)
Output: storage/chictr_details.parquet

Usage:
    python pipelines/scrape_chictr_details.py
    python pipelines/scrape_chictr_details.py --stubs storage/chictr_playwright_stubs_partial.parquet
    python pipelines/scrape_chictr_details.py --from-year 2022
    python pipelines/scrape_chictr_details.py --limit 50
    python pipelines/scrape_chictr_details.py --resume

Changes from v1:
- wait_until changed from "networkidle" to "domcontentloaded" (~2s saved per page)
- DELAY_MIN/MAX reduced from 1.5-3.0s to 0.8-1.5s
- ETA now based on wall-clock rate instead of fetch-only avg (was wildly wrong before)
"""

import argparse
import json
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

DETAIL_BASE = "https://www.chictr.org.cn/showprojEN.html?proj="
CHECKPOINT_PATH = Path("storage/chictr_details_checkpoint.jsonl")
DELAY_MIN = 0.8   # reduced from 1.5
DELAY_MAX = 1.5   # reduced from 3.0
PROGRESS_EVERY = 10


# ------------------------------------------------------------------
# HTML parser
# ------------------------------------------------------------------

def _en_label_value(soup: BeautifulSoup, label_text: str) -> str | None:
    for tr in soup.find_all("tr", class_="en"):
        title_td = tr.find("td", class_="left_title")
        if not title_td:
            continue
        p = title_td.find("p", class_="en")
        if p and label_text.lower() in p.get_text().lower():
            for td in tr.find_all("td"):
                if "left_title" not in td.get("class", []):
                    text = td.get_text(" ", strip=True)
                    return text if text else None
    return None


def _en_span_value(soup: BeautifulSoup, class_name: str) -> str | None:
    el = soup.find("span", class_=class_name)
    return el.get_text(strip=True) if el else None


def _extract_interventions(soup: BeautifulSoup) -> str | None:
    for tr in soup.find_all("tr"):
        title_td = tr.find("td", class_="left_title")
        if not title_td or "Interventions" not in title_td.get_text():
            continue
        value_td = None
        for td in tr.find_all("td"):
            if "left_title" not in td.get("class", []):
                value_td = td
                break
        if not value_td:
            continue
        arms = []
        for sub_table in value_td.find_all("table"):
            group_name = intervention_text = None
            for row in sub_table.find_all("tr"):
                tds = row.find_all("td")
                if len(tds) < 2:
                    continue
                label = tds[0].get_text(strip=True)
                value = tds[1].get_text(strip=True)
                if "Group：" in label and not group_name:
                    group_name = value
                if "Intervention：" in label and not intervention_text:
                    intervention_text = value
            if group_name or intervention_text:
                part = f"{group_name or ''}: {intervention_text or ''}".strip(": ")
                if part:
                    arms.append(part)
        return " | ".join(arms) if arms else None
    return None


def parse_detail_page(html: str, proj_id: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = None
    title_el = soup.find("div", class_="project-tit")
    if title_el:
        p = title_el.find("p", class_="en")
        title = p.get_text(strip=True) if p else None

    return {
        "proj_id":            proj_id,
        "title_detail":       title,
        "target_disease":     _en_label_value(soup, "Target disease"),
        "phase":              _en_label_value(soup, "Study phase"),
        "study_design":       _en_label_value(soup, "Study design"),
        "study_type_detail":  _en_label_value(soup, "Study type"),
        "objectives":         _en_label_value(soup, "Objectives of Study"),
        "medicine_detail":    _en_label_value(soup, "Description for medicine"),
        "inclusion_criteria": _en_label_value(soup, "Inclusion criteria"),
        "exclusion_criteria": _en_label_value(soup, "Exclusion criteria"),
        "primary_sponsor":    _en_label_value(soup, "Primary sponsor"),
        "funding_source":     _en_label_value(soup, "Source(s) of funding"),
        "interventions_raw":  _extract_interventions(soup),
        "study_start":        _en_span_value(soup, "splaceTen3"),
        "study_end":          _en_span_value(soup, "splaceTen4"),
        "recruit_start":      _en_span_value(soup, "splaceTen5"),
        "recruit_end":        _en_span_value(soup, "splaceTen6"),
        "registration_date":  _en_span_value(soup, "splaceTen1"),
    }


# ------------------------------------------------------------------
# ETA helpers
# ------------------------------------------------------------------

def fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s}s"
    else:
        h, rem = divmod(int(seconds), 3600)
        m = rem // 60
        return f"{h}h {m}m"


def fmt_eta(seconds_remaining: float) -> str:
    eta_dt = datetime.now() + timedelta(seconds=seconds_remaining)
    if eta_dt.date() == datetime.now().date():
        return eta_dt.strftime("%H:%M:%S today")
    else:
        return eta_dt.strftime("%a %b %d at %H:%M:%S")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def load_stubs(stubs_path: str, from_year: int) -> pd.DataFrame:
    df = pd.read_parquet(stubs_path)
    print(f"Loaded {len(df):,} stubs from {stubs_path}")
    df["reg_date_parsed"] = pd.to_datetime(df["reg_date"], format="%Y/%m/%d", errors="coerce")
    df = df[df["reg_date_parsed"].dt.year >= from_year].copy()
    print(f"After {from_year}+ filter: {len(df):,} stubs")
    df = df[df["proj_id"].notna() & (df["proj_id"] != "")].copy()
    print(f"With valid proj_id: {len(df):,}")
    return df


def load_checkpoint() -> set[str]:
    done = set()
    if CHECKPOINT_PATH.exists():
        with open(CHECKPOINT_PATH) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if rec.get("proj_id"):
                        done.add(str(rec["proj_id"]))
                except Exception:
                    continue
        print(f"Resuming: {len(done):,} already fetched")
    return done


def scrape_details(
    stubs_path: str,
    from_year: int,
    limit: int,
    resume: bool,
    headless: bool,
) -> pd.DataFrame:

    df = load_stubs(stubs_path, from_year)
    done_ids = load_checkpoint() if resume else set()

    remaining = df[~df["proj_id"].astype(str).isin(done_ids)].copy()
    if limit:
        remaining = remaining.head(limit)

    total = len(remaining)
    print(f"To fetch: {total:,} detail pages")
    print(f"Started:  {datetime.now().strftime('%a %b %d %H:%M:%S')}")
    print()

    stealth = Stealth()

    fetch_times = []        # rolling window of per-page fetch seconds (display only)
    session_start = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        stealth.apply_stealth_sync(context)
        page = context.new_page()

        with open(CHECKPOINT_PATH, "a") as ckpt:
            for i, (_, row) in enumerate(remaining.iterrows()):
                proj_id = str(row["proj_id"])
                delay = random.uniform(DELAY_MIN, DELAY_MAX)
                time.sleep(delay)

                t_page = time.time()
                try:
                    page.goto(
                        f"{DETAIL_BASE}{proj_id}",
                        wait_until="domcontentloaded",   # was "networkidle" — ~2s faster per page
                        timeout=30000,
                    )
                    detail = parse_detail_page(page.content(), proj_id)
                    detail["regno"]      = row.get("regno")
                    detail["sponsor"]    = row.get("sponsor")
                    detail["study_type"] = row.get("study_type")
                    detail["reg_date"]   = row.get("reg_date")
                    detail["source_url"] = row.get("source_url")
                    detail["title_list"] = row.get("title")
                    ckpt.write(json.dumps(detail) + "\n")

                    page_elapsed = time.time() - t_page
                    fetch_times.append(page_elapsed)
                    if len(fetch_times) > 50:
                        fetch_times.pop(0)

                except Exception as e:
                    print(f"  proj={proj_id}: ERROR — {e}")
                    time.sleep(5)
                    continue

                # Progress + ETA every PROGRESS_EVERY records
                if (i + 1) % PROGRESS_EVERY == 0:
                    done_count      = i + 1
                    remaining_count = total - done_count
                    avg_fetch_sec   = sum(fetch_times) / len(fetch_times)
                    session_elapsed = time.time() - session_start
                    # Use wall-clock rate for ETA — includes sleep + overhead, not just fetch time
                    wall_rate_per_sec = done_count / session_elapsed          # pages/sec
                    secs_left         = remaining_count / wall_rate_per_sec   # accurate ETA
                    pages_per_min     = wall_rate_per_sec * 60

                    print(
                        f"  {done_count:,}/{total:,} fetched"
                        f"  |  fetch {avg_fetch_sec:.1f}s/page"
                        f"  |  {pages_per_min:.1f} pages/min"
                        f"  |  ~{fmt_duration(secs_left)} left"
                        f"  |  ETA {fmt_eta(secs_left)}"
                    )

        browser.close()

    # Final summary
    total_elapsed = time.time() - session_start
    print()
    print(f"Session complete: {fmt_duration(total_elapsed)} elapsed")
    print(f"Finished at:      {datetime.now().strftime('%a %b %d %H:%M:%S')}")

    # Read full checkpoint into dataframe
    records = []
    with open(CHECKPOINT_PATH) as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except Exception:
                continue

    out_df = pd.DataFrame(records).drop_duplicates(subset=["proj_id"])
    return out_df


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stubs",     default="storage/chictr_playwright_stubs.parquet")
    parser.add_argument("--from-year", type=int, default=2022)
    parser.add_argument("--limit",     type=int, default=None)
    parser.add_argument("--resume",    action="store_true", default=True)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.add_argument("--headless",  action="store_true", default=True)
    args = parser.parse_args()

    out_df = scrape_details(
        stubs_path=args.stubs,
        from_year=args.from_year,
        limit=args.limit,
        resume=args.resume,
        headless=args.headless,
    )

    out_path = Path("storage/chictr_details.parquet")
    out_df.to_parquet(out_path, index=False)
    print(f"\nSaved {len(out_df):,} records → {out_path}")

    print("\nField completeness (% non-null):")
    print((out_df.notnull().mean() * 100).round(1).sort_values(ascending=False).to_string())

    print("\nPhase breakdown:")
    print(out_df["phase"].value_counts().head(15).to_string())

    print("\nSample:")
    cols = ["regno", "target_disease", "interventions_raw", "phase", "reg_date"]
    print(out_df[cols].head(10).to_string())
