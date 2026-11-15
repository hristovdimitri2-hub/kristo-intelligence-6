# -*- coding: utf-8 -*-
"""Generate 256x256 Glama listing thumbnails (local only, never committed).

Run:  python docs/glama_thumbnails/generate.py
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.dirname(os.path.abspath(__file__))
SIZE = 256

BG = (13, 17, 23)        # #0D1117 — тъмен фон (GitHub dark)
GREEN = (46, 160, 67)    # #2EA043 — зелен акцент
WHITE = (230, 237, 243)


def _font(size, bold=True):
    names = ["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]
    for name in names:
        for base in ("C:/Windows/Fonts/", ""):
            try:
                return ImageFont.truetype(base + name, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _center_text(draw, xy, text, font, fill):
    """Draw text horizontally+vertically centered on xy."""
    x, y = xy
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    draw.text((x - (r - l) / 2 - l, y - (b - t) / 2 - t), text, font=font, fill=fill)


def variant_a():
    """Монограм „KI" голям в центъра + тънка зелена рамка."""
    img = Image.new("RGB", (SIZE, SIZE), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([8, 8, SIZE - 9, SIZE - 9], outline=GREEN, width=3)
    _center_text(d, (SIZE / 2, SIZE / 2 + 6), "KI", _font(128), GREEN)
    return img


def variant_b():
    """Зелен щит с „KI" вътре (защита/собственост)."""
    img = Image.new("RGB", (SIZE, SIZE), BG)
    d = ImageDraw.Draw(img)
    shield = [(128, 22), (218, 56), (218, 128), (128, 234), (38, 128), (38, 56)]
    d.polygon(shield, fill=GREEN)
    # вътрешен контур за дълбочина
    inner = [(128, 44), (198, 70), (198, 126), (128, 208), (58, 126), (58, 70)]
    d.polygon(inner, outline=(23, 88, 44), width=3)
    _center_text(d, (128, 118), "KI", _font(72), WHITE)
    return img


def variant_c():
    """Ончейн стил — възходяща линия/стрелка + малък блок."""
    img = Image.new("RGB", (SIZE, SIZE), BG)
    d = ImageDraw.Draw(img)
    # baseline (пунктирана)
    for x0 in range(24, 236, 16):
        d.line([x0, 200, x0 + 8, 200], fill=(48, 58, 70), width=2)
    # възходяща линия с върхове (price/transfer line)
    line = [(30, 190), (78, 150), (110, 168), (152, 112), (186, 128), (214, 74)]
    d.line(line, fill=GREEN, width=7, joint="curve")
    # стрелка накрая
    d.polygon([(226, 58), (226, 96), (188, 78)], fill=GREEN)
    d.line([(214, 74), (226, 68)], fill=GREEN, width=7)
    # блокче с „K" долу вляво (буквален on-chain блок)
    d.rectangle([30, 214, 62, 246], fill=GREEN)
    _center_text(d, (46, 231), "K", _font(22), BG)
    _center_text(d, (128, 232), "on-chain", _font(20, bold=False), (139, 148, 158))
    return img


def main():
    variants = {
        "glama_thumb_a_monogram.png": variant_a(),
        "glama_thumb_b_shield.png": variant_b(),
        "glama_thumb_c_onchain.png": variant_c(),
    }
    for name, img in variants.items():
        path = os.path.join(OUT, name)
        img.save(path, "PNG")
        kb = os.path.getsize(path) / 1024
        print(f"{name}: {img.size[0]}x{img.size[1]}, {kb:.1f} KB")
        # preview за проверка на четимост (ще се изтрие след прегледа)
        img.resize((64, 64), Image.LANCZOS).save(
            os.path.join(OUT, "preview_64_" + name), "PNG")
    print("готово ->", OUT)


if __name__ == "__main__":
    main()
