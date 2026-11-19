# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Erzeugt die PWA-Icons (Wabe mit Alarmzelle). Einmalig ausgeführt; Ergebnis liegt in web/assets/icons."""
import math
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).parent / "web" / "assets" / "icons"
OUT.mkdir(parents=True, exist_ok=True)
BG, AMBER, ORANGE, LEAF = (27, 38, 32), (232, 162, 0), (217, 72, 15), (231, 236, 225)


def hexagon(cx, cy, r, rot=30):
    return [(cx + r * math.cos(math.radians(rot + 60 * i)), cy + r * math.sin(math.radians(rot + 60 * i))) for i in range(6)]


def draw(size, maskable=False, mono=False):
    S = 4  # Supersampling
    N = size * S
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if not mono:
        if maskable:
            d.rectangle([0, 0, N, N], fill=BG)
        else:
            d.rounded_rectangle([0, 0, N - 1, N - 1], radius=int(N * 0.22), fill=BG)
    k = 0.30 if maskable else 0.36
    c = N / 2
    fg = (255, 255, 255, 255) if mono else AMBER
    d.polygon(hexagon(c, c, N * k * 1.18), fill=fg)
    d.polygon(hexagon(c, c, N * k * 0.98), fill=(0, 0, 0, 0) if mono else BG)
    d.polygon(hexagon(c, c, N * k * 0.62), fill=(255, 255, 255, 255) if mono else ORANGE)
    return im.resize((size, size), Image.LANCZOS)


draw(192).save(OUT / "icon-192.png")
draw(512).save(OUT / "icon-512.png")
draw(512, maskable=True).save(OUT / "icon-maskable-512.png")
draw(180, maskable=True).convert("RGB").save(OUT / "apple-touch-icon.png")
draw(96, mono=True).save(OUT / "badge-96.png")
(OUT / "favicon.svg").write_text(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#1B2620"/>'
    '<polygon points="49.9,32 40.9,47.6 23.1,47.6 14.1,32 23.1,16.4 40.9,16.4" fill="#E8A200"/>'
    '<polygon points="46.4,32 38.7,45.4 25.3,45.4 17.6,32 25.3,18.6 38.7,18.6" fill="#1B2620"/>'
    '<polygon points="39.5,32 35.8,38.5 28.2,38.5 24.5,32 28.2,25.5 35.8,25.5" fill="#D9480F"/></svg>', encoding="utf-8")
print("icons ok", sorted(p.name for p in OUT.iterdir()))