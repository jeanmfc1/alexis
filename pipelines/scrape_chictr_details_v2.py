# pipelines/scrape_chictr_details_v2.py
"""
ChiCTR detail page scraper — v2 (faster)
=========================================
Optimizations over v1:
1. httpx first, Playwright fallback — skips browser overhead for pages
   that serve full HTML without JS rendering (~80% expected)
2. domcontentloaded instead of networkidle — 2-4x faster per Playwright page
3. Async concurrent workers — N pages fetched in parallel
4. Progress every 10 records instead of every 100

The existing checkpoint file is fully compatible — resume works as before.

New output column: _fetch_method ("httpx" or "playwright") — lets you
measure httpx hit rate after a test run.

Usage:
    python pipelines/scrape_chictr_details_v2.py --limit 50           # test
    python pipelines/scrape_chictr_details_v2.py --workers 3          # concurrent
    python pipelines/scrape_chictr_details_v2.py --resume             # continue from checkpoint
    python pipelines/scrape_chictr_details_v2.py --workers 1          # safe/slow mode

Install new dependency first:
    pip install httpx
"""

import argparse
import asyncio
import json
import random
import time
from pathlib import Path

import httpx
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

DETAIL_BASE     = "https://www.chictr.org.cn/showprojEN.html?proj="
CHECKPOINT_PATH = Path("storage/chictr_details_checkpoint.jsonl")
DELAY_MIN       = 1.5
DELAY_MAX       = 3.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


# ─────────────────────────────────────────────────────────────────────────────
# HTML parsers (shared with v1 — identical output schema)
# ─────────────────────────────────────────────────────────────────────────────

def _en_label_value(soup, label_text):
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


def _en_span_value(soup, class_name):
    el = soup.find("span", class_=class_name)
    return el.get_text(strip=True) if el else None


def _extract_interventions(soup):
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


def _html_looks_valid(html: str) -> bool:
    """Check that the HTML has actual ChiCTR trial content."""
    return "project-tit" in html or "left_title" in html


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


# ─────────────────────────────────────────────────────────────────────────────
# Async worker
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_one(
    proj_id: str,
    row: dict,
    http_client: httpx.AsyncClient,
    pw_page,                        # Playwright page (one per worker)
    ckpt_lock: asyncio.Lock,
    ckpt_file,
    counters: dict,
) -> dict | None:
    url = f"{DETAIL_BASE}{proj_id}"
    await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    detail = None
    fetch_method = None

    # ── Try httpx first ──────────────────────────────────────────
    try:
        resp = await http_client.get(url, timeout=15)
        if resp.status_code == 200 and _html_looks_valid(resp.text):
            detail = parse_detail_page(resp.text, proj_id)
            fetch_method = "httpx"
            counters["httpx"] += 1
    except Exception:
        pass

    # ── Playwright fallback ──────────────────────────────────────
    if detail is None:
        try:
            await pw_page.goto(url, wait_until="domcontentloaded", timeout=25000)
            html = await pw_page.content()
            if _html_looks_valid(html):
                detail = parse_detail_page(html, proj_id)
                fetch_method = "playwright"
                counters["playwright"] += 1
            else:
                counters["failed"] += 1
                return None
        except Exception as e:
            counters["failed"] += 1
            print(f"\n  proj={proj_id}: ERROR — {e}")
            return None

    # ── Merge list-level fields ──────────────────────────────────
    detail["regno"]        = row.get("regno")
    detail["sponsor"]      = row.get("sponsor")
    detail["study_type"]   = row.get("study_type")
    detail["reg_date"]     = row.get("reg_date")
    detail["source_url"]   = row.get("source_url")
    detail["title_list"]   = row.get("title")
    detail["_fetch_method"] = fetch_method

    # ── Write to checkpoint ──────────────────────────────────────
    async with ckpt_lock:
        ckpt_file.write(json.dumps(detail) + "\n")
        ckpt_file.flush()
        counters["total"] += 1
        if counters["total"] % 10 == 0:
            httpx_pct = counters["httpx"] / max(counters["total"], 1) * 100
            print(
                f"  {counters['total']:,} fetched  "
                f"[httpx={counters['httpx']:,} ({httpx_pct:.0f}%)  "
                f"playwright={counters['playwright']:,}  "
                f"failed={counters['failed']:,}]",
                end="\r",
                flush=True,
            )

    return detail


# ─────────────────────────────────────────────────────────────────────────────
# Main async loop
# ─────────────────────────────────────────────────────────────────────────────

async def scrape_async(remaining: pd.DataFrame, num_workers: int, headless: bool):
    stealth = Stealth()
    counters = {"total": 0, "httpx": 0, "playwright": 0, "failed": 0}
    ckpt_lock = asyncio.Lock()
    queue: asyncio.Queue = asyncio.Queue()

    for _, row in remaining.iterrows():
        await queue.put(row)

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as http_client:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            )

            # One context + page per worker
            pages = []
            for _ in range(num_workers):
                ctx = await browser.new_context(
                    user_agent=HEADERS["User-Agent"],
                    viewport={"width": 1280, "height": 800},
                    locale="en-US",
                )
                stealth.apply_stealth_sync(ctx)
                pages.append(await ctx.new_page())

            with open(CHECKPOINT_PATH, "a") as ckpt_file:

                async def worker(pw_page):
                    while True:
                        try:
                            row = queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        proj_id = str(row.get("proj_id", ""))
                        await fetch_one(
                            proj_id, row, http_client, pw_page,
                            ckpt_lock, ckpt_file, counters,
                        )
                        queue.task_done()

                await asyncio.gather(*[worker(page) for page in pages])

            await browser.close()

    print()  # newline after \r progress
    return counters


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def load_stubs(stubs_path: str, from_year: int) -> pd.DataFrame:
    df = pd.read_parquet(stubs_path)
    print(f"Loaded {len(df):,} stubs from {stubs_path}")
    df["reg_date_parsed"] = pd.to_datetime(df["reg_date"], format="%Y/%m/%d", errors="coerce")
    df = df[df["reg_date_parsed"].dt.year >= from_year].copy()
    print(f"After {from_year}+ filter: {len(df):,} stubs")
    df = df[df["proj_id"].notna() & (df["proj_id"] != "")].copy()
    print(f"With valid proj_id: {len(df):,}")
    return df


def load_checkpoint() -> set:
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stubs",     default="storage/chictr_playwright_stubs.parquet")
    parser.add_argument("--from-year", type=int, default=2022)
    parser.add_argument("--limit",     type=int, default=None)
    parser.add_argument("--workers",   type=int, default=2)
    parser.add_argument("--resume",    action="store_true", default=True)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.add_argument("--headless",  action="store_true", default=True)
    args = parser.parse_args()

    df = load_stubs(args.stubs, args.from_year)
    done_ids = load_checkpoint() if args.resume else set()
    remaining = df[~df["proj_id"].astype(str).isin(done_ids)].copy()
    if args.limit:
        remaining = remaining.head(args.limit)

    print(f"To fetch: {len(remaining):,} detail pages")
    print(f"Workers:  {args.workers}")
    print(f"Strategy: httpx first → Playwright fallback (domcontentloaded)")
    print()

    t0 = time.time()
    counters = asyncio.run(scrape_async(remaining, args.workers, args.headless))
    elapsed  = time.time() - t0

    print(f"\nDone in {elapsed/60:.1f} minutes")
    print(f"  httpx:      {counters['httpx']:,} ({counters['httpx']/max(counters['total'],1):.1%})")
    print(f"  playwright: {counters['playwright']:,} ({counters['playwright']/max(counters['total'],1):.1%})")
    print(f"  failed:     {counters['failed']:,}")

    # Build final parquet from checkpoint
    records = []
    with open(CHECKPOINT_PATH) as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except Exception:
                continue

    out_df = pd.DataFrame(records).drop_duplicates(subset=["proj_id"])
    out_path = Path("storage/chictr_details.parquet")
    out_df.to_parquet(out_path, index=False)
    print(f"\nSaved {len(out_df):,} records → {out_path}")

    print("\nField completeness (% non-null):")
    print((out_df.notnull().mean() * 100).round(1).sort_values(ascending=False).to_string())

    print("\nPhase breakdown:")
    print(out_df["phase"].value_counts().head(15).to_string())

    if "_fetch_method" in out_df.columns:
        print("\nFetch method breakdown (new records only):")
        print(out_df["_fetch_method"].value_counts().to_string())
