"""Generate packaging/alexis.ico - a benzene-ring app icon in the ALEXIS palette.

Draws a pointy-top hexagon with the aromatic inner ring + node dots, on a dark
rounded-square background, at high resolution, then saves a multi-size .ico.

Run from the repo root:  python tools/make_icon.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

# Brand palette
BG      = (12, 17, 24, 255)      # --surf  #0C1118
BORDER  = (26, 40, 64, 255)      # --border #1A2840
CYAN    = (0, 207, 255, 255)     # --cyan  #00CFFF
BLUE    = (59, 130, 246, 255)    # --blue  #3B82F6


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(4))


def _hexagon(cx, cy, r):
    # pointy-top hexagon (vertex at top)
    return [
        (cx + r * math.cos(math.radians(90 + 60 * i)),
         cy - r * math.sin(math.radians(90 + 60 * i)))
        for i in range(6)
    ]


def _rounded_bg(size, radius, fill, outline, ow):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius,
                        fill=fill, outline=outline, width=ow)
    return img, d


def make(px: int = 1024) -> Image.Image:
    img, d = _rounded_bg(px, int(px * 0.22), BG, BORDER, max(2, px // 128))
    cx = cy = px / 2
    R = px * 0.30
    lw = max(3, int(px * 0.030))

    verts = _hexagon(cx, cy, R)

    # Outer ring (hexagon) — cyan->blue per edge for a subtle gradient feel.
    for i in range(6):
        a = verts[i]
        b = verts[(i + 1) % 6]
        col = _lerp(CYAN, BLUE, i / 5)
        d.line([a, b], fill=col, width=lw, joint="curve")

    # Aromatic inner ring (the classic circle inside benzene).
    ir = R * 0.55
    d.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], outline=CYAN, width=max(2, lw - 2))

    # Node dots at each vertex.
    dot = max(4, int(px * 0.028))
    for i, (x, y) in enumerate(verts):
        col = _lerp(CYAN, BLUE, i / 5)
        d.ellipse([x - dot, y - dot, x + dot, y + dot], fill=col)

    return img


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    out = root / "packaging" / "alexis.ico"
    out.parent.mkdir(parents=True, exist_ok=True)

    base = make(1024)
    icon = base.resize((256, 256), Image.LANCZOS)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icon.save(out, format="ICO", sizes=sizes)

    # Also drop a PNG preview for docs / quick viewing.
    base.resize((256, 256), Image.LANCZOS).save(root / "packaging" / "alexis_icon.png")
    print(f"[ok] wrote {out} ({out.stat().st_size:,} bytes) + alexis_icon.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
