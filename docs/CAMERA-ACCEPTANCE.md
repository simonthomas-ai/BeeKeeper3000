# Abnahmeprotokoll für Kamera und Erkennungsmodell

**Status: Noch keine Abnahme auf echter Hardware.** Die lokale Verarbeitungskette ist ein ausführbarer Softwareadapter. Damit ist weder die Funktion einer bestimmten Kamera oder eines RTSP-Streams noch die Qualität eines Modells nachgewiesen.

## 1. Konfiguration und Herkunftsprüfung
Vor dem Kamerastart:
- Hersteller/Modell, Firmware, Verbindungstyp, Auflösung, Bildrate und rein lokalen oder externen Streamzugriff dokumentieren.
- Herkunfts-URL des ONNX-Modells, unveränderliche Version/Commit, Datei-SHA-256, SPDX-Lizenz, Weitergabebedingungen für Gewichte, Herkunft des Trainingsdatensatzes und Lizenzen sämtlicher Bilder/Annotationen dokumentieren.
- Abgeschlossene Lizenzprüfung im lokalen Modellmanifest bestätigen. Die Codelizenz eines Repositories gilt nicht automatisch für Gewichte oder Bilder.
- Tensor-Namen, Eingabedimensionen, Farben, Layout, Normalisierung und Bedeutung der Ausgaben anhand der **konkreten ONNX-Datei** prüfen. Ausgaberechtecke müssen normalisierte `xyxy`-Koordinaten nach NMS sein; Konfidenzwerte zwischen 0 und 1 liegen; Klassen-IDs müssen dokumentierten Bezeichnungen entsprechen.
- Modelle und Manifeste außerhalb des öffentlichen Repositories speichern, sofern die Weitergabelizenz dies nicht ausdrücklich erlaubt.

## 2. Prüfung der Bildaufnahme
Der Netzwerk-/Dateiadapter fordert über das FFmpeg-Backend von OpenCV jeweils fünf Sekunden Zeitlimit für Öffnen und Lesen an. Die tatsächliche OpenCV-Version und das Backend dokumentieren; Verhalten mit der vorgesehenen Kamera-Firmware messen. Eine konfigurierte Zeitbegrenzung ersetzt keinen echten Trennungs- und Wiederverbindungstest.

Eine eigene Teststation und ein Kamerakonto ohne Produktionsrechte verwenden. Typische Tag-/Nachtbedingungen und schwierige Situationen aufnehmen: Bewegungsunschärfe, Regen, Blendung, unruhiger Hintergrund, mehrere Insekten und teilweise verdeckte Tiere.

Bei einem **ununterbrochenen Test von mindestens zwei Stunden** festhalten:
- Erfolgreiches Öffnen und Zeit bis zum ersten Bild.
- Bildrate, Alter der Bilder und Anteil verworfener Bilder.
- Anzahl der Wiederverbindungen und Wiederherstellungszeit nach Kamera-/Netzwerkausfall.
- CPU-, Arbeitsspeicher- und Temperaturverhalten.
- Ob Kamerazugangsdaten in Prozessprotokollen, Absturzabbildern oder Diagnosen auftauchen.
- Nachweis, dass keine Bild-, Audio- oder GPS-Datei erzeugt wird und keine Mediendaten den lokalen Rechner verlassen.

Test mit physisch getrennter Kamera und nicht erreichbarer lokaler Quell-API wiederholen. Der Prozess muss mit begrenzten Wartezeiten erneut verbinden; Metadaten bleiben bis zur Bestätigung gespeichert. Bei voller Versandwarteschlange muss der Prozess erkennbar stoppen, statt Daten stillschweigend zu verwerfen.

## Einzelbild-Hardwaretest unter Windows
Im Repository-Verzeichnis mit installierten Kamera-Abhängigkeiten in einer eigenen Umgebung ausführen:

```powershell
.\scripts\Test-BeeKeeperCamera.ps1 -PythonExe ".\.venv-camera\Scripts\python.exe"
```

Das Skript fragt den Kameraindex (z. B. `0`) oder die vollständige lokale RTSP(S)-/HTTP(S)-Adresse verdeckt ab. Die Quelle wird ausschließlich über eine temporäre Prozessumgebungsvariable, nicht über Befehlszeilenargumente übergeben und anschließend gelöscht. Es wird genau ein Bild gelesen, die Kamera freigegeben und **kein Bild gespeichert**. Für diesen reinen Bildaufnahmetest ist kein Modell erforderlich.

Die Stationsdiagnose prüft zusätzlich Basisstation, Bridge und optionale Modellkonfiguration. Ihr Gesamt-Rückgabecode kann deshalb ungleich null sein, selbst wenn der einzelne Eintrag `Live camera test` erfolgreich ist. Diesen Eintrag und alle anderen Fehler getrennt bewerten.

Bei Reolink oder anderen Netzwerkkameras den RTSP-Dienst in den Geräteeinstellungen aktivieren, ein eigenes Kamerakonto mit minimalen Berechtigungen verwenden und den zur Firmware passenden Stream-Pfad eintragen. RTSP-Adressen mit Zugangsdaten niemals in Issues, Chats, Screenshots oder Protokolle kopieren. Ein erfolgreich gelesenes Einzelbild belegt nur die Verbindung. Vor einem Pilotbetrieb sind die zweistündige Aufnahmeprüfung, Trennungs-/Wiederverbindungstests, Datenschutz- und Feldqualitätstests notwendig.

### Reolink RLC-510WA: RTSP/ONVIF
Reolink führt die RLC-510WA unter den WLAN-/RLC-Kameras mit eigenständiger RTSP- und ONVIF-Unterstützung. In Reolink Client unter **Geräteeinstellungen → Netzwerk → Erweitert → Servereinstellungen** RTSP aktivieren und speichern. Der übliche RTSP-Port ist 554. Dokumentierte Stream-Pfade für Einzelkameras sind `/Preview_01_main` (Hauptstream) und `/Preview_01_sub` (Nebenstream).

Unter Windows zunächst die lokale TCP-Erreichbarkeit **ohne Zugangsdaten** prüfen:

```powershell
Test-NetConnection -ComputerName CAMERA_IP -Port 554
```

Danach den Einzelbildtest mit verdeckter Eingabe starten:

```powershell
.\scripts\Test-BeeKeeperCamera.ps1 -PythonExe ".\.venv-camera\Scripts\python.exe"
```

Die vollständige RTSP-Adresse ausschließlich an der verdeckten Eingabeaufforderung eingeben. Benutzername, Passwort und IP müssen zur Kamera passen, etwa nach dem dokumentierten Muster `rtsp://USER:PASSWORD@CAMERA_IP:554/Preview_01_main`. Diese Adresse **nicht** in PowerShell-Befehle, Verlauf, Issues oder Logs schreiben. RTSP niemals per Portweiterleitung ins Internet freigeben. Falls der TCP-Test fehlschlägt, zuerst Porteinstellung, lokales Netzwerk oder Firewall prüfen, nicht die ONNX-Erkennung.

Herstellerquellen:
- [Reolink: unterstützte RTSP-/ONVIF-Geräte](https://support.reolink.com/articles/900000617826-Which-Reolink-Products-Support-CGI-RTSP-ONVIF/)
- [Reolink: RTSP-Adressformat](https://support.reolink.com/articles/900000630706-Introduction-to-RTSP/)
- [Reolink: Porteinstellungen](https://support.reolink.com/articles/900000621783-How-to-Configure-Reolink-Ports-Settings/)

## 3. Bewertung der Erkennungsqualität
Keine zufällige Aufteilung einzelner Videobilder in Trainings- und Testsatz. Bilder nach Beobachtung, Fotograf, Bienenstock/Standort, Kamera und Aufnahmezeitraum gruppieren, damit fast identische Bilder nicht in beiden Datensätzen auftauchen. Einen unabhängigen, zurückgehaltenen Feldtestsatz führen.

Für *Vespa velutina*, *Vespa crabro*, andere *Vespa*, *Vespula/Dolichovespula*, *Apis*, *Bombus*, Schwebfliegen und unbekannte/sonstige Arten getrennt berichten:
- Präzision, Recall, F1, Konfusionsmatrix je Klasse und 95-%-Konfidenzintervalle.
- Fehlalarme pro Kameratag bzw. Bienenstocktag.
- Übersehene Fälle bei schwachem Licht, Verdeckung und kleinen Objekten.
- Verhalten bei unbekannten Klassen (Open-Set-Erkennung).
- Kalibrierung der Konfidenz und Schwellwertwahl ausschließlich anhand von Validierungsdaten.
- Gesamtlatenz, CPU- und Speicherbedarf bei Zielauflösung und Zielbildrate.

Eine pauschale Genauigkeitsprozentzahl ist **kein ausreichendes Abnahmekriterium**. Hohe Trainings- oder Validierungswerte allein erlauben keine Freigabe. Unabhängige Prüfer müssen die zurückgehaltenen Bilder insbesondere bei Verwechslungen von *velutina* und *crabro* manuell bewerten. Keine zerstörende Bekämpfungsmaßnahme darf allein auf einer automatischen Klassifikation beruhen.

## 4. Softwareintegration und Wiederherstellung
Auf einem eigenen Testsystem:
1. Quell-API, Monitor-Empfänger und Bridge starten.
2. Kameraprozess mit geprüftem Modellmanifest starten.
3. Kandidatenereignisse im lokalen Quelljournal und in der Monitor-PWA prüfen.
4. Quell-API während der Aufnahme stoppen, Warteschlange anwachsen lassen, API wiederherstellen und genau einmalige Zustellung im Monitor-Speicher kontrollieren.
5. Kameraprozess und Rechner neu starten; prüfen, dass die Warteschlange Neustarts übersteht und bestätigte Ereignisse nicht erneut als Duplikate erscheinen.
6. Eine entbehrliche Testwarteschlange bis zur eingestellten Grenze füllen und sicherstellen, dass die Laufzeit ohne Löschen offener Ereignisse stoppt.
7. Vollständiges Backup erstellen, Prüfsummen kontrollieren, Quell-, Monitor- und Kamera-Datenbanken in **neue Pfade** wiederherstellen und ausschließlich in der isolierten Testumgebung erneut abspielen.

## 5. Freigabe oder Sperre
Eine Kamera-/Modellkombination ist **erst nach** dokumentierten Nachweisen für sämtliche obigen Abschnitte, einer geprüften Modellkarte, einem vollständigen Lizenzregister, erfolgreichem Wiederherstellungstest und unabhängiger Feldbewertung für einen Pilotbetrieb geeignet. Bis dahin: KI-Status experimentell, Erkennungen unbestätigt und externe Öffentlichkeitsarbeit zur angeblichen Einsatzbereitschaft deaktiviert.
