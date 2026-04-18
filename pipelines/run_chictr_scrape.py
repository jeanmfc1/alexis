"""
run_chictr_scrape.py -- Interactive launcher for the ChiCTR Stage 1 scraper.

Presents timeframe and output choices, then invokes
pipelines/scrape_chictr_playwright.py in-process.

Usage:
    PYTHONPATH=. python pipelines/run_chictr_scrape.py
"""

from __future__ import annotations
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

W = 60

STUBS_DIR = Path("storage")
DEFAULT_STUBS = STUBS_DIR / "chictr_playwright_stubs.parquet"


# -----------------------------------------------------------------
# Prompt helpers (style mirrors analytics/run_update_categorizer.py)
# -----------------------------------------------------------------

def _yn(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        raw = input(f"  {prompt}{suffix}: ").strip().lower()
        if raw == "":
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  Please enter Y or N.")


def _pick(options, label, default_idx=1):
    print(f"\n  Available {label}:")
    print(f"  {'-' * 55}")
    for i, (short, desc) in enumerate(options, 1):
        print(f"    {i:2d}) {short:20s}  {desc}")
    print()
    while True:
        raw = input(f"  Select {label} [1-{len(options)}, default {default_idx}]: ").strip()
        if raw == "":
            return default_idx
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return idx
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(options)}.")


def _prompt_date(label, default=None):
    hint = f" [default: {default}]" if default else " [blank = none]"
    while True:
        raw = input(f"  {label}{hint}: ").strip()
        if raw == "":
            return default
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print("  Please use YYYY-MM-DD format.")


def _prompt_int(label, default=None):
    hint = f" [default: {default}]" if default is not None else " [blank = no limit]"
    while True:
        raw = input(f"  {label}{hint}: ").strip()
        if raw == "":
            return default
        try:
            n = int(raw)
            if n > 0:
                return n
        except ValueError:
            pass
        print("  Please enter a positive integer.")


# -----------------------------------------------------------------
# Config assembly
# -----------------------------------------------------------------

def prompt_config():
    today = date.today()
    print()
    print("=" * W)
    print("  ChiCTR Stage 1 Scraper -- Interactive")
    print("=" * W)
    print(f"  Today: {today}")

    # -- Timeframe --
    options = [
        ("last-7-days",   "trials registered in the last  7 days"),
        ("last-30-days",  "trials registered in the last 30 days"),
        ("last-90-days",  "trials registered in the last 90 days"),
        ("year-to-date",  "trials registered since Jan 1 of this year"),
        ("custom",        "enter --since / --until manually"),
        ("full",          "no date filter (scrapes entire corpus, ~4h)"),
    ]
    pick = _pick(options, "timeframe", default_idx=1)

    since = None
    until = None
    if pick == 1:
        since = today - timedelta(days=7)
    elif pick == 2:
        since = today - timedelta(days=30)
    elif pick == 3:
        since = today - timedelta(days=90)
    elif pick == 4:
        since = date(today.year, 1, 1)
    elif pick == 5:
        print()
        since = _prompt_date("  --since  (YYYY-MM-DD)")
        until = _prompt_date("  --until  (YYYY-MM-DD)")
    elif pick == 6:
        if not _yn("\n  Full scrape is slow (~4 h). Continue?", default=False):
            print("  Cancelled.")
            sys.exit(0)

    # -- Limit --
    print()
    limit = _prompt_int("  Max trials to keep (safety cap)", default=None)

    # -- Browser mode --
    print()
    headless = _yn("Run Chromium headless?", default=True)

    # -- Output --
    print()
    if pick in (1, 2, 3, 4, 5) and (since or until):
        stem = f"chictr_stubs_{since}_to_{until or today}.parquet"
        default_out = STUBS_DIR / stem
    else:
        default_out = DEFAULT_STUBS
    raw = input(f"  Output parquet [default: {default_out}]: ").strip()
    out_path = Path(raw) if raw else default_out

    if out_path.exists():
        print(f"  ! {out_path} already exists.")
        if not _yn("    Overwrite?", default=False):
            print("  Cancelled.")
            sys.exit(0)

    # -- Confirmation --
    print()
    print(f"  {'-' * 55}")
    print(f"  Since:     {since}")
    print(f"  Until:     {until}")
    print(f"  Limit:     {limit}")
    print(f"  Headless:  {headless}")
    print(f"  Output:    {out_path}")
    print(f"  {'-' * 55}")
    print()
    if not _yn("Proceed?", default=True):
        print("  Cancelled.")
        sys.exit(0)

    return {
        "since":    since,
        "until":    until,
        "limit":    limit,
        "headless": headless,
        "out_path": out_path,
    }


# -----------------------------------------------------------------
# Main
# -----------------------------------------------------------------

def main():
    config = prompt_config()

    from pipelines.scrape_chictr_playwright import scrape
    import pandas as pd

    trials = scrape(
        headless=config["headless"],
        limit=config["limit"],
        since=config["since"],
        until=config["until"],
    )

    if not trials:
        print("\nNo trials retrieved.")
        sys.exit(0)

    df = pd.DataFrame(trials)
    config["out_path"].parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(config["out_path"], index=False)

    print()
    print("=" * W)
    print("  SUMMARY")
    print("=" * W)
    print(f"  Trials scraped: {len(df):,}")
    print(f"  Output:         {config['out_path']}")
    print()
    if "study_type" in df.columns:
        print("  Study type breakdown:")
        for k, v in df["study_type"].value_counts().head(10).items():
            print(f"    {str(k):40s} {v:>6,}")
    print()
    print("  Sample rows:")
    cols = [c for c in ("regno", "title", "sponsor", "reg_date") if c in df.columns]
    print(df[cols].head(5).to_string())


if __name__ == "__main__":
    main()
