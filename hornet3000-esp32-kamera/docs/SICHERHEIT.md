# Sicherheit der ESP32-Kamera

## Schutz

* **Zugangsschlüssel für alles außer dem Namensschild** (`/`): `/status`, `/jpg`, `/stream`, `/reboot`, `/factory-reset`. Vergleich in konstanter Zeit.
* **Sperre bei Fehlversuchen:** 5 falsche Schlüssel innerhalb 60 s sperren alle geschützten Zugriffe 60 s lang (Antwort 429). Das bremst Raten (Schlüssel ≥ 16 Zeichen).
* Schlüssel, WLAN-Name und -Passwort werden vor dem Speichern streng geprüft (Länge, erlaubte Zeichen); Anfragegrößen sind begrenzt (Einrichtung 600 Byte, Adresse/Abfrage 160 Byte).
* Einrichtungs-WLAN mit **zufälligem WPA2-Passwort** (12 Zeichen, ca. 59 Bit, aus dem Hardware-Zufallsgenerator, im Flash gespeichert), bei einer eingerichteten Kamera nur nach drei erfolglosen WLAN-Versuchen und höchstens 10 Minuten am Stück offen; eine nie eingerichtete Kamera bleibt im Einrichtungsmodus.
* Kein Fernzugriff von außen, kein Cloud-Dienst, keine Telemetrie; die Kamera baut selbst keine Verbindung ins Internet auf (außer der WLAN-Anmeldung).
* Selbstheilung: Wächterhund (30 s), Neustart bei WLAN-Verlust (5 min), Neustart nach 10 Kamerafehlern in Folge, Neustart bei zu wenig Speicher (< 20 kB), geplanter Neustart alle 7 Tage.

## Grenzen (bewusst oder technisch bedingt)

1. **Kein HTTPS.** Der Zugangsschlüssel (`?t=…`) wird im Klartext im Heimnetz übertragen und steht in der Adresse des Wächters.
   Wer im selben WLAN mitlesen kann, kann ihn sehen. Deshalb: eigenes WLAN/VLAN für Kameras, WLAN mit WPA2/WPA3, Schlüssel nicht wiederverwenden.
   Bei einer Funkstrecke ins Freie oder über Internet: nur durch einen VPN-Tunnel, **nie** den Port der Kamera ins Internet freigeben.
2. **Der Schlüssel liegt unverschlüsselt im Flash (NVS).** Wer die Platine in der Hand hat, kann Flash auslesen (Schlüssel, WLAN-Passwort). Flash-Verschlüsselung und Secure Boot sind **nicht** eingerichtet.
   Gilt auch für das Einrichtungs-Passwort. Bei Verlust der Kamera: Schlüssel und WLAN-Passwort ändern.
3. **Die Sperre ist global, nicht je Absender.** Wer im WLAN 5 falsche Schlüssel schickt, sperrt die Kamera für 60 s auch gegen den Wächter (Dienst-Verweigerung). Wer im WLAN ist, kann die Kamera aber ohnehin überlasten oder stören.
4. **Keine Funkaktualisierung (OTA).** Neue Firmware nur per Kabel. Das verhindert Fremdsoftware über das Netz, heißt aber auch: Sicherheitskorrekturen brauchen einen Besuch.
5. **Ein Zuschauer.** Wer den Strom belegt, blockiert den Wächter (er erholt sich nach Trennung von selbst). Der Schutz davor ist der Schlüssel.
6. **Einrichtung ohne Bestätigung am Gerät.** Wer, solange das Einrichtungs-WLAN offen ist, das Passwort kennt (oder die Konsole mitliest), kann die Kamera umkonfigurieren. Darum das Passwort geheim halten und die Konsole nicht im Freien offen lassen.
7. mDNS (`hornet-cam-xxxx.local`) macht die Kamera im Netz sichtbar (Name, IP).

## Was bei der Prüfung auffiel (und behoben ist)

* Beim Fuzzing der Abfrage-Auswertung blieb bei ungültiger Prozent-Kodierung ein halb dekodierter Schlüssel im Ausgabepuffer (`t=GEHEIM%zz` ergab „abgelehnt“, aber der Rest „GEHEIM“ stand im Puffer). Jetzt wird der Ausgabepuffer bei jedem Fehler geleert und der Aufrufer setzt zusätzlich zurück; Regressionstests sind enthalten.
* Das Passwort des Einrichtungs-WLANs war zunächst aus der MAC-Adresse abgeleitet und damit für jeden in Funkreichweite berechenbar. Ersetzt durch ein zufälliges, gespeichertes Passwort.
* Im Hornet3000-Server stand die komplette Kamera-Adresse (mit `?t=Schlüssel` bzw. Benutzer:Passwort bei RTSP-Kameras) in ffmpeg-Fehlertexten und damit im Status und in Telegram-Statusantworten. Jetzt geschwärzt, mit Tests.
