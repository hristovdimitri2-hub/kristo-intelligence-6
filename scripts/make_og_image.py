"""Generate the social-share (Open Graph) card for the public pages.

Run:  python scripts/make_og_image.py

Writes static/og/kristo-og.png at the 1200x630 size that Open Graph and Twitter
cards expect. Deliberately contains NO price: a number baked into a PNG cannot be
checked by the price sweep, and the old phantom "$0.05" survived for months
exactly because it was written into places nothing verified. Brand and protocol
names only.

No network access, no repository state is read.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
BG = (11, 15, 26)
PANEL = (17, 23, 38)
LINE = (30, 42, 68)
TEXT = (219, 228, 255)
MUTED = (130, 148, 184)
ACCENT = (96, 165, 250)
GREEN = (74, 222, 128)

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "static", "og")
OUT_PATH = os.path.join(OUT_DIR, "kristo-og.png")

REGULAR = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
           "C:/Windows/Fonts/DejaVuSans.ttf"]
BOLD = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/DejaVuSans-Bold.ttf"]


def load(candidates, size):
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def centred(draw, text, font, y, fill, width=W):
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(((width - (right - left)) / 2 - left, y), text, font=font, fill=fill)
    return bottom - top


def chip(draw, x, y, label, font, fill, border):
    pad_x, pad_y = 22, 13
    left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
    w, h = right - left, bottom - top
    draw.rounded_rectangle([x, y, x + w + pad_x * 2, y + h + pad_y * 2],
                           radius=999, fill=fill, outline=border, width=2)
    draw.text((x + pad_x - left, y + pad_y - top), label, font=font, fill=TEXT)
    return w + pad_x * 2


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Soft vignette-ish panel so the card does not look like flat black.
    draw.rounded_rectangle([36, 36, W - 36, H - 36], radius=28,
                           fill=PANEL, outline=LINE, width=3)

    title = load(BOLD, 74)
    sub = load(REGULAR, 33)
    small = load(REGULAR, 25)

    centred(draw, "KRISTO INTELLIGENCE", title, 172, TEXT)

    # Accent rule under the wordmark.
    draw.rounded_rectangle([W / 2 - 110, 278, W / 2 + 110, 286], radius=4,
                           fill=ACCENT)

    centred(draw, "DeFi market intelligence API for AI agents", sub, 316, MUTED)
    centred(draw, "No API keys - the HTTP 402 response is the checkout", sub,
            362, MUTED)

    labels = ["x402", "USDC on Base", "paid per call"]
    widths = []
    for label in labels:
        left, top, right, bottom = draw.textbbox((0, 0), label, font=small)
        widths.append(right - left + 44)
    gap = 18
    total = sum(widths) + gap * (len(labels) - 1)
    x = (W - total) / 2
    for label, width in zip(labels, widths):
        chip(draw, x, 452, label, small, BG, LINE)
        x += width + gap

    # Green live dot on the panel edge - reads as "operational" at a glance.
    draw.ellipse([W - 108, 76, W - 84, 100], fill=GREEN)

    img.save(OUT_PATH, "PNG", optimize=True)
    print("wrote %s (%d x %d, %d bytes)"
          % (OUT_PATH, W, H, os.path.getsize(OUT_PATH)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
