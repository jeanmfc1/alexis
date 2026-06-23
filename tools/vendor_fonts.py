"""Vendor the Google Fonts used by ALEXIS for fully-offline rendering.

Fetches the Google Fonts CSS (with a modern browser UA so it serves woff2),
downloads every referenced woff2 into viz/vendor/fonts/, and writes a
self-contained viz/vendor/fonts.css with local @font-face URLs.

Run from the repo root:  python tools/vendor_fonts.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx

CSS_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Barlow+Condensed:wght@500;600;700"
    "&family=Barlow:wght@400;500"
    "&family=JetBrains+Mono:wght@400;500;600"
    "&display=swap"
)
# A modern Chrome UA so Google serves woff2 (not ttf).
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    out_dir = root / "viz" / "vendor" / "fonts"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[info] fetching font CSS ...")
    css = httpx.get(CSS_URL, headers={"User-Agent": UA}, timeout=30).text

    urls = sorted(set(re.findall(r"https://fonts\.gstatic\.com/[^)]+?\.woff2", css)))
    print(f"[info] {len(urls)} woff2 files referenced")

    mapping: dict[str, str] = {}
    for i, url in enumerate(urls):
        name = f"font_{i:02d}.woff2"
        data = httpx.get(url, headers={"User-Agent": UA}, timeout=30).content
        (out_dir / name).write_bytes(data)
        mapping[url] = f"fonts/{name}"
        print(f"  [ok] {name}  ({len(data):,} bytes)")

    for url, local in mapping.items():
        css = css.replace(url, local)

    css_path = root / "viz" / "vendor" / "fonts.css"
    css_path.write_text(css, encoding="utf-8")
    print(f"[ok] wrote {css_path} ({len(css):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
