# Hornet3000 – Website zum Anbieten der Software an Imkerinnen und Imker

Eine rein statische Website (nur HTML und CSS, **kein JavaScript, keine Cookies, keine Fremdinhalte**), über die ihr
Hornet3000 Wächter unentgeltlich anbietet. Sie nennt das Gemeinwohl als Ziel, enthält einen Haftungsausschluss, eine
Datenschutzerklärung nach DSGVO und ein Impressum, das offenlegt, dass die Software von einer KI hergestellt wurde.

Der Baukasten (`build.py`, nur Python-Standardbibliothek) setzt die Seiten aus euren Angaben zusammen und **weigert sich,
eine Website zu erzeugen, solange Pflichtangaben fehlen oder nach Platzhaltern aussehen.** Es gibt keine erfundenen
Beispieldaten im Ergebnis.

> **Wichtig:** Das hier ist technische Vorarbeit und kein Rechtsrat. Die Texte sind sorgfältig am deutschen Recht
> ausgerichtet, aber ich bin keine Anwältin und kein Anwalt. Lasst Impressum, Datenschutz und Haftungstext einmal von
> einer fachkundigen Person prüfen (Verbraucherzentrale, Rechtsanwalt, Verein mit Rechtsberatung), bevor ihr online geht.
> Einen vollständigen Haftungsausschluss kann kein Text bewirken (siehe unten).

## Schnellstart

1. **Ansehen:** `python build.py --vorschau` erzeugt `vorschau/`. Fehlende Angaben sind rot markiert, auf jeder Seite
   steht „VORSCHAU – nicht veröffentlichen“. Öffnet `vorschau/index.html` im Browser (in Chromium getestet). Erscheint die
   Seite ungestaltet, startet einen lokalen Server: `python -m http.server -d vorschau` und öffnet `http://localhost:8000`.
2. **Ausfüllen:** `config.json` bearbeiten. `python build.py --felder` erklärt jedes Feld.
3. **Dateien bereitstellen:** Release-Ordner mit den Installern und `SHA256SUMS-<Version>.txt`. Den Ordner in
   `downloads.quelle_ordner` eintragen (auch wenn die Dateien später woanders liegen: die Prüfsummen werden immer geprüft).
4. **Bauen:** `python build.py --dateien-kopieren` erzeugt `public/`. Der Bau bricht mit einer lesbaren Liste ab, wenn
   etwas fehlt, widersprüchlich ist oder eine Prüfsumme nicht stimmt.
5. **Hochladen:** bei Google Firebase Hosting (nächster Abschnitt) oder auf einen eigenen Server (nginx-Beispiel in `server/`).

## Hosting bei Google (Firebase Hosting)

Firebase Hosting liefert statische Seiten über Googles weltweites Netz aus, mit https. Das ist für diese Website gut geeignet.
Die Datei `firebase.json` im Hauptordner setzt dieselben Sicherheits-Kopfzeilen wie das nginx-Beispiel und ist an Googles
Hosting-Emulator getestet (nicht am echten Dienst, siehe „Nach dem Hochladen prüfen“).

**Was Google dafür vorgibt** (laut Googles Dokumentation, Stand Herbst 2026; bitte vor dem Start selbst nachsehen):

- Kostenlos (Spark-Tarif): 10 GB gespeicherte Dateien, **10 GB Datenmenge pro Monat**, höchstens 2 GB je Datei.
  **Ist die Datenmenge verbraucht, wird die gesamte Seite bis zum nächsten Monat abgeschaltet**, also auch Impressum und
  Datenschutzerklärung (Google nennt eine kurze Schonfrist). Eure Installer sind je 25 bis 139 MB groß, zusammen etwa 520 MB.
  Ein einzelner Download kostet 87 bis 139 MB, also reichen die 10 GB für etwa 100 bis 120 Downloads im Monat.
- **Empfehlung:** Die Seite selbst (unter 1 MB) bei Firebase, die großen Installer als „Release“ bei GitHub (kostenlos, ohne
  Monatsgrenze). Dann in `config.json`: `downloads.basis_url` auf die Release-Adresse (`https://github.com/<Organisation>/<Repo>/releases/download/v<Version>/`),
  dazu `downloads.anbieter` (Name, Anschrift und Datenschutz-Adresse **so, wie GitHub sie in seiner Datenschutzerklärung angibt**).
  Die Datenschutzerklärung der Website beschreibt dann automatisch, dass Downloads vom anderen Anbieter kommen. Legt dafür eine
  GitHub-Organisation mit neutralem Namen an, sonst steht euer persönlicher GitHub-Name in jeder Download-Adresse.
- Wer alles bei Google lassen will: `downloads.basis_url` bleibt `downloads/`. Dann sind die Installer Teil der Seite und
  zählen auf die 10 GB. Beobachtet den Verbrauch in der Firebase-Konsole.

**Schritte:**

1. In der Firebase-Konsole ein Projekt anlegen (Spark-Tarif). Die Projekt-ID wird Teil der Adresse `https://<projekt-id>.web.app`:
   neutral wählen, ohne Personennamen. Diese Adresse kostet nichts; eine eigene Domain kostet extra und ist nicht nötig.
2. **Auftragsverarbeitung:** Google erklärt, dass es für Firebase-Dienste Auftragsverarbeiter ist („Firebase Data Processing
   and Security Terms“, Stand 21.08.2024). Diese Bedingungen gelten laut Google nicht von selbst, sondern nur, wenn der
   Dienstvertrag auf sie verweist. **Prüft in eurem Konto, dass sie gelten bzw. angenommen sind**, und setzt erst dann
   `website.avv_abgeschlossen` auf `true`.
3. **Vertragspartner eintragen:** `website.hoster_name` und `hoster_anschrift` müssen der Google-Gesellschaft entsprechen, die in
   euren Bedingungen steht. Für Geschäftskunden in Deutschland nennt Google bei kostenpflichtigen Diensten *Google Ireland Limited,
   Gordon House, Barrow Street, Dublin 4, Irland* (Googles Übersicht, Fassung von 2021). Für den kostenlosen Tarif bitte in
   den Bedingungen nachsehen und nichts annehmen.
4. **Cloud Logging nicht mit Hosting verbinden.** Google protokolliert jeden Aufruf (unter anderem IP-Adresse, Browserkennung);
   Einträge sehen und speichern könnt ihr nur, wenn ihr Hosting mit Cloud Logging verbindet (dann 30 Tage Aufbewahrung, wenn
   nicht anders eingestellt). Ohne diese Verbindung stimmt der Satz „Wir speichern keine Protokolle und haben keinen Zugriff
   auf einzelne Einträge“. Habt ihr es verbunden, stellt um: `protokolle: "selbst"`, `logfiles_tage: 30`, `ip_kuerzen: false`.
5. Angaben in `config.json` für Google (Beispielwerte; Hoster-Name und -Anschrift nach Schritt 3):

   ```json
   "website": {
     "adresse": "https://<projekt-id>.web.app",
     "hoster_name": "…", "hoster_anschrift": "…",
     "hoster_land": "weltweit verteilt (Content-Delivery-Netz), Verwaltung in Irland",
     "avv_abgeschlossen": true,
     "protokolle": "hoster",
     "hoster_datenschutz_url": "https://firebase.google.com/support/privacy",
     "hoster_drittland": true,
     "hoster_drittland_grundlage": "Angemessenheitsbeschluss der EU-Kommission (EU-US Data Privacy Framework, Google ist zertifiziert) und, soweit nötig, Standardvertragsklauseln",
     "logfiles_tage": null, "ip_kuerzen": null
   }
   ```
   Googles Datenschutz-Angaben sagen, dass Hosting „weltweit“ verarbeitet wird (Firebase kann Daten überall verarbeiten, wo
   Google Einrichtungen hat) und dass Google dem EU-US Data Privacy Framework beigetreten ist. Das Rahmenwerk ist politisch
   und gerichtlich umstritten; die Erklärung nennt daher auch die Standardvertragsklauseln.
6. `python build.py --dateien-kopieren` (bei GitHub-Downloads ohne Kopieren: `python build.py`).
7. Hochladen: `npm install -g firebase-tools`, `firebase login`, im Hauptordner `firebase use --add` (Projekt wählen), dann
   `firebase deploy --only hosting`.

**Nach dem Hochladen prüfen** (das kann der Emulator nicht): `curl -sI https://<projekt-id>.web.app/` zeigt die Kopfzeilen.
Erwartet: `content-security-policy`, `x-content-type-options`, `referrer-policy`, **kein** `set-cookie`. Ruft Impressum,
Datenschutz und Download auf dem Handy auf.

## Ohne Person im Impressum: was geht und was nicht

Ein Freistellungsbescheid gilt für eine Körperschaft (Verein, gGmbH, Stiftung). Damit ist der Betreiber **die Organisation**, nicht
eine Einzelperson. Das hilft, aber nicht vollständig:

- Im Impressum stehen der Name der Organisation (wie im Freistellungsbescheid), die Rechtsform, die ladungsfähige Anschrift
  und Kontaktwege. **Für juristische Personen verlangt § 5 DDG zusätzlich den Namen einer vertretungsberechtigten Person**
  (bei einem Verein: ein Vorstandsmitglied). Ganz ohne Namen geht das nicht. Es genügt eine Person, und es muss nicht die sein,
  die die Software betreut. Eintragen unter `betreiber.vertretungsberechtigt`.
- **Anschrift:** Vereinssitz oder Geschäftsstelle. Wenn der Verein keine eigene Anschrift hat, wäre es die eines Vorstands.
- **E-Mail:** eine eigene, neutrale Adresse der Organisation anlegen. Eine private Adresse mit Klarnamen verrät die Person im Impressum.
  Liegt das Postfach bei Google (Gmail), tragt das unter `betreiber.email_anbieter` ein; die Datenschutzerklärung nennt es dann.
  Für die Organisation ist ein kostenloses Google-Workspace-Konto für gemeinnützige Organisationen eine Alternative (Googles
  Angebot „Google Workspace for Nonprofits“, Voraussetzung ist die Zulassung bei Google for Nonprofits; ob und wie das für
  Deutschland gilt, steht in Googles Beschreibung und war für mich nicht prüfbar).
- **Zweiter Kontaktweg:** Telefon oder zum Beispiel ein Kontaktweg per Post (`kontakt_alternative`), nicht zwingend eine Privatnummer.
- Google sieht, wer das Firebase-Konto führt. Auf der Website erscheint das nicht.
- **In der Software selbst** habe ich in Code, Metadaten und dem Zertifikat der Android-App nach Personennamen gesucht und
  keine gefunden (das Zertifikat nennt nur „Hornet3000 Station“ und „Hornet3000 Imker-Initiative“). Der Urhebervermerk lautet
  „Hornet3000-Mitwirkende“.

## Was ihr selbst eintragen müsst (`config.json`)

| Bereich | Felder | Hinweis |
|---|---|---|
| `betreiber` | Name, Rechtsform, **ladungsfähige Anschrift**, E-Mail, zweiter Kontaktweg | § 5 DDG. Ein Postfach genügt nicht. |
| `betreiber` | `vertretungsberechtigt`, `register`, `registernummer` | Pflicht bei e. V., GmbH, UG usw. |
| `betreiber` | `gemeinnuetzig_anerkannt` (vorbelegt mit `true`), `gemeinnuetzig_nachweis` | Ihr habt einen Freistellungsbescheid. Tragt Finanzamt und Datum ein, z. B. „Freistellungsbescheid des Finanzamts … vom …“. Der Bescheid muss **aktuell** sein. Ohne gültigen Bescheid zurück auf `false`. |
| `website` | `adresse`, `hoster_*`, `avv_abgeschlossen`, `protokolle`, `hoster_drittland*` | Siehe Abschnitt Google. |
| `website` | `logfiles_tage`, `ip_kuerzen` | Nur bei `protokolle: "selbst"` (eigener Server). Sie müssen zur Server-Einstellung passen. |
| `lizenz` | vorbelegt: `GPL-3.0-or-later` | Siehe Lizenz. |
| `aufsicht` | Behörde | Vorbelegt mit der LDI Nordrhein-Westfalen. **Gilt nur, wenn die Organisation ihren Sitz in NRW hat.** |
| `ki` | System, Anbieter, Modelle | Vorbelegt mit der tatsächlichen Herkunft (Claude, Anthropic PBC). |
| `software` | Version, Stand, APK-Fingerabdruck | Bei jeder neuen Version anpassen. |

## Lizenz: alles frei und kostenlos

Alles steht unter der **GNU General Public License, Version 3 oder neuer (GPL-3.0-or-later)**: Programmcode, Baukasten, Texte,
Gestaltung. Jede und jeder darf es kostenlos nutzen, ändern und weitergeben, auch andere Imker-Initiativen, solange Weitergaben
unter denselben Bedingungen erfolgen (Copyleft). Der Lizenztext liegt in `LICENSE`; die Quelltexte tragen die Kennung
`SPDX-License-Identifier: GPL-3.0-or-later`. Die Schriften (Bitter, Atkinson Hyperlegible) behalten ihre eigene Lizenz (SIL OFL 1.1).

Warum GPL: Das Erkennungsmodell steht unter GPL-3.0 und ffmpeg wird als GPL-Build mitgeliefert. Die GPL passt dazu und
hält die Software auf Dauer frei.

Zwei Dinge, die ihr wissen solltet (keine Rechtsberatung):

- **Urheberrecht an KI-Ergebnissen ist ungeklärt.** Nach deutschem Recht schützt das Urheberrecht „persönliche geistige
  Schöpfungen“ von Menschen. Rein von der KI erzeugte Teile sind womöglich gar nicht geschützt; die Lizenz wirkt dann nur für
  Teile mit eigenem menschlichem Beitrag. Das schadet der freien Nutzung nicht.
- **Rechteinhaber:** Damit nicht eine Einzelperson als Inhaberin gilt, sollte die Person, die die Software gestaltet und
  angeleitet hat, dem Verein die Nutzungsrechte schriftlich einräumen (ein Satz genügt, am besten mit Vorstandsbeschluss).

**Noch offen:** Die bereits gebauten Installer der Version 1.3.0 enthalten den Lizenztext der eigenen Software noch nicht.
Vor der Veröffentlichung sollte eine Fassung 1.3.1 mit `LICENSE` in allen Paketen erscheinen (siehe Software-Repository).

## Checkliste vor dem Veröffentlichen

- [ ] Alle Pflichtfelder echt ausgefüllt (der Bau prüft das), E-Mail wird regelmäßig gelesen.
- [ ] Freistellungsbescheid aktuell; Finanzamt und Datum eingetragen.
- [ ] Impressum, Datenschutzerklärung und Haftungstext von einer fachkundigen Person gegengelesen.
- [ ] Bei Google: Auftragsverarbeitungs-Bedingungen im Konto geprüft, Vertragspartner richtig eingetragen, Cloud Logging **nicht** verbunden.
- [ ] Installer-Version mit Lizenztext (1.3.1) gebaut, Prüfsummen und Prüfstand in `site/daten/downloads.json` stimmen.
- [ ] Nutzungsrechte beim Verein (siehe Lizenz).
- [ ] `python build.py` ohne Fehler, `python -m pytest tests -q` grün, nach dem Hochladen die Kopfzeilen geprüft.

## Was die Website rechtlich kann und was nicht

- **Kein Text kann jede Haftung ausschließen.** Nach deutschem Recht bleibt die Haftung bei Vorsatz, grober Fahrlässigkeit,
  Verletzung von Leben, Körper oder Gesundheit, Arglist, übernommenen Garantien und nach dem Produkthaftungsgesetz bestehen.
  Der Haftungstext sagt das offen, beruft sich auf die unentgeltliche Überlassung (§§ 521, 599 BGB: nur Vorsatz und grobe
  Fahrlässigkeit) und schließt nur **einfache Fahrlässigkeit „soweit gesetzlich zulässig“** aus. Der Baukasten lehnt Sätze
  wie „jede Haftung ist ausgeschlossen“ ab, weil sie unwirksam wären und die Seite angreifbar machen.
- „Niemals schaden wollen“ steht ausdrücklich auf der Seite. Das ersetzt keine Haftungsregeln, zeigt aber die Haltung.
- **KI als Hersteller:** Das Impressum sagt, dass die Software von einer KI hergestellt wurde. Rechtlich ist die KI keine Person;
  Anbieter und Ansprechpartner ist die Organisation. Anthropic wird nur als Herkunft genannt und ausdrücklich nicht als Betreiber oder Empfehler.
- **DSGVO:** Die Website braucht keine Einwilligung (keine Cookies, kein Tracking, keine Fremdressourcen). Verarbeitet werden
  nur Server-Protokolle beim Hoster und E-Mails. Die Erklärung nennt Zwecke, Rechtsgrundlagen, Fristen, Empfänger, Drittlandübermittlung,
  Rechte und die Aufsichtsbehörde.
- **Gemeinnützigkeit:** Die Seite nennt sich nur dann „als gemeinnützig anerkannt“, wenn `gemeinnuetzig_anerkannt` wahr ist und
  ein Nachweis eingetragen ist. Sonst sagt sie „ohne Gewinnabsicht“.
- **Produkthaftung / EU-Recht:** Die neue EU-Produkthaftungsrichtlinie nimmt freie Software aus, die außerhalb einer
  Geschäftstätigkeit bereitgestellt wird. Wer Spenden einnimmt oder Dienstleistungen verkauft, kann diese Ausnahme verlieren.
  Das ist hier nicht abschließend geklärt; im Zweifel beraten lassen.

## Neue Version der Software veröffentlichen

1. Neue Dateien und `SHA256SUMS-<Version>.txt` in den Release-Ordner legen.
2. `config.json`: `software.version`, `software.stand`, `software.apk_zertifikat_sha256` und `seite.stand` anpassen.
3. In `site/daten/downloads.json` den **Prüfstand jeder Datei ehrlich** anpassen (`getestet`, `gebaut`, `teils`). Die Seite zeigt ihn
   neben jedem Download. Eine Datei, die nie auf echter Hardware lief, bleibt als solche gekennzeichnet.
4. `python build.py --dateien-kopieren`, prüfen, hochladen (`firebase deploy --only hosting`).

## Tests

`python -m pytest tests -q`:

- Baukasten: Pflichtfelder, Platzhalter, widersprüchliche Angaben, beschädigte oder fehlende Download-Dateien, Hoster-Modi.
- Inhalte: Impressum mit KI-Herstellerangabe, Haftungstext ohne absolute Floskeln, Datenschutz-Pflichtbestandteile in beiden Hoster-Modi.
- Technik: gültiges HTML, strenge Inhaltsrichtlinie, keine Fremdadressen, alle Links und Anker, Kontraste (WCAG), HTTP ohne Cookies.
- Browser (`tests/browser_check.py`, braucht Playwright + Chromium): Handy, Tablet, Desktop, hell und dunkel.
- Server (`tests/test_server.py`, braucht nginx und openssl): Syntax, Kopfzeilen, nur Lesezugriff, IP-Kürzung, Downloads.
- Firebase (`tests/test_firebase.py`, braucht `firebase-tools`; Pfad in `FIREBASE_BIN`): `firebase.json` am lokalen Emulator.
- Die APK-Prüfsumme der Seite wird gegen die echte APK mit `apksigner` verglichen, wenn beides vorhanden ist.

**Was kein Test leisten kann:** Ob die rechtlichen Texte vor Gericht tragen, wie sich der echte Google-Dienst verhält (der
Emulator ist ein Nachbau) und was in euren Google-Bedingungen steht. Die Tests nutzen erfundene Betreiberdaten
(`Bienenschutz Teststand`, `*.invalid`) und Testattrappen als Download-Dateien; beides steckt nur in `tests/`, nie im Ergebnis.

## Dateien

```
build.py              Baukasten und Prüfer
config.json           Eure Angaben (Pflichtfelder zunächst leer)
firebase.json         Konfiguration für Firebase Hosting (Kopfzeilen)
LICENSE               GPL-3.0-or-later
site/seiten/          Seitentexte (Start, Download, Anleitung, Hinweise, Gemeinwohl, Haftung, Datenschutz, Impressum, Lizenzen, 404)
site/teile/           Kopf und Fuß
site/assets/          Gestaltung, Logo, Schriften (Bitter, Atkinson Hyperlegible, jeweils SIL OFL 1.1)
site/daten/           Download-Liste mit Prüfstand
server/               nginx- und logrotate-Beispiel (für einen eigenen Server)
tests/                Tests (nur diese enthalten erfundene Testdaten)
```

## Quellen (Googles Angaben, abgerufen im November 2026)

- Firebase Hosting, Kontingente und Preise: https://firebase.google.com/docs/hosting/usage-quotas-pricing
- Firebase Data Processing and Security Terms: https://firebase.google.com/terms/data-processing-terms
- Datenschutz und Sicherheit in Firebase: https://firebase.google.com/support/privacy
- Anfragen-Protokolle von Firebase Hosting: https://firebase.google.com/docs/hosting/web-request-logs-and-metrics
- Vertragspartner für Google Cloud nach Land (Fassung 2021): https://cloud.google.com/terms/google-entity
