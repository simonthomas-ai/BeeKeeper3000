# Alte Handys und Tablets nutzen (Hornet3000 1.3.0)

Ein ausrangiertes Handy oder Tablet kann für den Wächter **Kamera** sein, **Alarm-Anzeige** (Ton, Vibration, Bild der
Sichtung) oder beides nacheinander. Je älter das Gerät, desto eher geht das über die **Android-App**; iPhones nutzen eine
**Handy-Seite im Browser**. Die Erkennung läuft immer auf dem Wächter – das Altgerät muss nur Bilder liefern bzw. anzeigen.

> **Ehrlich vorweg:** Die Android-App wurde auf **keinem** Gerät und in **keinem** Emulator ausgeführt (es gab hier weder
> noch). Geprüft sind ihr Netzwerkteil gegen den echten Wächter, der Bau gegen die Android-2.2-Systembibliothek und die
> Signatur (Abschnitt 6). Kamera, Bildschirme und Ton sind nur gebaut und gelesen, nicht erprobt. Bitte die Checkliste in
> Abschnitt 5 einmal durchgehen und Ergebnisse zurückmelden.

## 1. Was läuft auf welchem Gerät?

**Android-App „Hornet3000 Station“** (Datei `Hornet3000-Station-1.3.0.apk`, rund 95 KB). Im Manifest steht Mindestversion
**Android 2.2 (API 8, 2010)**; der Quelltext wird gegen die Systembibliothek von Android 2.2 übersetzt, also kommen nur
Funktionen vor, die es dort gibt. Das ist eine **Berechnung aus der Bauprüfung, kein Test an einem echten Gerät**.

| Android | Kamera-Betrieb | Alarm-Anzeige | Verschlüsselung (https) | Besonderheiten |
|---|---|---|---|---|
| 2.2 (API 8) | möglich, nur die Standardkamera | möglich | nur unverschlüsselt (http) im eigenen Netz | Gerät kann nur TLS 1.0 |
| 2.3 – 4.0 (9–15) | möglich, Kamera wählbar | möglich | nur http | wie oben |
| 4.1 – 4.4 (16–19) | möglich | möglich | https mit Fingerabdruck möglich (TLS 1.2 wird von der App eingeschaltet) | |
| 5.0 – 5.1 (21–22) | möglich | möglich | https | |
| 6.0+ (23+) | möglich | möglich | https | Kamera-Erlaubnis wird beim ersten Start abgefragt |
| 9+ (28+) | möglich | möglich | https | Kamera nur im Vordergrund (Systemregel) – die Kameraansicht bleibt deshalb offen, Bildschirm bleibt an |
| 15+ (35+) | möglich | möglich | https | Installation setzt Zielversion ≥ 24 voraus; die App hat 28. Neueste Versionen können Warnhinweise zeigen |

**Handy-Seite `/m`** (Adresse des Wächters + `/m`, z. B. `http://192.168.1.20:8000/m`; reines ES5, keine Bibliotheken):

| Gerät / Browser | Alarm-Anzeige | Foto prüfen | Kamera-Betrieb |
|---|---|---|---|
| iPhone/iPad iOS 9 – 10 (iPhone 4S, 5, 5c; iPad 2 – 4) | ja (Ton erst nach einmal Tippen; Safari kann auf dem iPhone nicht vibrieren) | ja | **nein** – Safari kann die Kamera im Browser erst ab iOS 11 |
| iPhone/iPad iOS 11+ | ja | ja | ja, aber nur über **https**; die Seite muss im Safari-Tab vorn bleiben (als Home-Bildschirm-App funktioniert die Kamera auf alten iOS-Versionen nicht) |
| Android-Browser ab 4.0 | ja | ja | Chrome ab Version 47 verlangt https; ältere Browser erlauben http (nur lokal ausprobiert, siehe Abschnitt 6) |
| Android 2.x/3.x-Browser | nicht vorgesehen – bitte die App nehmen | | |

**Eine iPhone-App gibt es nicht.** Dafür bräuchte man einen Mac mit Xcode und ein Apple-Entwicklerkonto zum Signieren; beides
gab es hier nicht. Die Handy-Seite ist der Weg für iPhones. Sie lässt sich auf dem Gerät auch als Lesezeichen/„Zum
Home-Bildschirm“ ablegen (nur für die Alarm-Anzeige empfohlen).

## 2. Einrichtung in vier Schritten

1. **Wächter:** Einrichtung → Kamera → Knopf **„Altgerät als Station verwenden („push“)“** → unten speichern → Wächter neu
   starten. (Im Reiter „Live“ steht dann „wartet auf Bild“.) Das gilt nur für den Kamera-Betrieb; die Alarm-Anzeige geht mit
   jeder Kamera-Quelle.
2. **Zugangsschlüssel** bereithalten (steht beim Start im Programmfenster bzw. unter Einrichtung).
3. **Altgerät:**
   * *Android:* Im Browser des Geräts `http://ADRESSE:PORT/m` öffnen, anmelden, unten auf **„Android-App laden“** tippen,
     Datei öffnen und die Installation aus „Unbekannten Quellen“ erlauben (ab Android 8 pro App, davor eine Systemeinstellung).
     Geht der Browser-Weg nicht (sehr alte Geräte), die Datei `mobil/Hornet3000-Station.apk` aus dem Programmordner des Wächters
     per USB-Kabel, Speicherkarte oder Messenger übertragen. Dann App öffnen, Adresse und Schlüssel eintragen, **„Verbindung
     prüfen“**, dann **„Als Kamera starten“** oder **„Als Alarm-Anzeige starten“**.
   * *iPhone:* Safari öffnen, `…/m` aufrufen, Schlüssel eingeben. Kamera nur ab iOS 11 mit https, sonst Alarm-Anzeige/Fotoprüfung.
4. **Kontrolle:** Im Reiter „Live“ des Wächters erscheint die Station mit Namen und Bildern pro Sekunde.

Es ist immer **eine** Station gleichzeitig aktiv (sonst springt die Erkennung zwischen zwei Blickwinkeln). Eine zweite Station
bekommt die Meldung „andere Station aktiv“ und übernimmt automatisch, sobald die erste 20 Sekunden schweigt.

## 3. Was die Station macht (und was nicht)

* Sie schickt alle gut 3 Sekunden ein JPEG (Standard, einstellbar am Wächter), höchstens 5 Bilder pro Sekunde. Typisch sind
  30 – 80 KB je Bild, also etwa 0,1 – 0,25 MB/s – **nur im WLAN** nutzen, nicht im Mobilfunk-Datentarif.
* Die Auflösung wird auf höchstens etwa 800 Pixel Breite begrenzt: Das schont alte Geräte, und das Erkennungsmodell
  arbeitet ohnehin mit verkleinerten Bildern.
* Reißt die Verbindung ab, versucht die App es nach 1, 2, 4, 8 und dann alle 15 Sekunden wieder und meldet es in der
  Statuszeile. Ein falscher Schlüssel beendet den Betrieb mit klarer Meldung (sonst würde der Wächter die Adresse sperren).
* Die **Videoclips** zu einem Alarm entstehen aus den Einzelbildern (ohne Ton), mit geringerer Bildrate als bei einer
  richtigen Videokamera. Für genaue Bestimmung ist eine echte Kamera besser; das Altgerät ist ein Aufpasser, kein Studio.
* Die App läuft **nur im Vordergrund**: Bildschirm bleibt an (Gerät ans Ladekabel), „Display dunkel“ senkt nur die Helligkeit.
  Sperrt jemand den Bildschirm oder öffnet eine andere App, hört die Kamera auf (Systemregel, ab Android 9 ohnehin).

## 4. Praktische Hinweise für Altgeräte

* **WLAN:** Sehr alte Geräte können oft nur 2,4 GHz und WPA2 – der Router darf nicht „nur WPA3“ oder „nur 5 GHz“ sein.
* **Strom und Akku:** Alte Akkus können aufquellen. Gerät nicht in praller Sonne, nicht auf brennbarem Untergrund und nicht
  unbeaufsichtigt über Wochen laden, ohne regelmäßig nachzusehen. Ist der Akku abnehmbar und das Gerät hat eine Dauerstrom-
  möglichkeit, ist der Betrieb ohne Akku am sichersten. Bei aufgeblähtem Akku Gerät sofort vom Strom nehmen.
* **Uhr:** Alte Geräte ohne Netzzeit gehen oft falsch. Die App verlässt sich bei http nicht auf die Uhr; bei https mit
  Fingerabdruck wird sie ebenfalls nicht gebraucht (Abschnitt 6).
* **Schutz:** Kamera nur auf Köderstation/Flugloch richten, nicht auf Nachbars Grundstück oder Wege (Datenschutz).
* **Netz:** Schlüssel und Bilder laufen bei http **unverschlüsselt** durchs WLAN. Im eigenen, geschützten Heimnetz ist das
  üblich; über fremde Netze oder das Internet nur mit https (am besten mit dem Fingerabdruck des Zertifikats in der App).

## 5. Checkliste für den ersten Einsatz (bitte einmal durchgehen)

1. App installieren, öffnen, Adresse und Schlüssel eintragen, „Verbindung prüfen“ → grüner Text „Verbunden mit Wächter 1.3.0 …“.
2. „Als Kamera starten“ → Kamera-Erlaubnis erteilen → Vorschau erscheint, Statuszeile zeigt „Bilder gesendet“ wachsend.
3. Am Wächter, Reiter „Live“: Station mit Namen, Bilder pro Sekunde, Bild aktuell?
4. Gerät kurz aus dem WLAN nehmen und wieder einschalten → Statuszeile meldet Ausfall und geht von selbst weiter.
5. „Als Alarm-Anzeige starten“ auf einem zweiten Gerät, am Wächter „Testalarm“ → Ton, Vibration, Bild?
6. Notieren: Gerät, Android-Version, was ging, was nicht. Besonders: Absturz beim Start? Schwarze Vorschau? Falsch gedrehtes Bild?
   (Das Bild wird nicht gedreht: Das Gerät bitte mit der Kamera in Querformat aufstellen.)

## 6. Was geprüft wurde – und was nicht

| Prüfung | Wie | Ergebnis |
|---|---|---|
| Netzwerk- und Ablaufteil der App (reines Java: Client, Wiederholung, Alarm-Abfrage, JSON, TLS) | 104 Prüfungen in der JVM **gegen den echten Wächter** als eigenen Prozess: falscher Schlüssel, zweite Station (409), zu schnell (429), kaputte/zu große/falsche Bilder, Ausfall und Wiederkehr (TCP-Zwischenstück), Stationswechsel nach 20 s, Testalarm, Stumm, Bild der Meldung, **https mit Fingerabdruck** (richtig/falsch/fehlt); dazu ein absichtlich schlechter Server (Weiterleitung, übergroße oder kaputte Antwort) | bestanden |
| Dieselben Quelldateien wie in der APK | Das Prüfskript stellt sicher, dass sie kein `android.*` benutzen | bestanden |
| Bau gegen alte Android-Versionen | Übersetzung gegen die Systembibliotheken von Android 2.2, 2.3, 4.0 und 4.1: jede zu neue Funktion wäre ein Fehler | bestanden (nur Funktionen bis API 8) |
| APK-Aufbau | `aapt dump badging`: Mindestversion 8, Zielversion 28, Berechtigungen nur Internet/Kamera/Vibration; `apksigner verify`: Signatur v1 (SHA-1, für alte Geräte) + v2 + v3 gültig; `zipalign` geprüft; Dex-Format 035 | bestanden |
| Handy-Seite `/m` im echten Browser (Chromium) | 37 Prüfungen: Anmeldung, Station mit Testkamera, Foto-Auswertung, Alarm mit Ton, Stumm, 320 Pixel Breite, keine Inhaltsrichtlinien-Verstöße, App-Download; zweiter Durchgang mit **entfernten** modernen Funktionen (fetch, Promise, classList …) als *Nachbildung* alter Browser | bestanden |
| Server-Seite | 31 Tests: Bildprüfung, Begrenzungen, 409/429, Schlüssel-Sperre, Abfrage, Foto-Auswertung, Clip aus Einzelbildern, App-Download | bestanden |
| **Auf einem echten Altgerät oder Emulator** | – | **nicht geprüft** (Kamera-Vorschau, Gerätemarken, Bildschirmaufbau, Ton, Hintergrundverhalten) |
| **Echte alte iPhones/Android-Browser** | – | **nicht geprüft**; nur die Nachbildung im modernen Chromium |
| Fingerabdruck-https auf Android 4.1 – 4.4 | – | nur in der JVM geprüft; das Einschalten von TLS 1.2 auf diesen Versionen ist nicht an einem Gerät erprobt |

**Bekannte Grenzen:** (a) Der Schlüssel liegt im privaten App-Speicher des Geräts (Datensicherung in die Cloud ist
abgeschaltet), aber nicht zusätzlich verschlüsselt – ein Gerät mit Root-Zugriff kann ihn lesen. Bei Verlust: Schlüssel am
Wächter wechseln. (b) Kein Hintergrunddienst, keine Benachrichtigung bei geschlossener App. (c) Die App kann nicht auf
mehrere Wächter umschalten. (d) Das Bild wird nicht gedreht. (e) Kein Ton aus der Kamera.

## 7. App selbst bauen / mit eigenem Schlüssel signieren

Die App ist reine Java-Quelle (Ordner `android/`), gebaut **ohne Gradle**. Auf Debian/Ubuntu:

```
sudo apt install default-jdk-headless aapt apksigner zipalign dalvik-exchange android-sdk-platform-23
cd android
# optional (empfohlen): android.jar einer ALTEN Android-Version als LINT_JAR – dann ist jede zu neue Funktion ein Fehler
LINT_JAR=/pfad/zu/android-8/android.jar ./build.sh MEIN.keystore PASSWORTDATEI
```

Ohne Schlüsselspeicher erzeugt `build.sh` einen Wegwerf-Schlüssel (nur zum Ausprobieren). **Updates der App sind nur mit demselben
Schlüssel möglich** – den Schlüsselspeicher sicher aufheben (er gehört nicht ins Repository und nicht ins Quellcode-Paket). Wer die
App vom Wächter herunterladbar machen will, legt die APK als `mobil/Hornet3000-Station.apk` in den Programmordner.
Netzwerkteil prüfen: `python3 tests/android/run_protocol.py` (braucht `javac`, `openssl`, die Python-Umgebung des Wächters).
