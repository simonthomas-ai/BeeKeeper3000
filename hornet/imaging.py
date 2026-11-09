"""Bildhilfen (nur Pillow): Erkennungsrahmen einzeichnen, Ausschnitt schneiden, JPEG erzeugen."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from .detector import Detection

DISPLAY = {
    "vvel": "Asiatische Hornisse",
    "vcra": "Europäische Hornisse",
    "amel": "Honigbiene",
    "vespsp": "Wespe",
    "vzon": "Klasse vzon",
}
LATIN = {
    "vvel": "Vespa velutina",
    "vcra": "Vespa crabro",
    "amel": "Apis mellifera",
}

COL_ALERT = (217, 72, 15)
COL_PROTECTED = (46, 125, 50)
COL_BEE = (242, 169, 0)
COL_OTHER = (120, 130, 125)


def display_name(cls_name: str) -> str:
    return DISPLAY.get(cls_name, cls_name)


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # sehr alte Pillow-Version
        return ImageFont.load_default()


def draw_detections(img: Image.Image, dets: list[Detection], alert: set[str], protected: set[str]) -> Image.Image:
    out = img.convert("RGB").copy()
    if not dets:
        return out
    d = ImageDraw.Draw(out)
    fs = max(12, out.width // 60)
    font = _font(fs)
    lw = max(2, out.width // 320)
    for det in dets:
        col = COL_ALERT if det.name in alert else COL_PROTECTED if det.name in protected \
            else COL_BEE if det.name == "amel" else COL_OTHER
        x1, y1, x2, y2 = det.box
        d.rectangle([x1, y1, x2, y2], outline=col, width=lw)
        label = f"{display_name(det.name)} {int(det.conf * 100)}%"
        try:
            tb = d.textbbox((0, 0), label, font=font)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
        except Exception:
            tw, th = len(label) * fs // 2, fs
        ty = y1 - th - 8 if y1 - th - 8 > 0 else y1 + 2
        d.rectangle([x1, ty, x1 + tw + 10, ty + th + 8], fill=col)
        d.text((x1 + 5, ty + 2), label, fill=(255, 255, 255), font=font)
    return out


def to_jpeg(img: Image.Image, quality: int = 85, max_w: int | None = None) -> bytes:
    im = img.convert("RGB")
    if max_w and im.width > max_w:
        im = im.resize((max_w, max(1, round(im.height * max_w / im.width))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def crop_around(img: Image.Image, box: tuple[float, float, float, float], pad: float = 0.6,
                min_side: int = 220, max_side: int = 768) -> Image.Image:
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    side = max(w, h) * (1 + 2 * pad)
    side = max(side, min_side)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    l, t = max(0, int(cx - side / 2)), max(0, int(cy - side / 2))
    r, b = min(img.width, int(cx + side / 2)), min(img.height, int(cy + side / 2))
    crop = img.crop((l, t, r, b))
    if max(crop.size) > max_side:
        k = max_side / max(crop.size)
        crop = crop.resize((max(1, int(crop.width * k)), max(1, int(crop.height * k))), Image.LANCZOS)
    elif max(crop.size) < 320:  # kleine Ausschnitte vergrößern (bessere Lesbarkeit für die Prüfung)
        k = 320 / max(crop.size)
        crop = crop.resize((int(crop.width * k), int(crop.height * k)), Image.LANCZOS)
    return crop
