# Lokaler Bild- und Videoimport

Status: Softwareadapter und automatisierte Grenztests vorhanden; reale Datei-/Codec-/Modellvalidierung auf Zielhardware weiterhin erforderlich.

## Zweck und Datenfluss

Der Adapter in adapters/local_media.py verarbeitet genau eine vom Betreiber ausgewählte lokale Bild- oder Videodatei. Unterstützte Endungen: JPEG, PNG, WebP sowie MP4, M4V, MOV, MKV, AVI und WebM.

Der Adapter gehört zum gemeinsamen AdapterSupervisor-Lebenszyklus. Er prüft einen freigegebenen Stammordner, verhindert Symlink-Pfade und Traversal, begrenzt Dateigröße und dekodierte Bildabmessungen, setzt FFmpeg-Öffnungs-/Lesetimeouts und begrenzt Videoframes sowie Laufzeit. Bildheader werden vor der vollständigen Dekodierung gelesen; Videoframes werden einzeln im Arbeitsspeicher verarbeitet.

Die ONNX-Auswertung läuft lokal auf der CPU. Der Event-Vertrag akzeptiert nur das bestehende Metadaten-Schema der Quell-API. Bildbytes, Medien-URLs, Audiobytes, Videodaten, Credentials und exakte Standortfelder werden vom gemeinsamen Lifecycle abgelehnt. Der CLI-Importer schreibt ausschließlich Metadaten in die lokale SQLite-Outbox. Er besitzt keinen HTTP-Client und lädt keine Dateien hoch.

## Konservative Standardgrenzen

| Grenze | Standard |
|---|---:|
| Bilddatei | 32 MiB |
| Videodatei | 256 MiB |
| Bildpixel gesamt | 50 Millionen |
| Bildbreite/-höhe | jeweils 12.000 Pixel |
| Videoframes | höchstens 10.000 |
| Videodauer | höchstens 3.600 Sekunden |
| Frames je Leseaufruf | höchstens 24 |
| Detektionen je Frame | höchstens 64 |
| Wiederholungs-Cooldown je Art | 30 Sekunden |
| FFmpeg Öffnen/Lesen | jeweils 5 Sekunden |

## Voraussetzungen

1. Optionalen Kamera-Stack installieren: python -m pip install -r camera/requirements.txt.
2. Das ONNX-Modell muss durch Manifest, SHA-256 und eine dokumentierte Lizenzprüfung eindeutig freigegeben sein. Das Beispielmanifest enthält absichtlich keine freigegebenen Modellgewichte.
3. Der Betreiber wählt den Ordner mit der Quelldatei ausdrücklich aus und bestätigt den lokalen Dateizugriff.
4. Die Quelldatei muss innerhalb dieses Ordners liegen; Symlink-Pfade sind nicht erlaubt.
5. Die SQLite-Outbox muss auf einem geschützten Datenträger liegen. Die Datenbank ist nicht anwendungsseitig verschlüsselt; BitLocker bzw. eine verschlüsselte Systempartition ist erforderlich.

## Beispiel – Windows PowerShell

~~~powershell
python -m pip install -r camera/requirements.txt
python scripts/import_local_media.py --manifest "C:/BeeKeeper/model/model-manifest.json" --source "C:/BeeKeeper/review/aufnahme.mp4" --allowed-root "C:/BeeKeeper/review" --station-id "station-01" --outbox "C:/BeeKeeper/data/local-media-outbox.sqlite3" --confirm-local-file-access
~~~

## Beispiel – Linux

~~~sh
python -m pip install -r camera/requirements.txt
python scripts/import_local_media.py --manifest "$HOME/.config/beekeeper/model-manifest.json" --source "$HOME/BeeKeeper/review/aufnahme.mp4" --allowed-root "$HOME/BeeKeeper/review" --station-id "station-01" --outbox "$HOME/.local/share/beekeeper3000/local-media-outbox.sqlite3" --confirm-local-file-access
~~~

Der CLI-Importer verwendet keine Netzwerkverbindung. Nach erfolgreicher Auswertung meldet er, wie viele Metadatenereignisse in die lokale Outbox übernommen wurden. Die spätere Weiterleitung bleibt Aufgabe des getrennten Stations-/Bridge-Dienstes und unterliegt dessen Authentifizierungs- und Datenschutzprüfungen.

## Tests und Abnahmegrenzen

~~~sh
python -m unittest adapters.test_lifecycle adapters.test_local_media -v
~~~

Die Tests decken JPEG/PNG/WebP-Header, lokale Bilddekodierung, Video-Zeitlimits, Dateigröße, Pixel-/Frame-/Detektionsgrenzen, Pfadtraversal, Symlink-Verbot, Quelländerung nach Discovery, Berechtigungsfehler, sauberes Ende einer Einmaldatei und Metadaten-only-Ausgabe ab.

Sie belegen keine Unterstützung jeder Kamera, jedes Video-Codecs, jedes Mobilgeräts oder jedes ONNX-Modells. Vor dem Pilotbetrieb sind reale Testdateien und Hardware mit dokumentierter Herkunft und Prüfsumme zu verwenden. Es entsteht weder eine Artbestätigung noch eine Trainingsfreigabe.
