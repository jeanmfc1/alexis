# pipelines/scrape_chictr_playwright.py
"""
ChiCTR scraper using Playwright to bypass Alibaba Cloud WAF.
The WAF uses acw_sc__v2 JS challenge — requires real browser execution.
Playwright solves it automatically. playwright-stealth hides headless indicators.

Usage:
    python pipelines/scrape_chictr_playwright.py
    python pipelines/scrape_chictr_playwright.py --limit 100   # test run
    python pipelines/scrape_chictr_playwright.py --headless     # no browser window
"""

import argparse
import time
import json
import random
from datetime import date, datetime
import pandas as pd
from pathlib import Path
from playwright.sync_api import sync_playwright, Page
from playwright_stealth import Stealth


def parse_reg_date(s: str):
    """Parse ChiCTR reg_date strings. Tolerates YYYY/MM/DD, YYYY-MM-DD, or junk."""
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None


def filter_by_window(trials, since, until):
    """Return (kept, all_older_than_since). kept = trials whose reg_date is
    within [since, until] inclusive. all_older_than_since is True when every
    parseable row on this page is older than since. ChiCTR returns newest-first
    so this flag drives pagination short-circuit."""
    if not since and not until:
        return trials, False
    kept = []
    older_count = 0
    parsed_count = 0
    for t in trials:
        d = parse_reg_date(t.get("reg_date"))
        if d is None:
            kept.append(t)
            continue
        parsed_count += 1
        if since and d < since:
            older_count += 1
            continue
        if until and d > until:
            continue
        kept.append(t)
    all_older = parsed_count > 0 and older_count == parsed_count
    return kept, all_older


BASE_URL = "https://www.chictr.org.cn/searchprojEN.html"
DELAY_MIN = 1.5
DELAY_MAX = 3.0


def build_url(page_num: int, studytype: str = "1") -> str:
    return (
        f"{BASE_URL}?page={page_num}"
        f"&studytype={studytype}"
        f"&studystage=&recruitmentstatus=&btngo=btn"
    )


def get_total_count(page: Page) -> int:
    try:
        el = page.locator("span#data-totalEN")
        el.wait_for(timeout=15000)
        text = el.inner_text().strip().replace(",", "")
        return int(text)
    except Exception:
        return 0


def parse_results_page(page: Page) -> list[dict]:
    trials = []
    rows = page.locator("table.table1 tr").all()
    for row in rows[1:]:  # skip header
        cols = row.locator("td").all()
        if len(cols) < 5:
            continue
        try:
            regno = cols[1].inner_text(timeout=3000).strip()
            title_link = cols[2].locator("a").first
            title = title_link.inner_text(timeout=3000).strip()
            href = title_link.get_attribute("href") or ""
            proj_id = href.split("proj=")[-1].strip() if "proj=" in href else ""
            sponsor_el = cols[2].locator("p")
            sponsor = sponsor_el.inner_text(timeout=3000).strip() if sponsor_el.count() > 0 else ""
            study_type = cols[3].inner_text(timeout=3000).strip()
            reg_date = cols[4].inner_text(timeout=3000).strip()
            trials.append({
                "regno": regno,
                "proj_id": proj_id,
                "title": title,
                "sponsor": sponsor,
                "study_type": study_type,
                "reg_date": reg_date,
                "source_url": f"https://www.chictr.org.cn/showprojEN.html?proj={proj_id}",
            })
        except Exception:
            continue
    return trials


def scrape(headless: bool = True, limit: int = None,
           since=None, until=None) -> list[dict]:
    all_trials = []
    checkpoint_path = Path("storage/chictr_playwright_checkpoint.jsonl")
    Path("storage").mkdir(exist_ok=True)

    stealth = Stealth()

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

        # --- Page 1: get total count ---
        print("Loading page 1 to get total count...")
        page.goto(build_url(1), wait_until="networkidle", timeout=30000)
        time.sleep(2)

        total = get_total_count(page)
        if total == 0:
            time.sleep(3)
            total = get_total_count(page)

        if since or until:
            print(f"Total trials in ChiCTR (unfiltered): {total:,}")
            print(f"Window since={since} until={until} -- will stop early "
                  f"once rows pass the window.")
        else:
            print(f"Total trials: {total:,}")
        total_pages = (total + 9) // 10

        if limit:
            max_pages = min(total_pages, (limit + 9) // 10)
            print(f"Limiting to {limit} trials ({max_pages} pages)")
        else:
            max_pages = total_pages

        trials = parse_results_page(page)
        kept, all_older = filter_by_window(trials, since, until)
        all_trials.extend(kept)
        if since or until:
            print(f"  Page 1: {len(trials)} trials, kept {len(kept)} in window")
        else:
            print(f"  Page 1: {len(trials)} trials")
        if since and all_older and not kept:
            print("  Page 1 already older than --since; stopping.")
            browser.close()
            return all_trials

        # --- Pages 2+ ---
        for page_num in range(2, max_pages + 1):
            if limit and len(all_trials) >= limit:
                break

            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

            try:
                page.goto(
                    build_url(page_num),
                    wait_until="networkidle",
                    timeout=30000,
                )
                trials = parse_results_page(page)
                if not trials:
                    print(f"  Page {page_num}: empty — stopping")
                    break
                kept, all_older = filter_by_window(trials, since, until)
                all_trials.extend(kept)

                if since and all_older and not kept:
                    print(f"  Page {page_num}: all rows older than --since; stopping")
                    break

                # Per-page date progress so user can gauge how far back we are.
                page_dates = [parse_reg_date(t.get("reg_date")) for t in trials]
                page_dates = [d for d in page_dates if d is not None]
                if page_dates:
                    newest, oldest = max(page_dates), min(page_dates)
                    if since or until:
                        print(f"  Page {page_num}/{max_pages}  "
                              f"newest={newest} oldest={oldest}  "
                              f"kept {len(kept)}/{len(trials)}  "
                              f"total {len(all_trials):,}")
                    else:
                        print(f"  Page {page_num}/{max_pages}  "
                              f"newest={newest} oldest={oldest}  "
                              f"total {len(all_trials):,}")

                if page_num % 50 == 0:
                    with open(checkpoint_path, "w") as f:
                        for t in all_trials:
                            f.write(json.dumps(t) + "\n")
            except Exception as e:
                print(f"  Page {page_num}: ERROR — {e}")
                time.sleep(5)
                continue

        browser.close()

    if limit:
        all_trials = all_trials[:limit]

    print(f"\nTotal scraped: {len(all_trials):,}")
    return all_trials


def _parse_date_arg(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be YYYY-MM-DD, got {s!r}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--since", type=_parse_date_arg, default=None,
                        help="Only keep trials with reg_date >= YYYY-MM-DD; "
                             "stops paginating once an entire page is older.")
    parser.add_argument("--until", type=_parse_date_arg, default=None,
                        help="Only keep trials with reg_date <= YYYY-MM-DD.")
    args = parser.parse_args()

    if args.since or args.until:
        print(f"Window: since={args.since}  until={args.until}")

    trials = scrape(headless=args.headless, limit=args.limit,
                    since=args.since, until=args.until)

    if not trials:
        print("No trials retrieved.")
        return

    df = pd.DataFrame(trials)
    out_path = Path("storage/chictr_playwright_stubs.parquet")
    df.to_parquet(out_path, index=False)
    print(f"Saved → {out_path}")

    print(f"\nStudy type breakdown:")
    print(df["study_type"].value_counts().head(10).to_string())
    print(f"\nSample:")
    print(df[["regno", "title", "sponsor", "reg_date"]].head(5).to_string())


if __name__ == "__main__":
    main()
