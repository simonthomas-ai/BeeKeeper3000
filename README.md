# Hornet3000 – Website zum Anbieten der Software an Imkerinnen und Imker

Eine rein statische Website (nur HTML und CSS, **kein JavaScript, keine Cookies, keine Fremdinhalte**), über die ihr
Hornet3000 Wächter unentgeltlich anbietet. Sie nennt das Gemeinwohl als Ziel, enthält einen Haftungsausschluss, eine
Datenschutzerklärung nach DSGVO und ein Impressum, das offenlegt, dass die Software von einer KI hergestellt wurde.

Der Baukasten (`build.py`, nur Python-Standardbibliothek, ab Python 3.9) setzt die Seiten aus euren Angaben zusammen und
**weigert sich, eine Website zu erzeugen, solange Pflichtangaben fehlen oder nach Platzhaltern aussehen.** Es gibt keine
erfundenen Beispieldaten im Ergebnis.

> **Wichtig:** Das hier ist technische Vorarbeit und kein Rechtsrat. Die Texte sind sorgfältig am deutschen Recht
> ausgerichtet, aber ich bin keine Anwältin und kein Anwalt. Lasst Impressum, Datenschutz und Haftungstext einmal von
> einer fachkundigen Person prüfen (Verbraucherzentrale, Rechtsanwalt, Verein mit Rechtsberatung), bevor ihr online geht.
> Einen vollständigen Haftungsausschluss kann kein Text bewirken (siehe unten).

## Schnellstart

1. **Ansehen:** `python build.py --vorschau` erzeugt `vorschau/`. Fehlende Angaben sind rot markiert, auf jeder Seite
   steht „VORSCHAU – nicht veröffentlichen“. Öffnet `vorschau/index.html` im Browser (in Chromium getestet). Erscheint die
   Seite ungestaltet, startet einen lokalen Server: `python -m http.server -d vorschau` und öffnet `http://localhost:8000`.
2. **Ausfüllen:** `config.json` bearbeiten. `python build.py --felder` erklärt jedes Feld.
3. **Dateien bereitstellen:** Release-Ordner mit den Installern und `SHA256SUMS-<Version>.txt` (so wie die Software
   ausgeliefert wird). Den Ordner in `downloads.quelle_ordner` eintragen.
4. **Bauen:** `python build.py --dateien-kopieren` erzeugt `public/`. Der Bau bricht mit einer lesbaren Liste ab, wenn
   etwas fehlt, widersprüchlich ist oder eine Prüfsumme nicht stimmt.
5. **Hochladen:** den Inhalt von `public/` auf euren Webspace oder Server legen. Für nginx liegt eine geprüfte
   Beispielkonfiguration in `server/`.

## Was ihr selbst eintragen müsst (`config.json`)

| Bereich | Felder | Hinweis |
|---|---|---|
| `betreiber` | Name, Rechtsform, **ladungsfähige Anschrift**, E-Mail, zweiter Kontaktweg | § 5 DDG. Ein Postfach genügt nicht. Bei Privatpersonen ist die Wohnanschrift öffentlich. Wer das nicht will, gründet einen Verein oder nutzt eine Impressumsadresse (Dienstleister). |
| `betreiber` | `vertretungsberechtigt`, `register`, `registernummer` | Pflicht bei e. V., GmbH, UG usw. |
| `betreiber` | `gemeinnuetzig_anerkannt` | **Nur `true`, wenn ihr einen gültigen Freistellungs- oder Feststellungsbescheid des Finanzamts habt.** Dann auch `gemeinnuetzig_nachweis` (z. B. „Freistellungsbescheid des Finanzamts … vom …“). Sonst `false`: Die Seiten sprechen dann nur von „ohne Gewinnabsicht“ und behaupten nichts Falsches. |
| `website` | `adresse`, `hoster_*`, `avv_abgeschlossen` | Mit dem Hoster muss ein Auftragsverarbeitungsvertrag bestehen (Art. 28 DSGVO). Fast jeder Hoster bietet ihn zum Anklicken an. |
| `website` | `logfiles_tage`, `ip_kuerzen` | **Müssen zur Server-Einstellung passen.** Die Datenschutzerklärung übernimmt genau diese Werte. Siehe `server/nginx.conf.beispiel` und `server/logrotate.beispiel`. |
| `lizenz` | `eigener_code`, `text_url` | Entscheidung der Rechteinhaberin bzw. des Rechteinhabers. Empfehlung: `GPL-3.0-or-later` (siehe Offene Punkte). |
| `aufsicht` | Behörde | Vorbelegt mit der LDI Nordrhein-Westfalen. **Gilt nur, wenn der Betreiber seinen Sitz in NRW hat.** Sonst die Behörde des eigenen Bundeslandes eintragen. |
| `ki` | System, Anbieter, Modelle | Vorbelegt mit der tatsächlichen Herkunft (Claude, Anthropic PBC). |
| `software` | Version, Stand, APK-Fingerabdruck | Bei jeder neuen Version anpassen. Der Fingerabdruck steht im LIES-MICH der Version. |

## Checkliste vor dem Veröffentlichen

- [ ] Alle Pflichtfelder echt ausgefüllt (der Bau prüft das), E-Mail wird regelmäßig gelesen, Telefon oder zweiter Weg erreichbar.
- [ ] Impressum, Datenschutzerklärung und Haftungstext von einer fachkundigen Person gegengelesen.
- [ ] Auftragsverarbeitungsvertrag mit dem Hoster abgeschlossen; `logfiles_tage` und `ip_kuerzen` entsprechen dem Server.
- [ ] Entscheidung über die Lizenz getroffen und im Quellcode (LICENSE-Datei) und in den Paketen hinterlegt.
- [ ] `gemeinnuetzig_anerkannt` nur mit Bescheid auf `true`.
- [ ] Bei Spenden oder anderen Einnahmen: steuerliche und produkthaftungsrechtliche Folgen klären (siehe unten).
- [ ] `python build.py` ohne Fehler, `python -m pytest tests -q` grün, Seite einmal selbst auf Handy und Rechner angesehen.

## Was die Website rechtlich kann und was nicht

- **Kein Text kann jede Haftung ausschließen.** Nach deutschem Recht bleibt die Haftung bei Vorsatz, grober Fahrlässigkeit,
  Verletzung von Leben, Körper oder Gesundheit, Arglist, übernommenen Garantien und nach dem Produkthaftungsgesetz bestehen.
  Der Haftungstext sagt das offen, beruft sich auf die unentgeltliche Überlassung (§§ 521, 599 BGB: nur Vorsatz und grobe
  Fahrlässigkeit) und schließt nur **einfache Fahrlässigkeit „soweit gesetzlich zulässig“** aus. Der Baukasten lehnt Sätze
  wie „jede Haftung ist ausgeschlossen“ ab, weil sie unwirksam wären und die Seite angreifbar machen.
- „Niemals schaden wollen“ steht ausdrücklich auf der Seite. Das ersetzt keine Haftungsregeln, zeigt aber die Haltung.
- **KI als Hersteller:** Das Impressum sagt, dass die Software von einer KI hergestellt wurde. Rechtlich ist die KI keine Person;
  Anbieter und Ansprechpartner ist der Betreiber der Website. Das steht dort so. Anthropic wird nur als Herkunft genannt und
  ausdrücklich nicht als Betreiber oder Empfehler.
- **DSGVO:** Die Website braucht keine Einwilligung (keine Cookies, kein Tracking, keine Fremdressourcen). Verarbeitet werden
  nur Server-Protokolle beim Hoster und E-Mails an euch. Die Erklärung nennt Zwecke, Rechtsgrundlagen, Fristen, Rechte und
  die Aufsichtsbehörde.
- **Produkthaftung / EU-Recht:** Die neue EU-Produkthaftungsrichtlinie nimmt freie Software aus, die außerhalb einer
  Geschäftstätigkeit bereitgestellt wird. Wer Spenden einnimmt oder Dienstleistungen verkauft, kann diese Ausnahme verlieren.
  Das ist hier nicht abschließend geklärt; im Zweifel beraten lassen.

## Neue Version der Software veröffentlichen

1. Neue Dateien und `SHA256SUMS-<Version>.txt` in den Release-Ordner legen.
2. `config.json`: `software.version`, `software.stand`, `software.apk_zertifikat_sha256` und `seite.stand` anpassen.
3. In `site/daten/downloads.json` den **Prüfstand jeder Datei ehrlich** anpassen (`getestet`, `gebaut`, `teils`). Die Seite zeigt ihn
   neben jedem Download. Eine Datei, die nie auf echter Hardware lief, bleibt als solche gekennzeichnet.
4. `python build.py --dateien-kopieren`, prüfen, hochladen.

## Tests

`python -m pytest tests -q` (72 Prüfungen der Seiten, 17 gegen einen echten nginx):

- Baukasten: Pflichtfelder, Platzhalter, widersprüchliche Angaben, beschädigte oder fehlende Download-Dateien.
- Inhalte: Impressum mit KI-Herstellerangabe, Haftungstext ohne absolute Floskeln, Datenschutz-Pflichtbestandteile.
- Technik: gültiges HTML, strenge Inhaltsrichtlinie, keine Fremdadressen, alle Links und Anker, Kontraste (WCAG),
  echter HTTP-Server ohne Cookies.
- Browser (`tests/browser_check.py`, braucht Playwright + Chromium): Handy, Tablet, Desktop, hell und dunkel; kein
  waagerechtes Scrollen, keine Fremdanfragen, Tastaturbedienung.
- Server (`tests/test_server.py`, braucht nginx und openssl): Syntax, Kopfzeilen, nur Lesezugriff, IP-Kürzung, Downloads.
- Die APK-Prüfsumme der Seite wird gegen die echte APK mit `apksigner` verglichen, wenn beides vorhanden ist.

**Was kein Test leisten kann:** Ob die rechtlichen Texte vor Gericht tragen, und wie sich euer konkreter Hoster verhält. Die
Tests nutzen erfundene Betreiberdaten (`Bienenschutz Teststand`, `*.invalid`) und Testattrappen als Download-Dateien; beides
steckt nur in `tests/`, nie im Ergebnis.

## Dateien

```
build.py              Baukasten und Prüfer
config.json           Eure Angaben (zunächst leer)
site/seiten/          Seitentexte (Start, Download, Anleitung, Hinweise, Gemeinwohl, Haftung, Datenschutz, Impressum, Lizenzen, 404)
site/teile/           Kopf und Fuß
site/assets/          Gestaltung, Logo, Schriften (Bitter, Atkinson Hyperlegible, jeweils SIL OFL 1.1)
site/daten/           Download-Liste mit Prüfstand
server/               nginx- und logrotate-Beispiel
tests/                Tests (nur diese enthalten erfundene Testdaten)
```
