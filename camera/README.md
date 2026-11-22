# Lokale Kamera und ONNX-Erkennung (experimentell)

Dieses optionale Modul ist der erste lokale Ereignislieferant für die Quell-API von BeeKeeper3000. Es liest eine USB-Kamera, eine lokale Videodatei oder einen RTSP-/HTTP-Stream über OpenCV, führt ein dokumentiertes ONNX-Objekterkennungsmodell auf der CPU aus und stellt **ausschließlich Metadaten** für die lokale Quell-API in eine Warteschlange. Einzelbilder, Vorschaubilder, Ton, Kameraadressen, GPS-Koordinaten und Modelltensoren werden weder hochgeladen noch dauerhaft gespeichert oder protokolliert.

## Sicherheit und Voraussetzungen
- Jede Beobachtung wird im strengen Schema der Quell-API als **unbestätigter Kandidat** ausgegeben. Der Monitor-Adapter kennzeichnet sie weiterhin als ungeprüft. Es gibt keine automatische Bestätigung einer Art, Nestlokalisierung oder Entscheidung zur Nestbekämpfung.
- Modellgewichte und Datensätze sind **nicht enthalten**. Das Beispielmanifest ist absichtlich ungültig (Platzhalter-Prüfsumme und ungeprüfte Lizenz) und kann keine Erkennung starten.
- Vor dem Modellstart müssen Originaladresse, unveränderliche Version/Prüfsumme, tatsächliche SPDX-Lizenz, Rechte an Weitergabe und Training sowie eine ausdrückliche Lizenzprüfung im lokalen Manifest dokumentiert werden. Die standardmäßig sperrende Manifestprüfung verlangt eine ohne Zugangsdaten erreichbare HTTPS-Adresse für Lizenznachweise, Identität der prüfenden Person, Prüfzeitstempel mit Zeitzone und ausdrückliche Wahr/Falsch-Angaben zur Erlaubnis für Inferenz und Weitergabe. Ein syntaktisch gültiger SPDX-ähnlicher Text ist **kein Nachweis** der tatsächlichen Rechte. Gemeinnützige Nutzung setzt NC-/ND-Bedingungen oder fehlende Rechte nicht außer Kraft.
- Nur Modelle mit `license_review_status` = `approved` oder `public-domain` bestehen die technische Freigabeprüfung. Das Feld dokumentiert eine Betreiberprüfung; es ist weder Rechtsberatung noch automatischer Rechtebeweis.
- Das Modell muss entweder drei benannte Ausgaben erzeugen (normalisierte `xyxy`-Rechtecke nach modellinterner NMS, Konfidenzwerte von 0 bis 1 und ganzzahlige Klassen-IDs) oder den ausdrücklich unterstützten Ultralytics-Post-NMS-Vertrag `matrix6` (`output0`: `xyxy`-Pixelkoordinaten, Konfidenz, Klassen-ID). Die Vorverarbeitung verwendet RGB, NCHW, float32 von 0 bis 1 und den im Manifest gewählten Modus `stretch` oder `letterbox`. Andere Ausgabeformen benötigen einen gesonderten Adapter mit Tests; die Tensorreihenfolge darf nicht geraten werden.
- Experimentelle Ergebnisse bleiben ungeprüft. Nicht zur Nestzerstörung, zum Fang, zur Pestizidanwendung oder zu anderen unumkehrbaren Maßnahmen verwenden.

## Installation (Python 3.11 oder neuer)
Im Hauptverzeichnis von BeeKeeper3000 unter Windows:

~~~powershell
python -m venv .venv-camera
.\.venv-camera\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r camera/requirements.txt
~~~

Unter Linux:

~~~sh
python3 -m venv .venv-camera
. .venv-camera/bin/activate
python -m pip install --upgrade pip
python -m pip install -r camera/requirements.txt
~~~

Die Erkennung nutzt nur die CPU. ONNX Runtime steht unter MIT, `opencv-python-headless` unter Apache-2.0. Dies sind optionale direkte Abhängigkeiten, keine vollständige Aufstellung aller transitiven Pakete (SBOM). Vor jeder Veröffentlichung müssen die transitiven Abhängigkeiten erneut geprüft und ihre Versionen für die Zielplattform festgelegt werden.

## Konfiguration
`camera/model-manifest.example.json` in eine lokale, geschützte Datei neben dem ONNX-Modell kopieren und **sämtliche Platzhalter** durch überprüfte Herkunftsdaten ersetzen. Der Modellpfad muss innerhalb des Verzeichnisses mit dem Manifest liegen. SHA-256 lokal berechnen:

~~~powershell
Get-FileHash .\models\your-model.onnx -Algorithm SHA256
~~~

Umgebungsvariablen im selben Terminal setzen. Echte Zugangsdaten niemals in Skripten, im Quellcode oder als Befehlszeilenargumente speichern:

~~~powershell
$env:BEEKEEPER_MODEL_MANIFEST = 'C:\secure\beekeeper\model-manifest.json'
$env:BEEKEEPER_CAMERA_SOURCE = '0' # USB-Kameraindex; alternativ lokale Datei / rtsp(s)://-Adresse
$env:BEEKEEPER_CAMERA_MAX_FPS = '5'
$env:BEEKEEPER_CAMERA_COOLDOWN_SECONDS = '30'
.\scripts\Start-BeeKeeperCamera.ps1 -ModelManifest $env:BEEKEEPER_MODEL_MANIFEST -CameraSource $env:BEEKEEPER_CAMERA_SOURCE -StationId 'station-01' -PythonExe '.\.venv-camera\Scripts\python.exe'
~~~

Der Kamerastarter liest den Quell-API-Schlüssel aus der DPAPI-geschützten Schlüsseldatei der Basisstation und übergibt ihn ausschließlich über die Prozessumgebung an den Kindprozess. Der Schlüssel erscheint nicht in Befehlszeile oder Protokollen. Die Basisdienste zuvor separat mit `scripts/Start-BeeKeeperStation.ps1` starten. Die Quelladresse ist auf Loopback (`127.0.0.1` oder `::1`) beschränkt; authentifizierte HTTP-Anfragen dürfen Weiterleitungen nicht folgen. Die Kameraquelle ist eine lokale Einstellung. RTSP-Zugangsdaten niemals in Tickets oder Protokolle kopieren.

## Offline-Warteschlange und Fehlerverhalten
- Erkennungen werden vor der Übertragung in einer privaten lokalen SQLite-Versandwarteschlange gespeichert.
- Ereignisse werden erst entfernt, wenn die Quell-API HTTP 200 oder 201 bestätigt.
- Bei vorübergehenden Verbindungsfehlern bleiben Ereignisse erhalten; die Bildaufnahme läuft weiter.
- Ist die begrenzte Warteschlange voll, beendet sich die Laufzeit kontrolliert, statt Beobachtungen stillschweigend zu verwerfen.
- Eine bestehende Ereignis-ID darf nicht für veränderte Inhalte wiederverwendet werden.
- Nach Kameraabbrüchen wird die Verbindung mit begrenzter exponentieller Wartezeit erneut aufgebaut. Einstellbare Bildrate und ONNX-Worker-Threads begrenzen die CPU-Last.
- Für Netzwerk-/Dateiquellen fordert OpenCV/FFmpeg beim Öffnen und Lesen ein Zeitlimit von fünf Sekunden an. Ohne Unterstützung dafür wird die Verarbeitung sicher abgebrochen. Diese Backend-Anforderung garantiert nicht, dass jeder Treiber oder jede Firmware niemals hängen bleibt.
- Rohbilder bleiben ausschließlich während der Auswertung im Arbeitsspeicher und werden von diesem Modul nicht dauerhaft gespeichert.

Unter Windows müssen NTFS-Zugriffsrechte eingeschränkt sein; unter Linux/macOS erhalten Verzeichnisse den Modus 0700 und Datenbankdateien 0600. SQLite ist nicht anwendungsseitig verschlüsselt: BitLocker oder verschlüsselten Datenträger einsetzen. Die Versandwarteschlange ist eine eigene Datenbank und muss vor dem produktiven Einsatz in einem vollständigen Sicherungs-/Wiederherstellungstest berücksichtigt werden.

## Expliziter lokaler Bild-/Videoimport

Für den einzelnen Dateiimport steht zusätzlich der gemeinsame Adapter `adapters/local_media.py` mit CLI `scripts/import_local_media.py` bereit. Er verarbeitet JPEG/PNG/WebP und ausgewählte lokale Videodateien innerhalb eines ausdrücklich erlaubten Stammordners, führt die Inferenz lokal aus und legt nur unbestätigte Metadaten in der privaten SQLite-Outbox ab. Er lädt keine Medien hoch und spricht keine Netzwerk-API an. Größen-, Pixel-, Frame- und Zeitlimits sowie Symlink-/Traversal-Sperren sind dokumentiert und automatisiert getestet. Siehe [Local Media Import](../docs/LOCAL-MEDIA-IMPORT.md).

## Tests

~~~sh
python -m unittest discover -s camera -p 'test_*.py' -v
~~~

Diese Tests verwenden künstliche Metadaten und simulierte Komponenten. Sie belegen **weder Kamerakompatibilität noch Modellqualität, ONNX-Schnittstellenkompatibilität, Feldleistung oder DSGVO-Konformität**. Das optionale [Werkzeug zur Bewertung mit unabhängigen Testbildern](../docs/MODEL-EVALUATION.md) berechnet reproduzierbare Kennzahlen nur mit tatsächlich bereitgestellten, unabhängig annotierten Testdaten. Vor einem Pilotbetrieb auf der genauen Kamera, dem Stream, dem Rechner und dem Modell prüfen.
