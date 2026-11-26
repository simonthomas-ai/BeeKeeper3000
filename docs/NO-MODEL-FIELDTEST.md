# Feldtest ohne KI-Erkennung

**Zweck:** Einen begrenzten, nicht-inferierenden Stations- und Bedienungs-Feldtest starten, obwohl im BeeKeeper3000-Checkout kein rechtlich und technisch freigegebenes Modell vorliegt. Das ist **keine** Abnahme der automatischen Erkennung und erzeugt keine Kamera-Erkennungsereignisse.

## Implementierungsstatus

Der ZIP/JSONL-Validator, der gruppierte Splitter und der reproduzierbare Siebenklassen-Trainer samt optionalem binärem `vespa_velutina`-Task sind inzwischen in `main` vorhanden. Der Monitor-ZIP-Export wurde gegen den gepinnten BeeKeeper3000-Validator und per Fixture-Roundtrip geprüft; das bestätigt nur die Import-/Vertragskompatibilität, nicht Bildqualität, Modelltraining oder Erkennungsleistung. Für ein echtes Training fehlen weiterhin `datasets/beekeeper/` mit vollständig geprüften Bild-/Label-/Provenienzdaten und `training/reviewed-annotations.json`. Es gibt weiterhin keinen freigegebenen Realbild-Datensatz, kein trainiertes oder integriertes Modell, keinen unabhängigen Feld-Holdout und keine Alarmfreigabe. Der Kamera-/KI-Pfad bleibt deaktiviert.

## Modellbestand: lokaler Checkout und externer Kandidat

Im BeeKeeper3000-Checkout und in den hier verfügbaren Archivdateien wurde keine ONNX-/PT-Gewichtsdatei gefunden. Das Beispielmanifest ist weiterhin absichtlich ungültig.

Eine gleichnamige Datei ist tatsächlich **extern** im öffentlichen, archivierten Repository [vespCV/hornet3000](https://github.com/vespCV/hornet3000) vorhanden: `yolov8sModel/best.onnx`, 44.737.849 Byte (Git-Blob `97fb748affc642238c1135768a53098f594de0d1`) bei Upstream-Commit [`78f51980ee99e45748e78e54dd1312cff846a5ac`](https://github.com/vespCV/hornet3000/commit/78f51980ee99e45748e78e54dd1312cff846a5ac). `best8.onnx` und `best_default.onnx` verweisen dort auf denselben Git-Blob; `best9.onnx` hat bei gleicher Dateigröße einen anderen Blob. Diese Git-Objekt-IDs sind **keine SHA-256-Prüfsummen der Modelldatei**. Die Datei wurde für diese Arbeit nicht heruntergeladen oder in dieses Projekt übernommen.

Das gepinnte Upstream-Commit enthält eine Repository-`LICENSE` unter GPL-3.0. Das belegt für sich allein weder die Lizenz oder Weitergabefähigkeit des konkreten Gewichts, noch die Rechte der Trainingsbilder oder die Einwilligung zur Weiterverarbeitung. Das README nennt das Kaggle-Training- und Validierungsdataset `vespa-velutina-v-crabro-vespulina-vulgaris` und sagt, Bilder seien überwiegend aus waarnemingen.nl/Observation.org mit „alle teilbaren Lizenzen“ zusammengestellt. Es enthält weder eine maschinenlesbare Dataset-Lizenzakte noch individuelle Bildrechte, Attributionen, Datensatz-Revision, Bild-/Label-Hashes oder eine überprüfbare Zuordnung zu Train/Val/Test. Das ist daher ein **Prüfkandidat**, kein freigegebenes BeeKeeper3000-Modell.

Technisch ist die Integration ebenfalls nicht nachgewiesen: `yolov8sModel/args.yaml` dokumentiert `task: detect`, YOLOv8s, `imgsz: 640`, `pretrained: true` und Determinismus-Seed 0. Eine gepinnte Dataset-Konfiguration in `colab/config.yaml` listet drei Ausgabeklassen in dieser Reihenfolge: `0: Vespa_velutina`, `1: Vespa_crabro`, `2: Vespula_vulgaris`. Diese YAML-Reihenfolge ist eine starke Upstream-Quellenangabe, aber sie beweist nicht die tatsächliche ONNX-Graph-Reihenfolge oder Klassensemantik jeder Exportvariante. Ohne lokale Datei kann auch die echte Ein-/Ausgabeschnittstelle nicht gemessen werden. BeeKeeper3000 akzeptiert derzeit nur explizite Post-NMS-`xyxy`-/Scores-/Klassen-Ausgaben beziehungsweise `matrix6`; ein bestätigtes Roh-ONNX-I/O- und NMS-Ergebnis für diese Datei liegt nicht vor. Die verfügbaren drei Klassen decken weder `other_vespidae`, Honigbiene, Hummel, Schwebfliege noch sonstige Insekten des Monitor-Siebenklassen-Katalogs ab. Ohne konkrete Datei-/SHA-256, Rechtsfreigabe, Graph-I/O, tatsächliche NMS-Ausgabe und unabhängige Holdout-Evaluation darf der Kandidat nicht aktiviert werden.

## Was dieser Test abdeckt

- Basisdienste, Loopback-APIs und Monitor-Verbindung auf dem tatsächlichen Stationsgerät.
- Optionale Verbindung zu einer echten Kamera durch genau einen gelesenen Frame; das Bild wird nicht gespeichert.
- Manuelle, vom Beobachter eingegebene Sichtungen in der lokalen Mobile-PWA. Diese bleiben in der Browser-IndexedDB.

Er startet ausdrücklich **nicht** `camera.runtime`, führt keine Inferenz aus, sendet keine Test-Sichtungen und erzeugt keine produktiven Alarme. Ein nicht gesetztes/lokales Modellmanifest und der Status `WARN: no model configured` sind in diesem Ablauf erwartet. Der ONNX-Nullbild-Smoke-Test im Stationsdoctor prüft nur Software-Ausführbarkeit und ist kein Feldtest.

## Datenfluss- und Sicherheitsgrenzen

Die lokale Source API akzeptiert sechs Beobachtungsfelder. Die Bridge ordnet **jedes** Quellereignis als `camera_detection` mit `unverified_candidate`-Label ein. Daher dürfen manuelle PWA-Exporte in diesem Modus **nicht** mit `Import-BeeKeeperMobileExport.ps1` in die Source API importiert werden: Das würde eine manuelle Beobachtung fälschlich als Kameraereignis darstellen. Es gibt keinen etablierten separaten manuellen Beobachtungstyp im Source-API-/Bridge-Vertrag.

Manuelle Sichtungen verbleiben im Browser und sind nicht in der Stationsdatenbank oder Monitor-Ansicht verfügbar. Für einen integrierten manuellen Server-Workflow ist zuerst ein versionierter Ereignistyp im Monitor-Vertrag und eine kompatible Änderung beider Repositories erforderlich. Keine künstlichen Ereignisse in eine Feldstation oder Produktionsdatenbank einspeisen.

## Voraussetzungen

- Raspberry Pi OS / Debian Bookworm oder neuer mit systemd, Python 3.11+ und Node.js 20+; konkrete Pi-Platine, Kamera, Firmware und Treiber vor Ort erfassen. Windows 10/11 kann denselben Ablauf für die Basisstation nutzen.
- Lokale BeeKeeper3000- und Beekeeper-Monitor-Checkouts. Monitor- und Quell-API-Schlüssel müssen vor dem Start lokal eingerichtet sein; niemals in Befehle, Logs oder dieses Protokoll kopieren.
- Für den optionalen Kameraverbindungstest: OpenCV aus `camera/requirements.txt` (`opencv-python-headless==4.14.0.94`, Apache-2.0). Die ONNX-Abhängigkeit (`onnxruntime==1.32.0`, MIT) und ein Modell werden für diesen No-AI-Test nicht benötigt.
- Kein zusätzliches Modell, Datensatz, Anbieter oder Paket wird heruntergeladen. Die im Upstream-Repository vorhandene ONNX-Datei ist noch nicht geprüft oder integriert und darf nicht als lokales Modell behandelt werden.

## Startsequenz für Linux / Raspberry Pi

Im BeeKeeper3000-Checkout zunächst nur die Voraussetzungen prüfen, dann die drei Basisdienste installieren und starten:

```sh
sudo bash scripts/install-linux.sh \
  --beekeeper-repo "$PWD" \
  --monitor-repo "../Beekeeper-Monitor" \
  --validate-only

sudo bash scripts/install-linux.sh \
  --beekeeper-repo "$PWD" \
  --monitor-repo "../Beekeeper-Monitor"

systemctl is-active beekeeper-monitor beekeeper-source-api beekeeper-bridge
python3 scripts/station_doctor.py --monitor-repo "../Beekeeper-Monitor" --json
```

Der Doctor muss die Repository- und Laufzeitprüfungen bestehen; nach gestarteten Diensten muss er die lokalen APIs erreichen. Authentifizierung wird nur geprüft, wenn die jeweiligen Schlüssel bereits in der Prozessumgebung vorhanden sind. Kein API-Port darf öffentlich freigegeben sein. Die Basisinstallation startet keine Kamera und aktiviert keine KI.

## Optionale echte Kameraverbindungsprüfung

Dieser Test öffnet die angegebene Kamera explizit, liest einen Frame und gibt die Kamera danach frei. Er speichert oder überträgt den Frame nicht und erstellt keine Kandidatenmeldung. Auch ein eventuell im Elternprozess gesetztes `BEEKEEPER_MODEL_MANIFEST` wird während dieses Tests unterdrückt und danach wiederhergestellt; es wird keine ONNX-Inferenz ausgeführt. Für Windows die verdeckte Eingabe verwenden:

```powershell
.\scripts\Test-BeeKeeperCamera.ps1 -PythonExe ".\.venv-camera\Scripts\python.exe"
```

Unter Linux Modellkonfiguration in einer Subshell ausblenden, Quelle interaktiv und ohne Echo setzen, prüfen und mit Ende der Subshell entfernen:

```sh
(
  unset BEEKEEPER_MODEL_MANIFEST
  read -r -s -p "Kameraindex, lokaler Pfad oder RTSP(S)-URL: " BEEKEEPER_CAMERA_SOURCE
  printf '\n'
  export BEEKEEPER_CAMERA_SOURCE
  python3 scripts/station_doctor.py \
    --monitor-repo "../Beekeeper-Monitor" \
    --test-camera \
    --json
)
```

RTSP-Zugangsdaten weder in die Shell-Historie noch in Logs oder Testnotizen schreiben. Eine erfolgreiche Zeile `Live camera test` belegt nur, dass die Kamera geöffnet und ein Frame gelesen wurde. Bei einem nicht-null Exitcode die einzelnen Prüfzeilen auswerten: Der Doctor kann unabhängig vom Kameratest an nicht laufenden Diensten scheitern.

## Manuelle Beobachtung ohne Serverübertragung

Die Mobile-PWA kann zur Bedienungsprobe auf demselben Stationsgerät lokal bereitgestellt werden:

```sh
python3 -m http.server 8000 --bind 127.0.0.1 --directory mobile-pwa
```

Auf diesem Gerät `http://127.0.0.1:8000/` öffnen und ausschließlich tatsächlich beobachtete Fälle manuell erfassen. Die Beobachterangabe ist weder Modellkonfidenz noch Expertenbestätigung. PWA-Datensätze bleiben in der lokalen Browser-IndexedDB; es gibt keine automatische Synchronisierung. Fotos, GPS und Notizen für diesen ersten Versuch ausgeschaltet lassen. Den Metadatenexport nicht in die Station importieren, solange der gemeinsame Vertrag manuelle und Kameraereignisse nicht unterscheidet. Server mit `Ctrl+C` beenden.

## Protokoll und Abbruch

Für den Feldbericht Gerät/Revision, Betriebssystem, Kamera/Firmware, Verbindung, Start-/Endzeit, Doctor-Ergebnis, erfolgreiche Frameaufnahme sowie Abbrüche notieren. Keine Passwörter, Kamera-URLs, Privatkoordinaten, Medien oder Personenangaben aufnehmen. Tests sofort abbrechen, wenn Daten unerwartet außerhalb des Geräts erscheinen, eine URL oder ein Schlüssel protokolliert wird oder eine manuelle Sichtung als Kameraereignis gespeichert wird.

Den Kameratest nach einem Frame beenden; den lokalen PWA-Webserver mit `Ctrl+C` stoppen. Basisdienste können ohne Datenlöschung angehalten werden:

```sh
sudo systemctl stop beekeeper-bridge beekeeper-source-api beekeeper-monitor
```

## Was weiterhin blockiert ist

- Automatische Detektion und jede Qualitätsaussage bleiben blockiert: kein lokales, freigegebenes und kompatibilitätsgeprüftes ONNX-Modell, keine belegte vollständige Rechtekette/fachliche Freigabe des externen Kandidaten, kein unabhängiger BeeKeeper-Holdoutbestand und keine gemessenen Kennzahlen.
- Ein einzelner Kamera-Frame ist keine Dauerbetriebs-, Wiederverbindungs-, Datenschutz- oder Feldleistungsprüfung.
- Das Feldprotokoll erzeugt absichtlich keine integrierten Beobachtungen. Ein manueller Server-Workflow benötigt einen eigenen, versionierten Eventtyp und Kompatibilitätstests im Monitor-Repository; dieses Repository allein kann das nicht sicher umsetzen.
- Der tatsächliche Raspberry-Pi-/Kameratest, Datenschutzfreigabe, Datenaufbewahrung und Betreiberrollen müssen vor Ort entschieden und nachgewiesen werden.
