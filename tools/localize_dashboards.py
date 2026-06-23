"""Rewrite CDN references in generated dashboard HTML to local vendor paths.

New dashboards already come out local (the template is vendored). This fixes
any pre-existing *_live.html artifacts so every dashboard renders offline.

Run from the repo root:  python tools/localize_dashboards.py
"""

from __future__ import annotations

import re
from pathlib import Path

REPLACEMENTS = {
    "https://unpkg.com/react@18/umd/react.production.min.js": "vendor/react.production.min.js",
    "https://unpkg.com/react-dom@18/umd/react-dom.production.min.js": "vendor/react-dom.production.min.js",
    "https://unpkg.com/recharts@2.12.7/umd/Recharts.js": "vendor/recharts.min.js",
    "https://unpkg.com/@babel/standalone/babel.min.js": "vendor/babel.min.js",
}
# The Google Fonts <link ... css2 ...> -> local fonts.css
FONTS_LINK_RE = re.compile(
    r'<link[^>]*fonts\.googleapis\.com/css2[^>]*>', re.IGNORECASE)
PRECONNECT_RE = re.compile(
    r'\s*<link[^>]*rel="preconnect"[^>]*fonts\.(googleapis|gstatic)\.com[^>]*>',
    re.IGNORECASE)


_RECHARTS_TAG = '<script src="vendor/recharts.min.js"></script>'
_PROPTYPES_TAG = '<script src="vendor/prop-types.min.js"></script>'

# Bootstrap that compiles the app with the CLASSIC JSX runtime (the in-browser
# Babel default uses the automatic runtime, which emits an unresolvable import
# and blanks the dashboard).
_BOOTSTRAP = """  <script>
    (function () {
      var src = document.getElementById("alexis-app-src");
      if (!src) return;
      try {
        var out = Babel.transform(src.textContent, {
          presets: [["react", { runtime: "classic" }]]
        }).code;
        var s = document.createElement("script");
        s.textContent = out;
        document.body.appendChild(s);
      } catch (e) {
        var root = document.getElementById("root");
        if (root) root.innerHTML =
          '<div style="padding:32px;font-family:monospace;color:#EF4444">' +
          'Dashboard failed to compile: ' + String(e) + '</div>';
        if (window.console) console.error(e);
      }
    })();
  </script>
</body>"""


def localize(text: str) -> tuple[str, int]:
    n = 0
    for cdn, local in REPLACEMENTS.items():
        if cdn in text:
            text = text.replace(cdn, local)
            n += 1
    # Recharts UMD needs a PropTypes global; ensure prop-types loads first.
    if _RECHARTS_TAG in text and _PROPTYPES_TAG not in text:
        text = text.replace(_RECHARTS_TAG, _PROPTYPES_TAG + "\n  " + _RECHARTS_TAG, 1)
        n += 1
    # Take the app script out of Babel's auto-transform (which uses the broken
    # automatic runtime) and compile it via the classic-runtime bootstrap.
    if "text/alexis-jsx" not in text:
        for tag in ('<script type="text/babel" data-presets="react">',
                    '<script type="text/babel">'):
            if tag in text:
                text = text.replace(
                    tag, '<script type="text/alexis-jsx" id="alexis-app-src">', 1)
                n += 1
                break
    if ('id="alexis-app-src"' in text
            and 'getElementById("alexis-app-src")' not in text
            and "</body>" in text):
        text = text.replace("</body>", _BOOTSTRAP, 1)
        n += 1
    if FONTS_LINK_RE.search(text):
        text = FONTS_LINK_RE.sub('<link href="vendor/fonts.css" rel="stylesheet" />', text)
        n += 1
    text, dropped = PRECONNECT_RE.subn("", text)
    n += dropped
    return text, n


def main() -> int:
    viz = Path(__file__).resolve().parent.parent / "viz"
    changed = 0
    for html in sorted(viz.glob("*.html")):
        original = html.read_text(encoding="utf-8", errors="replace")
        updated, n = localize(original)
        if n and updated != original:
            html.write_text(updated, encoding="utf-8")
            print(f"  [ok] localized {html.name} ({n} refs)")
            changed += 1
        else:
            print(f"  [info] {html.name}: already local / nothing to do")
    print(f"[ok] {changed} file(s) localized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
