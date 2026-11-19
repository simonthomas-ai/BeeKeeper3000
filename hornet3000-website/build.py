#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Baukasten der Hornet3000-Website (nur Python-Standardbibliothek, ab Python 3.9).

Was dieses Skript tut
  * liest config.json (Angaben des Betreibers) und site/ (Seiten, Gestaltung, Daten der Downloads),
  * setzt die Seiten zu einer rein statischen Website zusammen (kein JavaScript, keine Cookies, keine Fremdressourcen),
  * berechnet Größen und SHA-256-Prüfsummen der Download-Dateien aus den ECHTEN Dateien und gleicht sie mit SHA256SUMS ab,
  * prüft das Ergebnis streng und bricht ab, wenn etwas nicht stimmt.

Zwei Betriebsarten
  python build.py             VERÖFFENTLICHUNG: bricht ab, solange Pflichtangaben (Impressum, Datenschutz, Hoster …) fehlen,
                              nach Platzhaltern aussehen oder zueinander nicht passen. Ausgabe: public/
  python build.py --vorschau  VORSCHAU zum Ansehen: fehlende Angaben werden rot markiert, auf jeder Seite steht
                              „VORSCHAU – nicht veröffentlichen“. Ausgabe: vorschau/
  python build.py --felder    zeigt alle Felder der config.json mit Hinweis.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
VERSION_BAUKASTEN = "1.0.0"

# ---------------------------------------------------------------------------------------------------------------------
# 1. Felder der config.json
# ---------------------------------------------------------------------------------------------------------------------
HILFE = {
    "betreiber.initiative": "Anzeigename der Initiative (steht in Kopfzeile und Fuß), z. B. „Bienenschutz Musterland“",
    "betreiber.rechtsform": "z. B. „Privatperson“, „eingetragener Verein (e. V.)“, „GbR“, „gGmbH“",
    "betreiber.name": "Vollständiger Name der Organisation (so wie im Register bzw. im Freistellungsbescheid) oder der verantwortlichen Person",
    "betreiber.vertretungsberechtigt": "Pflicht bei Vereinen/Gesellschaften (§ 5 DDG): Name einer vertretungsberechtigten Person, z. B. „Vorstand: …“. Es genügt eine Person, und sie muss nicht diejenige sein, die die Software betreut",
    "betreiber.strasse": "Straße und Hausnummer der Organisation (ladungsfähige Anschrift, z. B. Vereinssitz oder Geschäftsstelle – ein Postfach genügt nicht)",
    "betreiber.plz": "Postleitzahl",
    "betreiber.ort": "Ort",
    "betreiber.land": "Land, z. B. Deutschland",
    "betreiber.email": "E-Mail-Adresse, die Sie regelmäßig lesen. Sie steht öffentlich im Impressum: eine eigene, neutrale Adresse der Organisation nehmen, keine private mit Klarnamen",
    "betreiber.email_anbieter": "Nur wenn das Postfach bei einem externen Anbieter liegt (z. B. „Google Ireland Limited (Gmail)“): wird in der Datenschutzerklärung genannt. Sonst leer lassen",
    "betreiber.telefon": "Telefonnummer (empfohlen). Wenn leer: unter kontakt_alternative einen zweiten, schnellen Kontaktweg nennen",
    "betreiber.kontakt_alternative": "Zweiter Kontaktweg, falls keine Telefonnummer angegeben wird (z. B. „Kontaktformular unter …“)",
    "betreiber.register": "Nur wenn eingetragen: Registergericht, z. B. „Amtsgericht Köln – Vereinsregister“",
    "betreiber.registernummer": "Nur wenn eingetragen: Registernummer, z. B. „VR 12345“",
    "betreiber.ust_id": "Nur wenn vorhanden: Umsatzsteuer-Identifikationsnummer",
    "betreiber.gemeinnuetzig_anerkannt": "true NUR bei gültigem Freistellungs-/Feststellungsbescheid des Finanzamts, sonst false",
    "betreiber.gemeinnuetzig_nachweis": "Wenn true: Finanzamt und Datum des Bescheids, z. B. „Freistellungsbescheid des Finanzamts … vom 01.02.2026“",
    "website.adresse": "Adresse der Website mit https://, z. B. https://ihre-domain.de (die echte Adresse, unter der die Seite erreichbar ist)",
    "website.hoster_name": "Name des Hosters (Anbieter des Servers/Webspace)",
    "website.hoster_anschrift": "Anschrift des Hosters (Straße, PLZ Ort)",
    "website.hoster_land": "Land, in dem der Server steht; bei Auslieferung über ein weltweites Netz (Content-Delivery-Netz) z. B. „weltweit verteilt, Verwaltung in Irland“ – so, wie es der Hoster angibt",
    "website.avv_abgeschlossen": "true, wenn ein Auftragsverarbeitungsvertrag (Art. 28 DSGVO) mit dem Hoster besteht (muss true sein)",
    "website.protokolle": "Wer führt die Server-Protokolle? „selbst“ = Sie (eigener Server; dann logfiles_tage und ip_kuerzen angeben). „hoster“ = der Hoster nach eigenen Regeln, ohne dass Sie einzelne Einträge sehen oder speichern (z. B. Firebase Hosting ohne verbundenes Cloud Logging)",
    "website.logfiles_tage": "Nur bei protokolle = selbst: wie viele Tage Server-Protokolle aufbewahrt werden (Zahl, 0–365); muss zur Servereinstellung passen. Sonst null",
    "website.ip_kuerzen": "Nur bei protokolle = selbst: true, wenn der Server IP-Adressen im Zugriffsprotokoll vor dem Speichern kürzt (Beispiel: server/nginx.conf.beispiel); sonst false. Bei „hoster“: null",
    "website.hoster_datenschutz_url": "https-Adresse der Datenschutzinformationen des Hosters (Pflicht bei protokolle = hoster; bei Google/Firebase z. B. die Seite „Privacy and Security in Firebase“)",
    "website.hoster_drittland": "true, wenn der Hoster Daten auch außerhalb des Europäischen Wirtschaftsraums verarbeiten kann (bei Google/Firebase: true), sonst false",
    "website.hoster_drittland_grundlage": "Nur wenn hoster_drittland = true: Grundlage der Übermittlung, z. B. „Angemessenheitsbeschluss der EU-Kommission (EU-US Data Privacy Framework, Google ist zertifiziert) und Standardvertragsklauseln“. Sonst leer",
    "downloads.quelle_ordner": "Ordner mit den Release-Dateien und SHA256SUMS-<Version>.txt (wird auf Vollständigkeit und Prüfsummen geprüft)",
    "downloads.basis_url": "„downloads/“ = Dateien liegen auf demselben Server; oder https://… eines anderen Anbieters",
    "downloads.anbieter.name": "Nur bei externem Download-Anbieter: Name",
    "downloads.anbieter.anschrift": "Nur bei externem Download-Anbieter: Anschrift",
    "downloads.anbieter.datenschutz_url": "Nur bei externem Download-Anbieter: https-Adresse von dessen Datenschutzerklärung",
    "software.version": "Version der Software, z. B. 1.3.0",
    "software.stand": "Datum der Veröffentlichung (JJJJ-MM-TT)",
    "software.apk_zertifikat_sha256": "SHA-256-Fingerabdruck des Zertifikats der Android-App (64 Hexzeichen, siehe LIES-MICH der Version)",
    "lizenz.eigener_code": "Lizenz für den eigenen Programmcode, z. B. GPL-3.0-or-later (Entscheidung des Rechteinhabers!)",
    "lizenz.text_url": "https-Adresse des Lizenztextes, z. B. https://www.gnu.org/licenses/gpl-3.0.html",
    "ki.system": "Name des KI-Systems, das die Software erstellt hat",
    "ki.anbieter": "Anbieter des KI-Systems",
    "ki.modelle": "Welche Modelle (z. B. „u. a. Claude Sonnet 5.5“)",
    "aufsicht.name": "Zuständige Datenschutz-Aufsichtsbehörde (nach Sitz des Betreibers)",
    "aufsicht.anschrift": "Anschrift der Aufsichtsbehörde",
    "aufsicht.telefon": "Telefon der Aufsichtsbehörde",
    "aufsicht.web": "https-Adresse der Aufsichtsbehörde",
    "seite.stand": "Stand der rechtlichen Texte (JJJJ-MM-TT)",
}

# Werte, die nach nicht ausgefülltem Platzhalter aussehen
PLATZHALTER = re.compile(r"(?i)(\btodo\b|\bxxx+\b|bitte ausf|musterstr|mustermann|musterfrau|\bplatzhalter\b|\blorem\b|\.{3}|…|"
                         r"\bexample\.(com|org|net)\b|\bbeispiel(stra|firma|name)|<[^>]+>)")
EMAIL = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]{2,}$")
JURISTISCH = re.compile(r"(?i)(e\.\s?v\.|eingetragener verein|gmbh|\bug\b|\bag\b|gbr|stiftung|genossenschaft|\bohg\b|\bkg\b)")
PROTOKOLL_MODI = ("selbst", "hoster")
REGISTERPFLICHT = re.compile(r"(?i)(e\.\s?v\.|eingetragener verein|gmbh|\bug\b|\bag\b|genossenschaft|\bohg\b|\bkg\b)")


class BauFehler(Exception):
    pass


def lookup(ctx: dict, pfad: str):
    cur = ctx
    for teil in pfad.split("."):
        if isinstance(cur, dict) and teil in cur:
            cur = cur[teil]
        else:
            return None
    return cur


def vorhanden(v) -> bool:
    return v is not None and v != "" and not isinstance(v, bool)


def pruefe_config(cfg: dict, modus_release: bool) -> list[str]:
    """Gibt eine Liste verständlicher Fehler zurück (leer = in Ordnung)."""
    f: list[str] = []

    def text(pfad: str, pflicht: bool = True):
        v = lookup(cfg, pfad)
        if not isinstance(v, str) or not v.strip():
            if pflicht:
                f.append(f"{pfad}: fehlt – {HILFE.get(pfad, '')}")
            return None
        if PLATZHALTER.search(v):
            f.append(f"{pfad}: sieht nach Platzhalter aus („{v}“) – bitte den echten Wert eintragen")
        if v != v.strip() or "\n" in v:
            f.append(f"{pfad}: darf keine Zeilenumbrüche oder überzähligen Leerzeichen enthalten")
        return v.strip()

    def boolean(pfad: str):
        v = lookup(cfg, pfad)
        if not isinstance(v, bool):
            f.append(f"{pfad}: muss true oder false sein – {HILFE.get(pfad, '')}")
        return v

    def https(pfad: str, pflicht: bool = True):
        v = text(pfad, pflicht)
        if v and not re.match(r"^https://[^\s/]+\.[^\s/]+", v):
            f.append(f"{pfad}: muss mit https:// beginnen und eine echte Adresse enthalten („{v}“)")
        return v

    b = "betreiber."
    text(b + "initiative")
    rf = text(b + "rechtsform")
    text(b + "name")
    text(b + "strasse")
    plz = text(b + "plz")
    text(b + "ort")
    land = text(b + "land")
    if plz and land and land.lower() == "deutschland" and not re.fullmatch(r"\d{5}", plz):
        f.append(f"{b}plz: deutsche Postleitzahl hat 5 Ziffern („{plz}“)")
    mail = text(b + "email")
    if mail and not EMAIL.match(mail):
        f.append(f"{b}email: keine gültige E-Mail-Adresse („{mail}“)")
    tel = text(b + "telefon", pflicht=False)
    alt = text(b + "kontakt_alternative", pflicht=False)
    if tel and not re.fullmatch(r"[+()\d\s/.-]{6,}", tel):
        f.append(f"{b}telefon: sieht nicht wie eine Telefonnummer aus („{tel}“)")
    if not tel and not alt:
        f.append(f"{b}telefon / {b}kontakt_alternative: mindestens ein zweiter, schneller Kontaktweg neben der E-Mail ist "
                 "erforderlich (§ 5 DDG)")
    if rf and JURISTISCH.search(rf):
        text(b + "vertretungsberechtigt")
    if rf and REGISTERPFLICHT.search(rf):
        text(b + "register")
        text(b + "registernummer")
    if lookup(cfg, b + "register") and not lookup(cfg, b + "registernummer"):
        f.append(f"{b}registernummer: fehlt (Register ist angegeben)")
    text(b + "ust_id", pflicht=False)
    if boolean(b + "gemeinnuetzig_anerkannt") is True:
        text(b + "gemeinnuetzig_nachweis")

    w = "website."
    adr = https(w + "adresse")
    text(w + "hoster_name")
    text(w + "hoster_anschrift")
    text(w + "hoster_land")
    if boolean(w + "avv_abgeschlossen") is not True:
        f.append(f"{w}avv_abgeschlossen: muss true sein – ohne Auftragsverarbeitungsvertrag mit dem Hoster (Art. 28 DSGVO) "
                 "darf die Seite nicht mit diesen Angaben veröffentlicht werden")
    modus = text(w + "protokolle")
    if modus and modus not in PROTOKOLL_MODI:
        f.append(f"{w}protokolle: nur „selbst“ oder „hoster“ erlaubt („{modus}“) – {HILFE[w + 'protokolle']}")
    if modus == "selbst":
        tage = lookup(cfg, w + "logfiles_tage")
        if isinstance(tage, bool) or not isinstance(tage, int) or not 0 <= tage <= 365:
            f.append(f"{w}logfiles_tage: ganze Zahl von 0 bis 365 – {HILFE[w + 'logfiles_tage']}")
        boolean(w + "ip_kuerzen")
        https(w + "hoster_datenschutz_url", pflicht=False)
    elif modus == "hoster":
        https(w + "hoster_datenschutz_url")
        for feld in ("logfiles_tage", "ip_kuerzen"):
            if lookup(cfg, w + feld) not in (None, ""):
                f.append(f"{w}{feld}: bei protokolle = hoster auf null setzen, denn der Hoster bestimmt die Aufbewahrung")
    if boolean(w + "hoster_drittland") is True:
        text(w + "hoster_drittland_grundlage")
    elif lookup(cfg, w + "hoster_drittland_grundlage"):
        f.append(f"{w}hoster_drittland_grundlage: nur ausfüllen, wenn hoster_drittland = true ist")
    text(b + "email_anbieter", pflicht=False)

    d = "downloads."
    basis = text(d + "basis_url")
    if basis:
        extern = basis.startswith(("http://", "https://"))
        if extern and not basis.startswith("https://"):
            f.append(f"{d}basis_url: externe Adresse muss mit https:// beginnen")
        if not extern and (basis.startswith("/") or ".." in basis or not basis.endswith("/")):
            f.append(f"{d}basis_url: relativer Ordner muss mit / enden und darf nicht mit / beginnen oder „..“ enthalten")
        if extern:
            text(d + "anbieter.name")
            text(d + "anbieter.anschrift")
            https(d + "anbieter.datenschutz_url")
    q = text(d + "quelle_ordner", pflicht=modus_release)
    if q and modus_release:
        qp = Path(q).expanduser()
        if not qp.is_dir():
            f.append(f"{d}quelle_ordner: Ordner nicht gefunden („{q}“)")

    s = "software."
    ver = text(s + "version")
    if ver and not re.fullmatch(r"\d+\.\d+\.\d+", ver):
        f.append(f"{s}version: Format 1.2.3 („{ver}“)")
    fp = text(s + "apk_zertifikat_sha256")
    if fp and not re.fullmatch(r"[0-9a-f]{64}", fp):
        f.append(f"{s}apk_zertifikat_sha256: 64 Hexzeichen (Kleinbuchstaben) erwartet")
    for datum in (s + "stand", "seite.stand"):
        v = text(datum)
        if v:
            try:
                date.fromisoformat(v)
            except ValueError:
                f.append(f"{datum}: Datum im Format JJJJ-MM-TT („{v}“)")

    text("lizenz.eigener_code")
    https("lizenz.text_url")
    for k in ("system", "anbieter", "modelle"):
        text("ki." + k)
    for k in ("name", "anschrift", "telefon"):
        text("aufsicht." + k)
    https("aufsicht.web")
    return f


# ---------------------------------------------------------------------------------------------------------------------
# 2. Mini-Vorlagensprache  ({{ pfad }}  {{= roh }}  {% if pfad %}…{% else %}…{% endif %}  {% include datei %})
# ---------------------------------------------------------------------------------------------------------------------
TOKEN = re.compile(r"(\{%.*?%\}|\{\{.*?\}\})", re.S)


def parse(tokens: list[str], i: int = 0, stop: tuple = ()):
    nodes = []
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("{%"):
            cmd = t[2:-2].strip()
            wort = cmd.split()[0] if cmd else ""
            if wort in stop:
                return nodes, i
            if wort == "if":
                cond = cmd[2:].strip()
                neg = False
                if cond.startswith("not "):
                    neg, cond = True, cond[4:].strip()
                then, i = parse(tokens, i + 1, ("else", "endif"))
                els: list = []
                if i < len(tokens) and tokens[i][2:-2].strip() == "else":
                    els, i = parse(tokens, i + 1, ("endif",))
                nodes.append(("if", cond, neg, then, els))
            elif wort == "include":
                nodes.append(("include", cmd[7:].strip()))
            else:
                raise BauFehler(f"Unbekannte Vorlagenanweisung: {t}")
        elif t.startswith("{{"):
            inner = t[2:-2].strip()
            raw = inner.startswith("=")
            nodes.append(("var", inner[1:].strip() if raw else inner, raw))
        elif t:
            nodes.append(("text", t))
        i += 1
    if stop:
        raise BauFehler("Vorlage: {% endif %} fehlt")
    return nodes, i


def render(nodes: list, ctx: dict, fehler: list[str], vorschau: bool, teile: dict, quelle: str) -> str:
    out: list[str] = []
    endet_punkt = False        # letzter eingesetzter Wert endete auf „.“ (z. B. „e. V.“): kein doppelter Satzpunkt
    for n in nodes:
        if n[0] == "text":
            t = n[1]
            if endet_punkt and t.startswith(".") and not t.startswith(".."):
                t = t[1:]
            endet_punkt = False
            out.append(t)
            continue
        endet_punkt = False
        if n[0] == "var":
            v = lookup(ctx, n[1])
            if not vorhanden(v):
                if vorschau:
                    if re.search(r'=\s*"[^"]*$', "".join(out)[-400:]):      # innerhalb eines Attributs: kein Markup
                        out.append(f"FEHLT-{html.escape(n[1])}")
                    else:
                        out.append(f'<mark class="fehlt">[{html.escape(n[1])} fehlt]</mark>')
                else:
                    fehler.append(f"{quelle}: Wert „{n[1]}“ ist leer")
            else:
                out.append(str(v) if n[2] else html.escape(str(v)))
                endet_punkt = str(v).endswith(".") and not str(v).endswith("..")
        elif n[0] == "if":
            v = lookup(ctx, n[1])
            wahr = bool(v) and v is not None
            if n[2]:
                wahr = not wahr
            out.append(render(n[3] if wahr else n[4], ctx, fehler, vorschau, teile, quelle))
        elif n[0] == "include":
            if n[1] not in teile:
                raise BauFehler(f"{quelle}: Teil „{n[1]}“ nicht gefunden")
            out.append(render(teile[n[1]], ctx, fehler, vorschau, teile, quelle + f" → {n[1]}"))
    return "".join(out)


# ---------------------------------------------------------------------------------------------------------------------
# 3. Downloads
# ---------------------------------------------------------------------------------------------------------------------
def groesse_text(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".replace(".", ",") + " MB"
    return f"{max(1, round(n / 1000))} KB"


def sha256_datei(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def lese_summen(p: Path) -> dict[str, str]:
    res = {}
    for zeile in p.read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"([0-9a-f]{64})\s+\*?(.+)", zeile.strip())
        if m:
            res[m.group(2).strip()] = m.group(1)
    return res


def baue_downloads(cfg: dict, vorschau: bool, fehler: list[str]) -> tuple[str, list[tuple[Path, str]], dict]:
    """HTML-Block je Gruppe, Liste (Quelldatei, Name) zum Kopieren und Prüfinformation."""
    daten = json.loads((SITE / "daten" / "downloads.json").read_text(encoding="utf-8"))
    ver = cfg["software"]["version"]
    basis = cfg["downloads"]["basis_url"]
    extern = basis.startswith("https://")
    q = cfg["downloads"].get("quelle_ordner", "")
    qdir = Path(q).expanduser() if q else None
    summen: dict[str, str] = {}
    if qdir and qdir.is_dir():
        sp = qdir / f"SHA256SUMS-{ver}.txt"
        if sp.is_file():
            summen = lese_summen(sp)
        elif not vorschau:
            fehler.append(f"downloads.quelle_ordner: SHA256SUMS-{ver}.txt nicht gefunden")
    elif not vorschau:
        fehler.append("downloads.quelle_ordner: Ordner nicht gefunden")

    gruppen: dict[str, list[str]] = {g["id"]: [] for g in daten["gruppen"]}
    kopieren: list[tuple[Path, str]] = []
    info: dict[str, dict] = {}
    for e in daten["dateien"]:
        name = e["name"].replace("{v}", ver)
        quelle = (qdir / name) if qdir else None
        groesse = sha = None
        if quelle and quelle.is_file():
            groesse = quelle.stat().st_size
            sha = sha256_datei(quelle)
            soll = summen.get(name)
            if soll is None:
                if e.get("ohne_summe"):
                    pass
                elif not (vorschau and not summen):
                    fehler.append(f"{name}: steht nicht in SHA256SUMS-{ver}.txt")
            elif soll != sha:
                fehler.append(f"{name}: Prüfsumme der Datei ({sha[:12]}…) weicht von SHA256SUMS ({soll[:12]}…) ab")
            kopieren.append((quelle, name))
        else:
            if not e.get("optional") and not vorschau:
                fehler.append(f"Download-Datei fehlt: {name}")
        info[name] = {"groesse": groesse, "sha256": sha, "gruppe": e["gruppe"]}
        e_h = html.escape
        href = html.escape(basis + name)
        rel = ' rel="noopener noreferrer"' if extern else ""
        meta = [f'<div><dt>Datei</dt><dd><code>{e_h(name)}</code></dd></div>']
        if groesse is not None:
            meta.append(f"<div><dt>Größe</dt><dd>{groesse_text(groesse)}</dd></div>")
            meta.append(f'<div><dt>SHA-256</dt><dd><code class="hash">{sha}</code></dd></div>')
        else:
            meta.append('<div><dt>Größe / SHA-256</dt><dd><mark class="fehlt">[Datei nicht gefunden]</mark></dd></div>')
        stufe = e.get("pruefung", {})
        stufe_html = ""
        if stufe:
            label = {"getestet": "Getestet", "gebaut": "Gebaut, nicht auf echter Hardware ausgeführt",
                     "teils": "Teilweise getestet"}[stufe["stufe"]]
            stufe_html = (f'<p class="stufe stufe-{e_h(stufe["stufe"])}"><span class="marke">{e_h(label)}</span> '
                          f'{e_h(stufe["text"])}</p>')
        knopf = ""
        if groesse is not None:
            knopf = f'<p><a class="knopf" href="{href}" download{rel}>Herunterladen</a></p>'
        gruppen[e["gruppe"]].append(
            f'<article class="datei" id="d-{e_h(e["id"])}">\n<h3>{e_h(e["titel"])}</h3>\n<p>{e_h(e["text"])}</p>\n'
            f'{stufe_html}\n<dl class="meta">{"".join(meta)}</dl>\n{knopf}\n</article>')
    teile = []
    for g in daten["gruppen"]:
        if gruppen[g["id"]]:
            teile.append(f'<section class="gruppe" aria-labelledby="g-{g["id"]}">\n<h2 id="g-{g["id"]}">{html.escape(g["titel"])}</h2>\n'
                         f'<p class="einleitung">{html.escape(g["text"])}</p>\n' + "\n".join(gruppen[g["id"]]) + "\n</section>")
    return "\n".join(teile), kopieren, info


# ---------------------------------------------------------------------------------------------------------------------
# 4. Prüfung der fertigen Seiten
# ---------------------------------------------------------------------------------------------------------------------
class Seite(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.ids: list[str] = []
        self.links: list[tuple[str, str, dict]] = []   # (tag, url, attrs)
        self.res: list[tuple[str, str]] = []           # geladene Ressourcen (tag, url)
        self.headings: list[int] = []
        self.imgs_ohne_alt = 0
        self.verboten: list[str] = []
        self.attr_verstoss: list[str] = []
        self.text: list[str] = []
        self.title = ""
        self._in_title = False
        self.lang = ""
        self.meta: dict[str, str] = {}
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        self.tags.append(tag)
        if tag == "html":
            self.lang = a.get("lang", "")
        if tag == "title":
            self._in_title = True
        if "id" in a:
            self.ids.append(a["id"])
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))
        if tag in ("script", "iframe", "form", "object", "embed", "style", "frame", "applet", "base", "input", "button",
                   "textarea", "select"):
            self.verboten.append(tag)
        for k in a:
            if k.startswith("on") or k == "style" or k == "srcset":
                self.attr_verstoss.append(f"{tag}[{k}]")
        if tag == "meta" and "name" in a:
            self.meta[a["name"]] = a.get("content", "")
        if tag == "meta" and a.get("http-equiv", "").lower() == "content-security-policy":
            self.meta["csp"] = a.get("content", "")
        if tag == "a" and "href" in a:
            self.links.append(("a", a["href"], a))
        if tag == "link":
            rel = a.get("rel", "").lower()
            if "href" in a and rel not in ("canonical",):
                self.res.append(("link:" + rel, a["href"]))
            if rel == "canonical":
                self.links.append(("canonical", a.get("href", ""), a))
        if tag in ("img", "source", "audio", "video", "track") and "src" in a:
            self.res.append((tag, a["src"]))
        if tag == "img" and "alt" not in a:
            self.imgs_ohne_alt += 1
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if not self._skip:
            self.text.append(data)


ABSOLUT = re.compile(r"(?i)(jegliche haftung (ist )?ausgeschlossen|haften unter keinen umständen|keinerlei haftung|"
                     r"jede haftung (ist )?ausgeschlossen|haftung (ist )?(vollständig|gänzlich|komplett) ausgeschlossen)")


def analysiere(p: Path) -> Seite:
    s = Seite()
    s.feed(p.read_text(encoding="utf-8"))
    return s


def pruefe_ausgabe(out: Path, cfg: dict, vorschau: bool, erlaubte_hosts: set[str]) -> list[str]:
    f: list[str] = []
    seiten = sorted(out.glob("*.html"))
    if not seiten:
        return ["Keine Seiten erzeugt"]
    analysen = {p.name: analysiere(p) for p in seiten}
    for name, s in analysen.items():
        t = lambda m: f"{name}: {m}"  # noqa: E731
        raw = (out / name).read_text(encoding="utf-8")
        if "{{" in raw or "{%" in raw:
            f.append(t("nicht aufgelöste Vorlagenanweisung"))
        if s.lang != "de":
            f.append(t('<html lang="de"> fehlt'))
        if not s.title.strip():
            f.append(t("<title> fehlt"))
        if "viewport" not in s.meta:
            f.append(t("Viewport-Angabe fehlt"))
        if "csp" not in s.meta or "default-src 'none'" not in s.meta["csp"]:
            f.append(t("Inhaltsrichtlinie (CSP) fehlt oder ist nicht streng"))
        if s.meta.get("referrer") != "no-referrer":
            f.append(t('meta referrer "no-referrer" fehlt'))
        if s.headings.count(1) != 1:
            f.append(t(f"genau eine Überschrift 1. Ordnung nötig (gefunden: {s.headings.count(1)})"))
        prev = 0
        for h in s.headings:
            if prev and h > prev + 1:
                f.append(t(f"Überschriftenebene springt von {prev} auf {h}"))
            prev = h
        if s.imgs_ohne_alt:
            f.append(t(f"{s.imgs_ohne_alt} Bild(er) ohne alt-Text"))
        if s.verboten:
            f.append(t(f"nicht erlaubte Elemente: {sorted(set(s.verboten))}"))
        if s.attr_verstoss:
            f.append(t(f"nicht erlaubte Attribute (Inline-Stil/Ereignis): {sorted(set(s.attr_verstoss))[:5]}"))
        dup = {i for i in s.ids if s.ids.count(i) > 1}
        if dup:
            f.append(t(f"doppelte ids: {sorted(dup)}"))
        for tag, url in s.res:
            if re.match(r"(?i)^(https?:)?//", url) or ":" in url.split("/")[0]:
                f.append(t(f"lädt eine Fremdressource ({tag}: {url})"))
            else:
                if not (out / url.lstrip("/").split("#")[0].split("?")[0]).is_file():
                    f.append(t(f"Ressource fehlt: {url}"))
        for tag, url, a in s.links:
            if tag == "canonical":
                continue
            if url.startswith("FEHLT-"):
                if not vorschau:
                    f.append(t(f"Link mit fehlender Angabe: {url}"))
                continue
            if url.startswith(("http://", "https://")):
                host = urlparse(url).hostname or ""
                if url.startswith("http://"):
                    f.append(t(f"Link ohne https: {url}"))
                if host not in erlaubte_hosts:
                    f.append(t(f"Link auf nicht freigegebenen Host {host} ({url})"))
                if "noopener" not in a.get("rel", "") or "noreferrer" not in a.get("rel", ""):
                    f.append(t(f'externer Link ohne rel="noopener noreferrer": {url}'))
            elif url.startswith("mailto:"):
                pass
            elif ":" in url.split("/")[0]:
                f.append(t(f"unerwartetes Link-Schema: {url}"))
            else:
                ziel, _, frag = url.lstrip("/").partition("#")
                zname = ziel or name
                if zname.startswith("downloads/"):
                    continue          # Dateien werden ggf. erst beim Kopieren bereitgestellt (eigener Test)
                if zname not in analysen:
                    f.append(t(f"interner Link ins Leere: {url}"))
                elif frag and frag not in analysen[zname].ids:
                    f.append(t(f"Sprungmarke fehlt: {url}"))
        text = " ".join(s.text)
        if ABSOLUT.search(text):
            f.append(t("absoluter Haftungsausschluss formuliert – nach deutschem Recht unwirksam, bitte streichen"))
        if vorschau:
            if "VORSCHAU" not in text:
                f.append(t("Vorschau-Hinweis fehlt"))
        else:
            if "fehlt]" in raw or 'class="fehlt"' in raw or "FEHLT-" in raw or "VORSCHAU – nicht veröffentlichen" in raw:
                f.append(t("Vorschau-Markierung in der Veröffentlichung"))
        if not cfg["betreiber"]["gemeinnuetzig_anerkannt"] and not vorschau:
            for m in re.finditer(r"(?i)gemeinnützig", text):
                kontext = text[max(0, m.start() - 90):m.end() + 40].lower()
                if not re.search(r"\b(nicht|keine|kein|ohne|noch)\b", kontext):
                    f.append(t("„gemeinnützig“ ohne Anerkennung verwendet: …" + text[max(0, m.start() - 40):m.end() + 20].strip() + "…"))
    # CSS
    for css in (out / "assets").glob("*.css"):
        c = css.read_text(encoding="utf-8")
        for m in re.finditer(r"url\(\s*['\"]?([^)'\"]+)", c):
            u = m.group(1)
            if re.match(r"(?i)^(https?:)?//", u) or u.startswith("data:"):
                f.append(f"{css.name}: Fremd- oder Inline-Ressource {u[:40]}")
            elif not (css.parent / u.split("#")[0].split("?")[0]).is_file():
                f.append(f"{css.name}: Datei fehlt: {u}")
        if re.search(r"@import", c):
            f.append(f"{css.name}: @import nicht erlaubt")
    return f


# ---------------------------------------------------------------------------------------------------------------------
# 5. Bauen
# ---------------------------------------------------------------------------------------------------------------------
SEITENKOPF = re.compile(r"<!--seite\s+(.*?)-->", re.S)


def lade_teile() -> dict:
    teile = {}
    for p in sorted((SITE / "teile").glob("*.html")):
        nodes, _ = parse(TOKEN.split(p.read_text(encoding="utf-8")))
        teile[p.name] = nodes
    return teile


def mm_tt(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def kontext(cfg: dict, vorschau: bool, downloads_html: str) -> dict:
    ctx = json.loads(json.dumps(cfg))
    b = ctx["betreiber"]
    b["anzeige"] = b.get("initiative") or b.get("name") or ""
    b["adresse_text"] = ", ".join(x for x in (b.get("strasse"), f'{b.get("plz", "")} {b.get("ort", "")}'.strip(), b.get("land")) if x)
    b["ist_juristisch"] = bool(JURISTISCH.search(b.get("rechtsform", "")))
    b["hat_register"] = bool(b.get("register"))
    b["gemeinnuetzig"] = b.get("gemeinnuetzig_anerkannt") is True
    basis = ctx["downloads"]["basis_url"]
    ctx["downloads"]["extern"] = basis.startswith("https://")
    ctx["downloads"]["host"] = urlparse(basis).hostname or ""
    ctx["downloads"]["html"] = downloads_html
    ctx["vorschau"] = vorschau
    v = ctx["software"]["version"]
    ctx["software"]["stand_de"] = mm_tt(ctx["software"]["stand"]) if re.fullmatch(r"\d{4}-\d\d-\d\d", ctx["software"]["stand"] or "") else ""
    ctx["seite"]["stand_de"] = mm_tt(ctx["seite"]["stand"]) if re.fullmatch(r"\d{4}-\d\d-\d\d", ctx["seite"]["stand"] or "") else ""
    ctx["web"] = {"stand_jahr": (ctx["seite"]["stand"] or "")[:4]}
    ctx["ver"] = v
    w = ctx["website"]
    tage = w.get("logfiles_tage")
    if not isinstance(tage, int) or isinstance(tage, bool):
        w["logfiles_text"] = '<mark class="fehlt">[website.logfiles_tage fehlt]</mark>'
    elif tage == 0:
        w["logfiles_text"] = "werden nicht gespeichert"
    else:
        w["logfiles_text"] = f"werden höchstens {tage} Tage gespeichert und dann gelöscht"
    w["protokoll_hoster"] = w.get("protokolle") == "hoster"
    if w["protokoll_hoster"]:
        w["ip_kuerzen"] = False                      # Kürzung liegt nicht in unserer Hand, daher keine Zusage
    dl = w.get("hoster_drittland")
    if dl is True:
        w["drittland_satz"] = ("Der Hoster kann Daten auch in Staaten außerhalb des Europäischen Wirtschaftsraums verarbeiten, "
                               "insbesondere in den USA. Grundlage dafür ist: " + html.escape(str(w.get("hoster_drittland_grundlage", "")).rstrip(".")) + ".")
    elif dl is False:
        w["drittland_satz"] = "Wir übermitteln keine Daten in Länder außerhalb des Europäischen Wirtschaftsraums."
    else:
        w["drittland_satz"] = '<mark class="fehlt">[website.hoster_drittland fehlt]</mark>'
    return ctx


def erlaubte_hosts(cfg: dict) -> set[str]:
    hosts = {"neobiota.naturschutzinformationen.nrw.de", "www.gnu.org", "ffmpeg.org", "johnvansickle.com", "github.com",
             "www.ldi.nrw.de", "datenschutzkonferenz-online.de", "www.gesetze-im-internet.de", "www.lanuk.nrw.de",
             "gbif.org", "www.gbif.org", "telegram.org", "www.anthropic.com", "docs.openwebui.com", "ollama.com"}
    for pfad in ("aufsicht.web", "lizenz.text_url", "downloads.anbieter.datenschutz_url", "downloads.basis_url",
                 "website.hoster_datenschutz_url"):
        v = lookup(cfg, pfad)
        if isinstance(v, str) and v.startswith("https://"):
            hosts.add(urlparse(v).hostname or "")
    adr = lookup(cfg, "website.adresse")
    if isinstance(adr, str) and adr.startswith("https://"):
        hosts.add(urlparse(adr).hostname or "")
    return hosts


def baue(config_pfad: Path, vorschau: bool, aus: Path | None = None, dateien_kopieren: bool = False) -> tuple[list[str], Path]:
    cfg = json.loads(config_pfad.read_text(encoding="utf-8"))
    out = aus or (ROOT / ("vorschau" if vorschau else "public"))
    fehler: list[str] = []
    if not vorschau:
        fehler += pruefe_config(cfg, True)
    if fehler:
        return fehler, out
    # In der Vorschau fehlende Angaben nur markieren: leere Felder anlegen
    for pfad in HILFE:
        cur = cfg
        teile = pfad.split(".")
        for t in teile[:-1]:
            cur = cur.setdefault(t, {})
        cur.setdefault(teile[-1], "")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(SITE / "assets", out / "assets")
    downloads_html, kopieren, _info = baue_downloads(cfg, vorschau, fehler)
    ctx = kontext(cfg, vorschau, downloads_html)
    teile = lade_teile()
    seiten_dir = SITE / "seiten"
    namen = [p.name for p in sorted(seiten_dir.glob("*.html"))]
    for name in namen:
        rohtext = (seiten_dir / name).read_text(encoding="utf-8")
        m = SEITENKOPF.search(rohtext)
        if not m:
            raise BauFehler(f"{name}: Kopfzeile <!--seite titel=\"…\" …--> fehlt")
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        rumpf = rohtext[m.end():]
        c = dict(ctx)
        c["seite"] = dict(ctx["seite"], **{k: attrs.get(k, "") for k in ("titel", "beschreibung", "nav")}, datei=name)
        c["seite"]["pfad"] = "" if name == "index.html" else name
        adr0 = (cfg["website"].get("adresse") or "").rstrip("/")
        c["seite"]["kanonisch"] = (adr0 + "/" + c["seite"]["pfad"]) if (adr0.startswith("https://") and not vorschau and name != "404.html") else ""
        c["nav"] = {c["seite"]["nav"]: True}
        nodes, _ = parse(TOKEN.split("{% include kopf.html %}" + rumpf + "{% include fuss.html %}"))
        text = render(nodes, c, fehler, vorschau, teile, name)
        if name == "404.html":     # wird unter beliebiger Adresse ausgeliefert: Pfade absolut machen
            text = re.sub(r'(href|src)="(?!https?:|mailto:|#|/)([^"]+)"', r'\1="/\2"', text)
        (out / name).write_text(text, encoding="utf-8", newline="\n")
    adr = cfg["website"].get("adresse", "")
    (out / "robots.txt").write_text("User-agent: *\nAllow: /\n" + (f"Sitemap: {adr.rstrip('/')}/sitemap.xml\n" if adr.startswith("https://") and not vorschau else ""),
                                    encoding="utf-8", newline="\n")
    if adr.startswith("https://") and not vorschau:
        urls = "".join(f"  <url><loc>{html.escape(adr.rstrip('/') + '/' + ('' if n == 'index.html' else n))}</loc>"
                       f"<lastmod>{cfg['seite']['stand']}</lastmod></url>\n" for n in namen if n != "404.html")
        (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                         + urls + "</urlset>\n", encoding="utf-8", newline="\n")
    if dateien_kopieren and not ctx["downloads"]["extern"]:
        ziel = out / cfg["downloads"]["basis_url"]
        ziel.mkdir(parents=True, exist_ok=True)
        for quelle, name in kopieren:
            shutil.copy2(quelle, ziel / name)
    fehler += pruefe_ausgabe(out, cfg, vorschau, erlaubte_hosts(cfg))
    if dateien_kopieren and not ctx["downloads"]["extern"]:
        for quelle, name in kopieren:
            if sha256_datei(out / cfg["downloads"]["basis_url"] / name) != sha256_datei(quelle):
                fehler.append(f"{name}: Kopie weicht von der Quelle ab")
    return fehler, out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--vorschau", action="store_true", help="Vorschau mit Markierungen statt strenger Prüfung")
    ap.add_argument("--aus", default="", help="Ausgabeordner (Standard: public/ bzw. vorschau/)")
    ap.add_argument("--dateien-kopieren", action="store_true", help="Download-Dateien nach <ausgabe>/downloads/ kopieren")
    ap.add_argument("--felder", action="store_true", help="alle Felder der config.json erklären")
    a = ap.parse_args(argv)
    if a.felder:
        for k, v in HILFE.items():
            print(f"{k:42} {v}")
        return 0
    try:
        fehler, out = baue(Path(a.config), a.vorschau, Path(a.aus) if a.aus else None, a.dateien_kopieren)
    except BauFehler as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        return 1
    if fehler:
        print(f"BAU ABGEBROCHEN – {len(fehler)} Problem(e):", file=sys.stderr)
        for x in fehler:
            print(" ·", x, file=sys.stderr)
        if not a.vorschau:
            print("\nTipp: python build.py --vorschau zeigt die Seiten mit markierten Lücken.", file=sys.stderr)
        return 1
    n = len(list(out.glob("*.html")))
    print(f"{'VORSCHAU' if a.vorschau else 'FERTIG'}: {n} Seiten in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
