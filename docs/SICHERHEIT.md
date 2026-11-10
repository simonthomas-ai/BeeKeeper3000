# Sicherheit (Hornet3000 1.2.0)

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

## Bewusste Grenzen – bitte beachten

1. **Standard ist „im Heimnetz erreichbar“** (`HOST=0.0.0.0`), geschützt nur durch den Zugangsschlüssel. Nicht ohne
   HTTPS (z. B. über einen Reverse-Proxy) ins offene Internet stellen. Nur für den Rechner selbst: `HOST=127.0.0.1`.
2. Hinter einem Reverse-Proxy sieht das Programm nur dessen Adresse: die Sperre nach Fehlversuchen gilt dann für alle gemeinsam.
3. Es gibt keine Prüfung des Host-Namens in der Anfrage. DNS-Rebinding wird durch die Cookie-Bindung an den Host und den
   Zugangsschlüssel abgefangen, nicht durch eine Namensliste.
4. Funknetz: gemeinsames Geheimnis, keine Einzelsignatur der Stationen (siehe `FUNKNETZ.md`).
5. Die mitgelieferten Programmbibliotheken sind zum Bauzeitpunkt auf bekannte Schwachstellen geprüft; neue Meldungen kommen
   danach. Bei einem Update der Programmdateien (Update-Paket) bleiben Einstellungen und Daten erhalten.
