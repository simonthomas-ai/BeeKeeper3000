#!/usr/bin/env python3
"""Browser-Prüfung der gebauten Website (Playwright + Chromium).

Prüft für jede Seite bei Handy-, Tablet- und Desktop-Breite, hell und dunkel:
  * kein waagerechtes Scrollen,
  * es werden ausschließlich Dateien vom eigenen Server geladen (keine Fremdanfragen),
  * kein Cookie wird gesetzt, kein Skript läuft, keine Konsolenfehler,
  * die Seite ist mit der Tastatur bedienbar (erster Tabulator-Halt ist „Zum Inhalt springen“, Fokus sichtbar),
  * die Schrift ist lesbar groß (Fließtext ≥ 16 px).
Optional: --bilder ORDNER legt Bildschirmfotos ab.

Aufruf:  python tests/browser_check.py <Ordner der gebauten Seite> [--bilder ORDNER]
Playwright: pip install playwright && playwright install chromium   (nur für diese Prüfung nötig)
"""
from __future__ import annotations

import argparse
import functools
import http.server
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

GROESSEN = {"handy": (360, 740), "tablet": (768, 1024), "desktop": (1280, 900)}


class Still(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ordner")
    ap.add_argument("--bilder", default="")
    a = ap.parse_args()
    root = Path(a.ordner).resolve()
    handler = functools.partial(Still, directory=str(root))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    seiten = sorted(p.name for p in root.glob("*.html") if p.name != "404.html")
    fehler: list[str] = []
    pruefungen = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for farbe in ("light", "dark"):
            for gname, (w, h) in GROESSEN.items():
                ctx = browser.new_context(viewport={"width": w, "height": h}, color_scheme=farbe, java_script_enabled=True)
                page = ctx.new_page()
                anfragen: list[str] = []
                konsole: list[str] = []
                page.on("request", lambda r: anfragen.append(r.url))
                page.on("console", lambda m: konsole.append(m.text) if m.type in ("error", "warning") else None)
                page.on("pageerror", lambda e: konsole.append(str(e)))
                for name in seiten:
                    anfragen.clear()
                    konsole.clear()
                    page.goto(f"{base}/{name}")
                    page.wait_for_load_state("networkidle")
                    tag = f"{name} [{gname}/{farbe}]"
                    breite = page.evaluate("document.documentElement.scrollWidth")
                    pruefungen += 1
                    if breite > w + 1:
                        fehler.append(f"{tag}: waagerechtes Scrollen ({breite} > {w})")
                    fremd = [u for u in anfragen if not u.startswith(base)]
                    pruefungen += 1
                    if fremd:
                        fehler.append(f"{tag}: Fremdanfragen {fremd[:3]}")
                    pruefungen += 1
                    if konsole:
                        fehler.append(f"{tag}: Konsole {konsole[:2]}")
                    pruefungen += 1
                    if ctx.cookies():
                        fehler.append(f"{tag}: Cookie gesetzt {ctx.cookies()}")
                    schrift = page.evaluate("parseFloat(getComputedStyle(document.querySelector('main p')).fontSize)")
                    pruefungen += 1
                    if schrift < 16:
                        fehler.append(f"{tag}: Fließtext zu klein ({schrift}px)")
                    if gname == "handy" and farbe == "light":
                        page.keyboard.press("Tab")
                        erst = page.evaluate("document.activeElement.className + '|' + document.activeElement.textContent.trim()")
                        pruefungen += 1
                        if not erst.startswith("sprung|Zum Inhalt"):
                            fehler.append(f"{tag}: erster Tabulator-Halt ist nicht „Zum Inhalt springen“ ({erst})")
                        umriss = page.evaluate("getComputedStyle(document.activeElement).outlineStyle + ' ' + getComputedStyle(document.activeElement).outlineWidth")
                        pruefungen += 1
                        if umriss.startswith("none"):
                            fehler.append(f"{tag}: Fokus nicht sichtbar")
                    if a.bilder and name in ("index.html", "download.html", "impressum.html", "hinweise.html", "haftung.html"):
                        Path(a.bilder).mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(Path(a.bilder) / f"{name[:-5]}-{gname}-{farbe}.png"), full_page=True)
                ctx.close()
        # Skripte dürfen nicht laufen: Inhaltsrichtlinie blockiert sie; wir prüfen, dass wirklich keine <script> existieren
        ctx = browser.new_context()
        page = ctx.new_page()
        for name in seiten:
            page.goto(f"{base}/{name}")
            pruefungen += 1
            if page.evaluate("document.scripts.length") != 0:
                fehler.append(f"{name}: enthält Skripte")
        browser.close()
    srv.shutdown()
    print(f"{pruefungen} Prüfungen, {len(fehler)} Fehler")
    for f in fehler:
        print(" ·", f)
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
