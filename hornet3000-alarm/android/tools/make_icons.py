#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Erzeugt die Start-Symbole der Android-App (res/drawable*/icon.png): Sechseck (Wabe) in Bernstein mit dunklen Streifen.
Eigene Gestaltung. Aufruf im Ordner android/:  python3 tools/make_icons.py"""
import math
import os

from PIL import Image, ImageDraw

SIZES = {"drawable-ldpi": 36, "drawable-mdpi": 48, "drawable-hdpi": 72, "drawable-xhdpi": 96,
         "drawable-xxhdpi": 144, "drawable-xxxhdpi": 192, "drawable": 96}


def icon(n: int) -> Image.Image:
    s = n * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c, r = s / 2, s * 0.46
    pts = [(c + r * math.cos(math.radians(60 * i + 30)), c + r * math.sin(math.radians(60 * i + 30))) for i in range(6)]
    d.polygon(pts, fill=(242, 176, 30, 255))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    stripes = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stripes)
    for k in (-1, 0, 1):
        y0 = c + k * s * 0.22 - s * 0.05
        sd.rectangle([0, y0, s, y0 + s * 0.10], fill=(40, 28, 10, 255))
    im = Image.composite(Image.alpha_composite(im, stripes), im, mask)
    ImageDraw.Draw(im).polygon(pts, outline=(40, 28, 10, 255), width=max(2, s // 40))
    return im.resize((n, n), Image.LANCZOS)


if __name__ == "__main__":
    for name, n in SIZES.items():
        os.makedirs(f"res/{name}", exist_ok=True)
        icon(n).save(f"res/{name}/icon.png", optimize=True)
    print("Symbole geschrieben")
