# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Automatische Tests des Website-Baukastens (pytest).

Aufruf:  python -m pytest tests -q

Wichtig zur Ehrlichkeit dieser Tests:
  * Die Betreiberdaten in tests/testconfig.json sind ERFUNDEN (Bienenschutz Teststand, *.invalid) und dienen nur diesen Tests.
  * Die „Download-Dateien“ sind TESTATTRAPPEN (Zufallsbytes mit Kennzeichnung), damit Größen und Prüfsummen echt berechnet
    und verglichen werden können. Das Produkt selbst (build.py, site/) enthält keine solchen Daten.
  * Ob die rechtlichen Texte juristisch tragen, kann kein Test prüfen. Geprüft wird, dass vorgesehene Bestandteile
    vorhanden und verbotene Zusicherungen (z. B. „jede Haftung ausgeschlossen“) nicht enthalten sind.
"""
from __future__ import annotations

import copy
import functools
import hashlib
import http.server
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("build", ROOT / "build.py")
build = importlib.util.module_from_spec(spec)
sys.modules["build"] = build
spec.loader.exec_module(build)

TESTCONFIG = json.loads((ROOT / "tests" / "testconfig.json").read_text(encoding="utf-8"))
DOWNLOADS = json.loads((ROOT / "site" / "daten" / "downloads.json").read_text(encoding="utf-8"))
VERSION = TESTCONFIG["software"]["version"]


# ---------------------------------------------------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------------------------------------------------
def leaf_pfade(d: dict, pre: str = "") -> set[str]:
    out: set[str] = set()
    for k, v in d.items():
        if isinstance(v, dict):
            out |= leaf_pfade(v, f"{pre}{k}.")
        else:
            out.add(f"{pre}{k}")
    return out


def erzeuge_testattrappen(ziel: Path, version: str = VERSION) -> Path:
    """TESTATTRAPPE: Dateien mit Zufallsinhalt + passende SHA256SUMS, genau so benannt wie echte Release-Dateien."""
    ziel.mkdir(parents=True, exist_ok=True)
    zeilen = []
    for e in DOWNLOADS["dateien"]:
        name = e["name"].replace("{v}", version)
        if e.get("ohne_summe"):
            continue
        daten = b"TESTATTRAPPE " + name.encode() + b"\n" + os.urandom(2048 + len(name))
        (ziel / name).write_bytes(daten)
        zeilen.append(f"{hashlib.sha256(daten).hexdigest()}  {name}")
    summen = "\n".join(zeilen) + "\n"
    (ziel / f"SHA256SUMS-{version}.txt").write_text(summen, encoding="utf-8")
    return ziel


def bau(tmp: Path, cfg: dict, vorschau: bool = False, kopieren: bool = True, name: str = "out"):
    p = tmp / f"cfg-{name}.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return build.baue(p, vorschau, tmp / name, kopieren)


@pytest.fixture(scope="session")
def attrappen(tmp_path_factory) -> Path:
    return erzeuge_testattrappen(tmp_path_factory.mktemp("TESTATTRAPPEN"))


@pytest.fixture()
def cfg(attrappen) -> dict:
    c = copy.deepcopy(TESTCONFIG)
    c["downloads"]["quelle_ordner"] = str(attrappen)
    return c


@pytest.fixture(scope="session")
def fertig(attrappen, tmp_path_factory) -> Path:
    """Einmal gebaute Veröffentlichungs-Fassung aus Testdaten."""
    c = copy.deepcopy(TESTCONFIG)
    c["downloads"]["quelle_ordner"] = str(attrappen)
    tmp = tmp_path_factory.mktemp("fertig")
    fehler, out = bau(tmp, c)
    assert fehler == [], fehler
    return out


def seite(out: Path, name: str) -> str:
    return (out / name).read_text(encoding="utf-8")


def sichtbarer_text(html_text: str) -> str:
    t = re.sub(r"(?s)<(script|style)\b.*?</\1>", " ", html_text)
    t = re.sub(r"<[^>]+>", " ", t)
    import html as h
    return re.sub(r"\s+", " ", h.unescape(t))


# ---------------------------------------------------------------------------------------------------------------------
# 1. Konfiguration und Schranke vor der Veröffentlichung
# ---------------------------------------------------------------------------------------------------------------------
def test_hilfe_und_config_json_decken_sich():
    ausgeliefert = leaf_pfade(json.loads((ROOT / "config.json").read_text(encoding="utf-8")))
    assert ausgeliefert == set(build.HILFE), (ausgeliefert ^ set(build.HILFE))


def test_testconfig_hat_alle_felder():
    assert leaf_pfade(TESTCONFIG) == set(build.HILFE)


def test_ausgelieferte_config_verweigert_veroeffentlichung(tmp_path):
    fehler, _ = build.baue(ROOT / "config.json", False, tmp_path / "x", False)
    text = "\n".join(fehler)
    assert fehler, "Leere Angaben dürfen nicht veröffentlicht werden"
    for pflicht in ("betreiber.name", "betreiber.strasse", "betreiber.email", "website.hoster_name",
                    "website.avv_abgeschlossen", "website.protokolle", "website.hoster_drittland", "gemeinnuetzig_nachweis"):
        assert pflicht in text, pflicht
    assert "lizenz." not in text, "Lizenz ist vorbelegt und darf nicht als fehlend gemeldet werden"
    assert not (tmp_path / "x").exists(), "Bei Fehlern darf nichts ausgegeben werden"


def test_ausgelieferte_config_erlaubt_vorschau_mit_markierungen(tmp_path):
    fehler, out = build.baue(ROOT / "config.json", True, tmp_path / "v", False)
    assert fehler == [], fehler
    index = seite(out, "index.html")
    impressum = seite(out, "impressum.html")
    assert "VORSCHAU – nicht veröffentlichen" in index
    assert 'class="fehlt"' in impressum
    assert (out / "robots.txt").is_file()
    assert "Sitemap:" not in (out / "robots.txt").read_text(encoding="utf-8")
    assert not (out / "sitemap.xml").exists(), "Vorschau darf keine Sitemap veröffentlichen"


def test_release_aus_testdaten_ist_sauber(fertig):
    assert len(list(fertig.glob("*.html"))) == 10
    for n in ("index", "download", "anleitung", "hinweise", "gemeinwohl", "haftung", "datenschutz", "impressum", "lizenzen", "404"):
        assert (fertig / f"{n}.html").is_file(), n
    for seite_ in fertig.glob("*.html"):
        t = seite_.read_text(encoding="utf-8")
        assert "VORSCHAU" not in t and 'class="fehlt"' not in t and "FEHLT-" not in t, seite_.name
        assert "{{" not in t and "{%" not in t, seite_.name


def fehler_fuer(tmp: Path, cfg: dict, **kw) -> str:
    fehler, _ = bau(tmp, cfg, **kw)
    return "\n".join(fehler)


def setze(cfg: dict, pfad: str, wert):
    cur = cfg
    teile = pfad.split(".")
    for t in teile[:-1]:
        cur = cur[t]
    cur[teile[-1]] = wert


@pytest.mark.parametrize("pfad,wert,erwartet", [
    ("betreiber.name", "Max Mustermann", "Platzhalter"),
    ("betreiber.email", "post@example.com", "Platzhalter"),
    ("betreiber.email", "keine-mail", "keine gültige E-Mail"),
    ("betreiber.plz", "123", "5 Ziffern"),
    ("betreiber.strasse", "Musterstraße 1", "Platzhalter"),
    ("betreiber.ort", "…", "Platzhalter"),
    ("betreiber.telefon", "abc", "Telefonnummer"),
    ("betreiber.vertretungsberechtigt", "", "vertretungsberechtigt: fehlt"),
    ("betreiber.register", "", "register: fehlt"),
    ("betreiber.registernummer", "", "registernummer: fehlt"),
    ("betreiber.gemeinnuetzig_anerkannt", "ja", "true oder false"),
    ("betreiber.gemeinnuetzig_anerkannt", None, "true oder false"),
    ("betreiber.gemeinnuetzig_nachweis", "", "gemeinnuetzig_nachweis: fehlt"),
    ("website.adresse", "http://seite.test.de", "https://"),
    ("website.adresse", "", "website.adresse: fehlt"),
    ("website.hoster_name", "", "hoster_name: fehlt"),
    ("website.avv_abgeschlossen", False, "avv_abgeschlossen"),
    ("website.logfiles_tage", 400, "logfiles_tage"),
    ("website.logfiles_tage", -1, "logfiles_tage"),
    ("website.logfiles_tage", True, "logfiles_tage"),
    ("website.logfiles_tage", "7", "logfiles_tage"),
    ("website.ip_kuerzen", "ja", "ip_kuerzen"),
    ("website.protokolle", "irgendwer", "nur „selbst“ oder „hoster“"),
    ("website.protokolle", "", "protokolle: fehlt"),
    ("website.hoster_drittland", None, "true oder false"),
    ("website.hoster_drittland", True, "hoster_drittland_grundlage: fehlt"),
    ("website.hoster_drittland_grundlage", "irgendwas", "nur ausfüllen, wenn hoster_drittland = true"),
    ("website.hoster_datenschutz_url", "http://hoster.test.de/datenschutz", "https://"),
    ("downloads.basis_url", "http://dl.test.de/", "https://"),
    ("downloads.basis_url", "../x/", "relativer Ordner"),
    ("downloads.basis_url", "/abs/", "relativer Ordner"),
    ("downloads.basis_url", "downloads", "relativer Ordner"),
    ("downloads.basis_url", "https://dl.testhost.invalid/", "anbieter.name: fehlt"),
    ("downloads.quelle_ordner", "/gibt/es/nicht", "Ordner nicht gefunden"),
    ("software.version", "1.3", "version"),
    ("software.stand", "15.11.2026", "stand"),
    ("software.apk_zertifikat_sha256", "abc", "apk_zertifikat"),
    ("lizenz.eigener_code", "", "lizenz.eigener_code: fehlt"),
    ("lizenz.text_url", "http://www.gnu.org/licenses/gpl-3.0.html", "https://"),
    ("aufsicht.web", "www.ldi.nrw.de", "https://"),
    ("seite.stand", "gestern", "stand"),
])
def test_ungueltige_angaben_werden_abgelehnt(tmp_path, cfg, pfad, wert, erwartet):
    setze(cfg, pfad, wert)
    text = fehler_fuer(tmp_path, cfg)
    assert text, f"{pfad}={wert!r} hätte abgelehnt werden müssen"
    assert erwartet.lower() in text.lower(), text


def test_ohne_zweiten_kontaktweg_abgelehnt(tmp_path, cfg):
    cfg["betreiber"]["telefon"] = ""
    cfg["betreiber"]["kontakt_alternative"] = ""
    assert "zweiter, schneller Kontaktweg" in fehler_fuer(tmp_path, cfg)
    cfg["betreiber"]["kontakt_alternative"] = "Kontaktformular auf Anfrage per Post"
    assert fehler_fuer(tmp_path, cfg, name="zwei") == ""


def test_privatperson_braucht_kein_register(tmp_path, cfg):
    b = cfg["betreiber"]
    b.update(rechtsform="Privatperson", name="Erika Testfrau", vertretungsberechtigt="", register="", registernummer="",
             gemeinnuetzig_anerkannt=False, gemeinnuetzig_nachweis="")
    assert fehler_fuer(tmp_path, cfg) == ""


def test_externer_anbieter_vollstaendig_ok(tmp_path, cfg):
    cfg["downloads"].update(basis_url="https://dl.testhost.invalid/hornet/", anbieter={
        "name": "Testdownload AG", "anschrift": "Weg 3, 54321 Dlstadt", "datenschutz_url": "https://dl.testhost.invalid/datenschutz"})
    fehler, out = bau(tmp_path, cfg)
    assert fehler == [], fehler
    ds = sichtbarer_text(seite(out, "datenschutz.html"))
    assert "Testdownload AG" in ds and "Ihre IP-Adresse" in ds
    assert 'href="https://dl.testhost.invalid/hornet/Hornet3000-Setup-1.3.0.exe"' in seite(out, "download.html")
    assert not (out / "downloads").exists(), "Bei externem Anbieter werden keine Dateien kopiert"


# ---------------------------------------------------------------------------------------------------------------------
# 2. Download-Dateien: echte Größen und Prüfsummen
# ---------------------------------------------------------------------------------------------------------------------
def test_download_seite_zeigt_echte_pruefsummen_und_kopien_sind_identisch(fertig, attrappen):
    dl = seite(fertig, "download.html")
    zaehler = 0
    for e in DOWNLOADS["dateien"]:
        name = e["name"].replace("{v}", VERSION)
        quelle = attrappen / name
        if not quelle.is_file():
            continue
        zaehler += 1
        sha = hashlib.sha256(quelle.read_bytes()).hexdigest()
        assert sha in dl, name
        kopie = fertig / "downloads" / name
        assert kopie.read_bytes() == quelle.read_bytes(), name
        assert f'href="downloads/{name}"' in dl
    assert zaehler >= 8


def test_beschaedigte_datei_wird_erkannt(tmp_path, cfg, attrappen):
    kopie = tmp_path / "q"
    shutil.copytree(attrappen, kopie)
    cfg["downloads"]["quelle_ordner"] = str(kopie)
    ziel = kopie / f"Hornet3000-Setup-{VERSION}.exe"
    ziel.write_bytes(ziel.read_bytes() + b"x")
    text = fehler_fuer(tmp_path, cfg)
    assert "Prüfsumme der Datei" in text and "Setup" in text


def test_fehlende_datei_summe_oder_eintrag_wird_erkannt(tmp_path, cfg, attrappen):
    k = tmp_path / "q2"
    shutil.copytree(attrappen, k)
    cfg["downloads"]["quelle_ordner"] = str(k)
    (k / f"Hornet3000-Station-{VERSION}.apk").unlink()
    assert "Download-Datei fehlt: Hornet3000-Station" in fehler_fuer(tmp_path, cfg, name="a")
    k3 = tmp_path / "q3"
    shutil.copytree(attrappen, k3)
    cfg["downloads"]["quelle_ordner"] = str(k3)
    (k3 / f"SHA256SUMS-{VERSION}.txt").unlink()
    assert "SHA256SUMS-1.3.0.txt nicht gefunden" in fehler_fuer(tmp_path, cfg, name="b")
    k4 = tmp_path / "q4"
    shutil.copytree(attrappen, k4)
    cfg["downloads"]["quelle_ordner"] = str(k4)
    p = k4 / f"SHA256SUMS-{VERSION}.txt"
    p.write_text("\n".join(l for l in p.read_text().splitlines() if "Update" not in l) + "\n")
    assert "steht nicht in SHA256SUMS" in fehler_fuer(tmp_path, cfg, name="c")


def test_apk_fingerprint_stimmt_mit_echter_apk_ueberein():
    apk = Path(os.environ.get("HORNET_APK", "/mnt/user-data/outputs/1.3.0/Hornet3000-Station-1.3.0.apk"))
    if not apk.is_file() or not shutil.which("apksigner"):
        pytest.skip("echte APK oder apksigner nicht vorhanden")
    ausgabe = subprocess.run(["apksigner", "verify", "--print-certs", str(apk)], capture_output=True, text=True, timeout=120).stdout
    m = re.search(r"certificate SHA-256 digest: ([0-9a-f]{64})", ausgabe)
    assert m, ausgabe
    ausgeliefert = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["software"]["apk_zertifikat_sha256"]
    assert m.group(1) == ausgeliefert
    assert m.group(1) == TESTCONFIG["software"]["apk_zertifikat_sha256"]


# ---------------------------------------------------------------------------------------------------------------------
# 3. Inhalt der rechtlichen Seiten
# ---------------------------------------------------------------------------------------------------------------------
def test_impressum_pflichtangaben_und_ki_hersteller(fertig):
    h = seite(fertig, "impressum.html")
    t = sichtbarer_text(h)
    for teil in ("§ 5 Digitale-Dienste-Gesetz", "Bienenschutz Teststand e. V.", "Teststraße 1", "50000 Teststadt",
                 "Erika Testfrau", "kontakt@teststand.invalid", "+49 2200 000000", "Vereinsregister", "VR 00000"):
        assert teil in t, teil
    assert 'id="ki"' in h
    for teil in ("Die Software wurde von einer künstlichen Intelligenz hergestellt", "Claude", "Anthropic PBC",
                 "Eine KI ist keine Rechtsperson", "die KI die Herstellerin der Software", "der Anbieter",
                 "weder diese Website noch bietet es die Software an"):
        assert teil in t, teil
    assert not re.search(r"V\.\.", t)


def test_ki_hinweis_auf_jeder_seite_im_fuss(fertig):
    for p in fertig.glob("*.html"):
        if p.name == "404.html":
            continue
        t = p.read_text(encoding="utf-8")
        assert 'href="impressum.html#ki"' in t, p.name
        for nav in ('href="haftung.html"', 'href="datenschutz.html"', 'href="impressum.html"'):
            assert nav in t, (p.name, nav)


def test_haftungsausschluss_gesetzeskonform_und_ohne_absolutes(fertig):
    t = sichtbarer_text(seite(fertig, "haftung.html"))
    for teil in ("Vorsatz", "grobe Fahrlässigkeit", "Leben, Körper oder Gesundheit", "arglistig", "Garantien",
                 "Produkthaftungsgesetz", "soweit das gesetzlich zulässig ist", "wollen niemandem schaden",
                 "unentgeltlich", "§§ 521, 599 BGB", "keine Rechtsberatung", "stammen von einer KI"):
        assert teil.lower() in t.lower(), teil
    assert not build.ABSOLUT.search(t), build.ABSOLUT.search(t)
    # Ehrlich: es wird nirgends behauptet, jede Haftung sei ausgeschlossen
    assert not re.search(r"(?i)\b(jede|jegliche|keinerlei)\s+haftung", t)


def test_datenschutz_pflichtbestandteile(fertig):
    t = sichtbarer_text(seite(fertig, "datenschutz.html"))
    for teil in ("Verantwortlicher", "Bienenschutz Teststand e. V.", "Art. 6 Abs. 1 lit. f DSGVO", "Testhoster GmbH",
                 "Auftragsverarbeitung nach Art. 28 DSGVO", "höchstens 7 Tage", "Art. 15 DSGVO", "Art. 16 DSGVO", "Art. 17 DSGVO",
                 "Art. 18 DSGVO", "Art. 20 DSGVO", "Art. 21 DSGVO", "Art. 77 DSGVO", "Landesbeauftragte für Datenschutz",
                 "keine Cookies", "kein JavaScript", "Beschwerde", "gekürzt"):
        assert teil.lower() in t.lower(), teil


def test_datenschutz_verzweigungen(tmp_path, cfg):
    cfg["website"]["ip_kuerzen"] = False
    cfg["website"]["logfiles_tage"] = 0
    fehler, out = bau(tmp_path, cfg, name="a")
    assert fehler == []
    t = sichtbarer_text(seite(out, "datenschutz.html"))
    assert "gekürzt" not in t
    assert "werden nicht gespeichert" in t
    cfg["website"]["logfiles_tage"] = 30
    fehler, out = bau(tmp_path, cfg, name="b")
    assert "höchstens 30 Tage" in sichtbarer_text(seite(out, "datenschutz.html"))


def test_gemeinnuetzig_wird_nur_mit_nachweis_behauptet(tmp_path, cfg):
    fehler, out = bau(tmp_path, cfg, name="ja")
    assert fehler == []
    assert "als gemeinnützig anerkannt: Freistellungsbescheid" in sichtbarer_text(seite(out, "impressum.html"))
    cfg["betreiber"]["gemeinnuetzig_anerkannt"] = False
    cfg["betreiber"]["gemeinnuetzig_nachweis"] = ""
    fehler, out = bau(tmp_path, cfg, name="nein")
    assert fehler == [], fehler
    for n in ("impressum.html", "gemeinwohl.html", "index.html", "haftung.html", "download.html"):
        t = sichtbarer_text(seite(out, n))
        assert "als gemeinnützig anerkannt" not in t, n
        assert "steuerbegünstigt" not in t, n
    assert "keine Gewinnabsicht" in sichtbarer_text(seite(out, "impressum.html"))


def test_absolute_haftungsfloskel_in_den_seiten_wird_vom_bau_abgelehnt(tmp_path, cfg, monkeypatch):
    rohling = ROOT / "site" / "seiten" / "haftung.html"
    original = rohling.read_text(encoding="utf-8")
    seiten_neu = tmp_path / "site"
    shutil.copytree(ROOT / "site", seiten_neu)
    (seiten_neu / "seiten" / "haftung.html").write_text(original + "\n<p>Jegliche Haftung ist ausgeschlossen.</p>\n", encoding="utf-8")
    monkeypatch.setattr(build, "SITE", seiten_neu)
    fehler, _ = bau(tmp_path, cfg, name="abs")
    assert any("haftung" in f.lower() for f in fehler), fehler


def test_keine_doppelten_satzpunkte(fertig):
    for p in fertig.glob("*.html"):
        t = sichtbarer_text(p.read_text(encoding="utf-8"))
        assert not re.search(r"(?<![.\s])\.\.(?!\.)", t), (p.name, re.search(r".{20}(?<![.\s])\.\.(?!\.).{10}", t))


# ---------------------------------------------------------------------------------------------------------------------
# 4. Vorlagen-Engine
# ---------------------------------------------------------------------------------------------------------------------
def vorlage(text: str, ctx: dict, teile: dict | None = None, vorschau: bool = False):
    nodes, _ = build.parse(build.TOKEN.split(text))
    fehler: list[str] = []
    return build.render(nodes, ctx, fehler, vorschau, teile or {}, "test"), fehler


def test_vorlage_maskiert_und_roh():
    ctx = {"x": '<b>&"\'</b>', "r": "<i>ok</i>"}
    out, f = vorlage("{{ x }}|{{= r }}", ctx)
    assert out == "&lt;b&gt;&amp;&quot;&#x27;&lt;/b&gt;|<i>ok</i>" and f == []


def test_vorlage_wenn_sonst_nicht():
    ctx = {"a": True, "b": "", "c": {"d": "x"}}
    assert vorlage("{% if a %}ja{% else %}nein{% endif %}", ctx)[0] == "ja"
    assert vorlage("{% if b %}ja{% else %}nein{% endif %}", ctx)[0] == "nein"
    assert vorlage("{% if not b %}leer{% endif %}", ctx)[0] == "leer"
    assert vorlage("{% if c.d %}{{ c.d }}{% endif %}", ctx)[0] == "x"
    assert vorlage("{% if fehlt %}ja{% else %}nein{% endif %}", ctx)[0] == "nein"


def test_vorlage_include_und_fehler():
    nodes, _ = build.parse(build.TOKEN.split("[{{ n }}]"))
    out, f = vorlage("a{% include t.html %}b", {"n": "1"}, {"t.html": nodes})
    assert out == "a[1]b"
    with pytest.raises(build.BauFehler):
        vorlage("{% include gibtsnicht.html %}", {})
    with pytest.raises(build.BauFehler):
        vorlage("{% if a %}offen", {"a": 1})


def test_leerer_wert_ist_im_release_ein_fehler_in_der_vorschau_markiert():
    out, f = vorlage("{{ a.b }}", {})
    assert f and "a.b" in f[0]
    out, f = vorlage("{{ a.b }}", {}, vorschau=True)
    assert f == [] and 'class="fehlt"' in out
    out, f = vorlage('<a href="{{ a.b }}">x</a>', {}, vorschau=True)
    assert "<mark" not in out and "FEHLT-a.b" in out


def test_doppelter_satzpunkt_nach_wert_mit_punkt():
    assert vorlage("{{ n }}. Danach", {"n": "Verein e. V."})[0] == "Verein e. V. Danach"
    assert vorlage("{{ n }}. Danach", {"n": "Verein"})[0] == "Verein. Danach"
    assert vorlage("{{ n }}...", {"n": "Ende."})[0] == "Ende...."      # Auslassungspunkte bleiben unangetastet
    assert vorlage("{{ n }}</li>", {"n": "e. V."})[0] == "e. V.</li>"


# ---------------------------------------------------------------------------------------------------------------------
# 5. Technische Qualität der fertigen Seiten
# ---------------------------------------------------------------------------------------------------------------------
class Klammern(HTMLParser):
    VOID = {"meta", "link", "img", "br", "hr", "input", "source", "wbr", "area", "col"}

    def __init__(self):
        super().__init__()
        self.stack: list[str] = []
        self.fehler: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.fehler.append(f"</{tag}> passt nicht zu {self.stack[-1:]}")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
        else:
            self.stack.pop()


def test_html_ist_wohlgeformt(fertig):
    for p in fertig.glob("*.html"):
        k = Klammern()
        k.feed(p.read_text(encoding="utf-8"))
        assert not k.fehler and not k.stack, (p.name, k.fehler[:3], k.stack[:3])


def test_grundregeln_aller_seiten(fertig):
    for p in fertig.glob("*.html"):
        t = p.read_text(encoding="utf-8")
        assert t.startswith("<!doctype html>"), p.name
        assert '<html lang="de">' in t, p.name
        assert "default-src 'none'" in t and "form-action 'none'" in t and "base-uri 'none'" in t, p.name
        assert 'name="referrer" content="no-referrer"' in t, p.name
        assert len(re.findall(r"<h1\b", t)) == 1, p.name
        assert "<script" not in t.lower() and "<iframe" not in t.lower() and "<form" not in t.lower(), p.name
        assert not re.search(r'\s(style|on\w+)=', t), p.name
        assert not re.search(r'(?:src|href)="//', t), p.name            # keine protokollrelativen Fremdadressen


def test_nur_erlaubte_externe_ziele_und_alle_mit_noopener(fertig):
    for p in fertig.glob("*.html"):
        t = p.read_text(encoding="utf-8")
        for m in re.finditer(r'<a\b[^>]*href="(https?://[^"]+)"[^>]*>', t):
            assert m.group(1).startswith("https://"), (p.name, m.group(1))
            assert 'rel="noopener noreferrer"' in m.group(0), (p.name, m.group(1))
        for m in re.finditer(r'<(?:img|link|source)\b[^>]*(?:src|href)="(https?:[^"]+)"', t):
            assert "canonical" in m.group(0), (p.name, m.group(1))


def test_404_hat_absolute_pfade(fertig):
    t = seite(fertig, "404.html")
    for m in re.finditer(r'(?:href|src)="([^"]+)"', t):
        u = m.group(1)
        assert u.startswith(("/", "https://", "mailto:", "#")), u


def test_sitemap_robots_und_canonical(fertig):
    adr = TESTCONFIG["website"]["adresse"]
    sm = (fertig / "sitemap.xml").read_text(encoding="utf-8")
    assert f"<loc>{adr}/</loc>" in sm and f"<loc>{adr}/impressum.html</loc>" in sm and "404" not in sm
    assert f"Sitemap: {adr}/sitemap.xml" in (fertig / "robots.txt").read_text(encoding="utf-8")
    assert f'<link rel="canonical" href="{adr}/impressum.html">' in seite(fertig, "impressum.html")
    assert "canonical" not in seite(fertig, "404.html")


def test_alle_internen_links_und_anker_loesen_auf(fertig):
    ids: dict[str, set[str]] = {p.name: set(re.findall(r'\sid="([^"]+)"', p.read_text(encoding="utf-8"))) for p in fertig.glob("*.html")}
    for p in fertig.glob("*.html"):
        if p.name == "404.html":
            continue
        t = p.read_text(encoding="utf-8")
        for u in re.findall(r'(?:href|src)="([^"#:][^"]*)"', t):
            if u.startswith(("http://", "https://", "mailto:")):
                continue
            ziel, _, anker = u.partition("#")
            assert (fertig / ziel).exists(), (p.name, u)
            if anker and ziel.endswith(".html"):
                assert anker in ids[ziel], (p.name, u)
        for a in re.findall(r'href="#([^"]+)"', t):
            assert a in ids[p.name], (p.name, a)


def test_keine_pfade_oder_zugangsdaten_im_ergebnis(fertig, attrappen):
    for p in fertig.rglob("*"):
        if "downloads" in p.relative_to(fertig).parts:      # Testattrappen sind Binärdaten
            continue
        if p.is_file() and p.suffix in {".html", ".css", ".xml", ".txt", ".svg"}:
            t = p.read_text(encoding="utf-8")
            assert str(attrappen) not in t, p
            assert "/home/" not in t and "/tmp/" not in t, p
            assert not re.search(r"(?i)password|passwort\.txt|keystore", t), p


# --- Kontraste (WCAG 2.x) -------------------------------------------------------------------------------------------
def luminanz(hexfarbe: str) -> float:
    h = hexfarbe.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def kontrast(a: str, b: str) -> float:
    la, lb = sorted((luminanz(a), luminanz(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def tokens(css: str) -> tuple[dict, dict]:
    hell = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", re.search(r":root\s*\{(.*?)\n\}", css, re.S).group(1)))
    dunkel_block = re.search(r"prefers-color-scheme: dark\)\s*\{\s*:root\s*\{(.*?)\}", css, re.S).group(1)
    dunkel = dict(hell)
    dunkel.update(dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", dunkel_block)))
    return hell, dunkel


@pytest.mark.parametrize("modus", [0, 1], ids=["hell", "dunkel"])
def test_kontraste_der_farbpaare(modus):
    css = (ROOT / "site" / "assets" / "style.css").read_text(encoding="utf-8")
    t = tokens(css)[modus]
    paare = [("ink", "bg"), ("ink", "surface"), ("ink-2", "bg"), ("ink-2", "surface"), ("calm", "bg"), ("calm", "surface"),
             ("calm", "calm-bg"), ("on-calm", "calm"), ("warn", "warn-bg"), ("warn", "surface"), ("alarm", "alarm-bg"),
             ("alarm", "surface"), ("ink", "warn-bg"), ("ink", "alarm-bg"), ("ink", "calm-bg"), ("focus", "bg")]
    for vorder, grund in paare:
        c = kontrast(t[vorder], t[grund])
        grenze = 3.0 if vorder == "focus" else 4.5       # Text: WCAG 1.4.3 (4,5:1); Fokusrahmen: WCAG 1.4.11 (3:1)
        assert c >= grenze, f"{vorder} auf {grund}: {c:.2f}"


def test_css_ohne_fremdadressen_und_mit_druckansicht():
    css = (ROOT / "site" / "assets" / "style.css").read_text(encoding="utf-8")
    assert not re.search(r"https?://", css.replace("http://www.w3.org", ""))
    assert "@import" not in css
    assert "@media print" in css
    assert "prefers-reduced-motion" in css or "animation" not in css and "transition" not in css


# ---------------------------------------------------------------------------------------------------------------------
# 6. Betrieb: echter HTTP-Server, keine Cookies, nur eigene Dateien
# ---------------------------------------------------------------------------------------------------------------------
class Still(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def test_http_ausgeliefert_ohne_cookies_und_ohne_fremdhosts(fertig):
    handler = functools.partial(Still, directory=str(fertig))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        for p in sorted(fertig.glob("*.html")):
            r = urllib.request.urlopen(f"{base}/{p.name}", timeout=10)
            assert r.status == 200
            assert not r.headers.get_all("Set-Cookie"), p.name
            r.read()
        css = urllib.request.urlopen(f"{base}/assets/style.css", timeout=10).read().decode()
        for f in re.findall(r'url\("([^"]+)"\)', css):
            assert urllib.request.urlopen(f"{base}/assets/{f}", timeout=10).status == 200, f
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"{base}/gibt-es-nicht.html", timeout=10)
        assert e.value.code == 404
        # Download wird wirklich unverändert ausgeliefert
        name = f"Hornet3000-Setup-{VERSION}.exe"
        geholt = urllib.request.urlopen(f"{base}/downloads/{name}", timeout=10).read()
        assert hashlib.sha256(geholt).hexdigest() in seite(fertig, "download.html")
    finally:
        srv.shutdown()


def python_mit_playwright() -> str | None:
    for py in (sys.executable, "/usr/bin/python3", shutil.which("python3") or ""):
        if py and subprocess.run([py, "-c", "import playwright"], capture_output=True).returncode == 0:
            return py
    return None


def test_browserpruefung_handy_tablet_desktop_hell_dunkel(fertig):
    py = python_mit_playwright()
    if not py:
        pytest.skip("Playwright nicht installiert (pip install playwright && playwright install chromium)")
    r = subprocess.run([py, str(ROOT / "tests" / "browser_check.py"), str(fertig)], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    assert " 0 Fehler" in r.stdout


# ---------------------------------------------------------------------------------------------------------------------
# 7. Hosting bei einem Dritten (z. B. Google Firebase Hosting), Organisation statt Privatperson, Lizenz
# ---------------------------------------------------------------------------------------------------------------------
GOOGLE_DS = "https://firebase.google.com/support/privacy"
GRUNDLAGE = "Angemessenheitsbeschluss der EU-Kommission (EU-US Data Privacy Framework) und Standardvertragsklauseln"


def als_fremd_hoster(cfg: dict) -> dict:
    cfg["website"].update(hoster_name="Testcloud Ltd.", hoster_anschrift="Cloudweg 1, Dublin, Irland", hoster_land="Irland",
                          protokolle="hoster", logfiles_tage=None, ip_kuerzen=None, hoster_datenschutz_url=GOOGLE_DS,
                          hoster_drittland=True, hoster_drittland_grundlage=GRUNDLAGE)
    return cfg


def test_fremd_hoster_datenschutz_sagt_ehrlich_wer_protokolliert(tmp_path, cfg):
    fehler, out = bau(tmp_path, als_fremd_hoster(cfg))
    assert fehler == [], fehler
    t = sichtbarer_text(seite(out, "datenschutz.html"))
    for teil in ("Testcloud Ltd.", "Die Server-Protokolle führt der Hoster nach eigenen Regeln",
                 "Wir selbst speichern keine Protokolle über Ihren Aufruf", "auf einzelne Protokolleinträge keinen Zugriff",
                 "Datenschutzinformationen des Hosters", "Auftragsverarbeitung nach Art. 28 DSGVO",
                 "auch in Staaten außerhalb des Europäischen Wirtschaftsraums verarbeiten", "insbesondere in den USA",
                 "Grundlage dafür ist: " + GRUNDLAGE + "."):
        assert teil in t, teil
    # Keine Zusagen, die wir nicht halten können:
    assert "höchstens" not in t and "gekürzt" not in t and "werden nicht gespeichert" not in t
    assert f'<a href="{GOOGLE_DS}" rel="noopener noreferrer">' in seite(out, "datenschutz.html")


def test_fremd_hoster_verbietet_eigene_log_zusagen(tmp_path, cfg):
    als_fremd_hoster(cfg)
    cfg["website"]["logfiles_tage"] = 7
    assert "auf null setzen" in fehler_fuer(tmp_path, cfg)


def test_ohne_drittland_steht_kein_usa_satz(tmp_path, cfg):
    fehler, out = bau(tmp_path, cfg)
    assert fehler == []
    t = sichtbarer_text(seite(out, "datenschutz.html"))
    assert "Wir übermitteln keine Daten in Länder außerhalb des Europäischen Wirtschaftsraums." in t
    assert "USA" not in t


def test_email_anbieter_wird_in_datenschutz_genannt(tmp_path, cfg):
    cfg["betreiber"]["email_anbieter"] = "Testmail Ltd. (E-Mail-Dienst)"
    fehler, out = bau(tmp_path, cfg, name="mit")
    assert fehler == []
    t = sichtbarer_text(seite(out, "datenschutz.html"))
    assert "Unser E-Mail-Postfach wird bei Testmail Ltd. (E-Mail-Dienst) geführt" in t
    assert "außer an den Betreiber unseres E-Mail-Postfachs" in t and "per Post an die Anschrift im Impressum" in t
    cfg["betreiber"]["email_anbieter"] = ""
    fehler, out = bau(tmp_path, cfg, name="ohne")
    t = sichtbarer_text(seite(out, "datenschutz.html"))
    assert "E-Mail-Postfach" not in t and "Wir geben sie nicht an Dritte weiter." in t


def test_organisation_nennt_nur_vorstand_nicht_den_betreuer(fertig):
    """Mit Verein als Betreiber steht im Impressum der Verein plus EINE vertretungsberechtigte Person (§ 5 DDG), sonst niemand."""
    t = sichtbarer_text(seite(fertig, "impressum.html"))
    assert "Vertretungsberechtigt: Erika Testfrau" in t
    namen = re.findall(r"\b(?:Herr|Frau|Dr\.|Prof\.)\s+\w+", t)
    assert namen == [], namen


def test_ausgelieferte_config_ist_frei_lizenziert_und_gemeinnuetzig_vorbereitet():
    c = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    assert c["lizenz"] == {"eigener_code": "GPL-3.0-or-later", "text_url": "https://www.gnu.org/licenses/gpl-3.0.html"}
    assert c["betreiber"]["gemeinnuetzig_anerkannt"] is True          # Freistellungsbescheid liegt laut Betreiber vor
    assert c["betreiber"]["gemeinnuetzig_nachweis"] == "", "Der Nachweis (Finanzamt, Datum) darf nicht erfunden werden"


def test_lizenzseite_nennt_freie_nutzung(fertig):
    t = sichtbarer_text(seite(fertig, "lizenzen.html"))
    assert "Lizenz GPL-3.0-or-later" in t
    assert "kostenlos nutzen, ändern und weitergeben" in t
    assert "https://www.gnu.org/licenses/gpl-3.0.html" in t


def test_firebase_json_passt_zu_den_seiten(fertig):
    fb = json.loads((ROOT / "firebase.json").read_text(encoding="utf-8"))["hosting"]
    assert fb["public"] == "public" and fb["cleanUrls"] is False
    assert "firebase.json" in fb["ignore"] and "**/.*" in fb["ignore"]
    kopf = {h["key"]: h["value"] for h in fb["headers"][0]["headers"]}
    assert fb["headers"][0]["source"] == "**"
    assert kopf["X-Content-Type-Options"] == "nosniff" and kopf["Referrer-Policy"] == "no-referrer"
    csp = kopf["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in csp
    meta = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', seite(fertig, "index.html")).group(1)
    for teil in meta.split(";"):
        assert teil.strip() in csp, teil
    nginx = (ROOT / "server" / "nginx.conf.beispiel").read_text(encoding="utf-8")
    assert csp in nginx, "nginx- und Firebase-Kopfzeilen müssen übereinstimmen"
