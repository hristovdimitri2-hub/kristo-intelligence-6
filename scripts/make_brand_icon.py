# -*- coding: utf-8 -*-
"""Render the Bazaar icon as a PNG, because SVG is not an accepted format.

WHY THIS FILE EXISTS. `resource.iconUrl` is the picture an agent's directory
shows next to the listing. Our 402 advertised
`/static/icons/kristo.svg`. The CDP discovery docs are explicit about the
formats that field accepts — JPG, JPEG, PNG, WebP and GIF — and say SVG is NOT
supported:

    "Set `resource.iconUrl` in your endpoint's payment-required response to a
     publicly accessible image. Supported formats are JPG, JPEG, PNG, WebP, and
     GIF. SVG is not supported."
    -- docs.cdp.coinbase.com/x402/seller/get-discovered

So the one format we published was the one format the index cannot use, and
`tests/test_bazaar_declaration.py` asserted the SVG on purpose. A test can lock
in a mistake as easily as it locks in a fix.

The SVG is still served: it is the web favicon and a browser is not the Bazaar.
This script draws the SAME design as `/static/icons/kristo.svg` as a raster, so
the icon does not have to be a binary nobody can regenerate. Run it from the
repository root:

    python scripts/make_brand_icon.py

It is deterministic — the same input geometry produces byte-identical output —
so re-running it is a no-op in review, not churn.
"""
from __future__ import annotations

import sys
from pathlib import Path

# The design, in the SVG's own 64x64 coordinate space. Kept as literals next to
# the SVG's literals so the two can be compared by eye in one place.
VIEWBOX = 64
SCALE = 8                     # 64 * 8 = 512px, a square directory icon
BACKGROUND = (0x0F, 0x17, 0x2A, 255)   # #0f172a
ACCENT = (0x38, 0xBD, 0xF8, 255)       # #38bdf8
CORNER_RADIUS = 14
RING_RADIUS = 18
RING_WIDTH = 4
CORE_RADIUS = 7
TICK_LENGTH = 10
TICK_WIDTH = 4
TRANSPARENT = (0, 0, 0, 0)

OUT = Path(__file__).resolve().parents[1] / "static" / "icons" / "kristo.png"


def render(size: int = VIEWBOX * SCALE):
    """Draw the mark. Raises ImportError with a usable message if PIL is absent."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:  # pragma: no cover - tooling only, never imported at runtime
        raise SystemExit(
            "Pillow is needed to REGENERATE this icon (pip install pillow). "
            "It is not needed to serve it: the PNG is committed.")

    s = size / float(VIEWBOX)
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    d = ImageDraw.Draw(img)

    # The rounded plate.
    d.rounded_rectangle([0, 0, size - 1, size - 1],
                        radius=CORNER_RADIUS * s, fill=BACKGROUND)

    # The ring, then the core.
    c = size / 2.0
    r = RING_RADIUS * s
    d.ellipse([c - r, c - r, c + r, c + r],
              outline=ACCENT, width=max(1, int(round(RING_WIDTH * s))))

    cr = CORE_RADIUS * s
    d.ellipse([c - cr, c - cr, c + cr, c + cr], fill=ACCENT)

    # Four ticks: up, down, left, right — drawn from the ring outward, exactly
    # where the SVG's `M32 4v10` family puts them.
    w = max(1, int(round(TICK_WIDTH * s)))
    half = w / 2.0
    inner = size / 2.0 - (VIEWBOX / 2.0 - 4) * s      # 4 units from the edge
    outer = inner + TICK_LENGTH * s
    for box in (
        [c - half, inner, c + half, outer],           # top
        [c - half, size - outer, c + half, size - inner],  # bottom
        [inner, c - half, outer, c + half],           # left
        [size - outer, c - half, size - inner, c + half],  # right
    ):
        d.rounded_rectangle(box, radius=half, fill=ACCENT)

    return img


def main() -> int:
    img = render()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # optimize=True keeps the file small; no timestamp chunks, so the bytes are
    # reproducible for a given Pillow build.
    img.save(OUT, format="PNG", optimize=True)
    print("wrote %s (%d bytes, %dx%d)"
          % (OUT, OUT.stat().st_size, img.width, img.height))
    return 0


if __name__ == "__main__":
    sys.exit(main())
