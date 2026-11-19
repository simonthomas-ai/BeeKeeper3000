# Sicherheit (Hornet3000 1.3.0)

## Was geschützt wird und wovor

Das Programm läuft im Heimnetz oder auf einem kleinen Server, hat eine Kamera mit Bildern vom Grundstück und kann Nachrichten
verschicken. Geschützt werden: Zugang zur Oberfläche, die Zugangsdaten der Meldewege (Telegram-Token, SMS usw.), die Bilder,
und das Funknetz vor Fremdtext und Überflutung.

## Maßnahmen

**Zugang**
* Ein langer Zugangsschlüssel wird beim ersten Start zufällig erzeugt. Alle Vergleiche laufen in konstanter Zeit.
* Anmeldung per Cookie (httpOnly, SameSite=Lax, bei https `Secure`); Fehlversuche je Adresse begrenzt (10 pro 10 Minuten).
* Freigabe-Links für einzelne Alarme sind signiert und laufen ab.

**Schutz vor Angriffen über den Browser (Webguard)**
* Schreibende Anfragen und WebSockets werden nur von der eigenen Seite angenommen (Origin- und `Sec-Fetch-Site`-Prüfung):
  eine fremde Webseite kann im Browser des Imkers nichts auslösen. Im echten Browser nachgestellt und geprüft.
* Strenge Inhaltsrichtlinie (CSP): Skripte und Stile nur aus dem Programm selbst, keine Inline-Skripte, `frame-ancestors 'none'`,
  `nosniff`, kein Referrer.
* Anfragegröße begrenzt (1 MiB); ungültiges JSON ergibt eine saubere Fehlermeldung statt eines Absturzes.

**Daten**
* Einstellungsdatei `.env` nur für den Besitzer lesbar (0600), Datenordner 0700.
* SQL ausschließlich mit Parametern; dynamische Spaltennamen nur aus fester Positivliste.
* Eingaben der Einrichtung werden vor dem Speichern geprüft (Port, Adresse, Namen, Schlüssel, Zahlenbereiche); Zeilenumbrüche
  oder Zusatzwerte lassen sich nicht in die `.env` einschleusen. Als Funkanschluss sind nur echte serielle Geräte erlaubt.
* Externe Programme (ffmpeg, riverctl) werden nie über eine Shell aufgerufen; Kamera-Quellen und Namen, die wie eine Option
  aussehen (mit „-“ beginnen) oder Zeilenumbrüche enthalten, werden abgelehnt.

**Funknetz**: siehe `FUNKNETZ.md` – striktes Format, Bereinigung, Mengenbegrenzung, begrenzte Warteschlangen.

**Altgeräte-Station und Handy-Seite (neu in 1.3.0, Einzelheiten in `MOBIL.md`)**
* Der Bildeingang `POST /api/station/frame` ist ein neuer Netzwerk-Eingang und verlangt wie alles den Zugangsschlüssel
  (Cookie oder `Authorization: Bearer`). Falsche Schlüssel per Bearer werden wie Anmeldeversuche gezählt: nach 10 in
  10 Minuten antwortet der Wächter dieser Adresse mit 429 – **auch auf richtige Schlüssel von derselben Adresse**, bis die Frist
  abgelaufen ist (Grenze 2 oben gilt entsprechend).
* Jedes Bild wird geprüft, **bevor** es jemand dekodiert: JPEG-Kennung, lesbarer Kopf, höchstens 4096 Pixel je Seite und
  8 Megapixel (Schutz vor „Dekompressionsbomben“), Farbmodus RGB/Graustufen; größer als 1 MiB wird schon vom Webguard abgewiesen.
* Höchstens 5 Bilder pro Sekunde (sonst 429 mit Wartezeit), nur **eine** Station aktiv (andere bekommen 409, bis die aktive
  20 s schweigt), Clip-Puffer nach Alter und nach Bytes (24 MiB) begrenzt. Der Stationsname wird auf einfache Zeichen begrenzt.
* Foto-Prüfung (`/api/mobile/check`): nur eine Auswertung gleichzeitig, löst nie einen Alarm aus.
* Die Handy-Seite `/m` setzt Texte vom Wächter nur mit `textContent` ein und hält die strenge Inhaltsrichtlinie ein; der Schlüssel
  aus einem QR-Link (`/m#k=…`) steht hinter dem `#` und geht nie an den Server oder in dessen Protokoll.
* Die Android-App folgt keinen Weiterleitungen (der Schlüssel geht nie an Dritte), begrenzt Antworten in der Größe, hält den
  Schlüssel aus Fehlermeldungen heraus und kann bei https das Zertifikat per SHA-256-Fingerabdruck festlegen. Der Schlüssel liegt im
  privaten App-Speicher (Cloud-Datensicherung aus), nicht zusätzlich verschlüsselt.
* Der Download der App (`/mobil/hornet3000-station.apk`) verlangt Anmeldung und liefert nur diese eine feste Datei. Die APK ist
  mit dem Schlüssel des Projekts signiert; wer den Schlüsselspeicher besitzt, kann Updates signieren – sicher aufbewahren.
* Geprüft: Pytest (Bildprüfung, Grenzen, Schlüssel-Sperre, Download), 104 Java-Prüfungen der App-Logik gegen den echten Wächter, echter
  Browser, und ein Dauerlauf, in dem eine ehrliche Station neben mehreren Störern (Müll, Übergröße, fremde Stationen, Fluten) Bilder
  liefert (Phase D von `tests/stability/soak.py`). **Nicht** geprüft: Verhalten auf echten Altgeräten.

## Bewusste Grenzen – bitte beachten

1. **Standard ist „im Heimnetz erreichbar“** (`HOST=0.0.0.0`), geschützt nur durch den Zugangsschlüssel. Nicht ohne
   HTTPS (z. B. über einen Reverse-Proxy) ins offene Internet stellen. Nur für den Rechner selbst: `HOST=127.0.0.1`.
2. Hinter einem Reverse-Proxy sieht das Programm nur dessen Adresse: die Sperre nach Fehlversuchen gilt dann für alle gemeinsam.
3. Es gibt keine Prüfung des Host-Namens in der Anfrage. DNS-Rebinding wird durch die Cookie-Bindung an den Host und den
   Zugangsschlüssel abgefangen, nicht durch eine Namensliste.
4. Funknetz: gemeinsames Geheimnis, keine Einzelsignatur der Stationen (siehe `FUNKNETZ.md`).
5. Die mitgelieferten Programmbibliotheken sind zum Bauzeitpunkt auf bekannte Schwachstellen geprüft; neue Meldungen kommen
   danach. Bei einem Update der Programmdateien (Update-Paket) bleiben Einstellungen und Daten erhalten.
