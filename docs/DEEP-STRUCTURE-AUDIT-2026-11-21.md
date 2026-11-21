# Tiefenprüfung und Strukturstatus – BeeKeeper3000 / VespaGuard

**Prüfdatum:** 21.11.2026  
**Geprüfter Ausgangsstand:** `main` nach Merge von PR #86, Commit `dbd4f69274cb95707e1c52605bf06c409c1011b5`  
**Gegenstand:** kompletter Git-Baum (Dateiinventar) und vertiefte Prüfung der zentralen Daten-, Kamera-, API-, Bridge-, PWA-, Triangulations- und MeshCore-Pfade.

## 1. Repository-Inventar

Der rekursive Git-Baum enthält 148 Dateien in 18 Verzeichnissen:

| Dateityp | Anzahl |
| --- | ---: |
| Markdown | 50 |
| Python | 47 |
| GitHub-Workflows (YAML) | 12 |
| PowerShell | 8 |
| JSON | 6 |
| JavaScript-Module | 5 |
| systemd-Units | 4 |
| Sonstige (HTML, CSS, SVG, Webmanifest, CSV, Shell, Lockfiles, Vorlagen) | 16 |

Zwei leere Dateien sind `__init__.py`-Paketmarker (`tests/`, `tools/`) und keine defekten Implementierungen. Das Repository enthält keine eingecheckten realen Trainingsbilder, kein freigegebenes Insektenmodell und keine produktive Kameradatenbank.

## 2. Verifizierte Softwarepfade

### Kamera und lokales Journal
- `camera/runtime.py`: lokaler Capture-/Inference-Loop, begrenzte FPS, Reconnect-Backoff, Drei-Frame-Ausfallgrenze und Freigabe des Capture-Handles.
- `camera/outbox.py`: SQLite-Outbox, eindeutige Event-ID, Payload-Kollisionsprüfung, persistente Cooldowns, Vollspeicher-Stopp statt stiller Verwerfung sowie POSIX-Dateirechte.
- `camera/source_client.py`: nur HTTP-Loopback, API-Key, kein Proxy, keine Weiterleitungen, Timeout und kontrollierter Umgang mit gelöschten Event-IDs.
- `camera/model_manifest.py` / `camera/onnx_detector.py`: strikte Modellmanifest-/Hash-/Lizenzprüfung und CPU-Inferenzpfad.

**Freigabegrenze:** Pipeline-Code vorhanden bedeutet nicht, dass ein gültiges Modell oder eine reale Kamerainstallation vorhanden ist. Das Beispielmanifest ist absichtlich nicht produktiv freigegeben; Modellgewichte fehlen.

### Source API und Bridge
- `network/source_api.py`: Loopback-only HTTP, API-Key, begrenzte Worker, Request-/Body-Timeouts, Rate-Limit, Body-/Response-Limits und Fehlercodes.
- `network/source_event_store.py`: SQLite-Journal, monotone Sequenz, Idempotenz, Konfliktprüfung, Tombstones, Retention und Kapazitätsgrenze.
- `network/source_cursors.py`: signierte HMAC-Cursor für wiederaufnehmbare Pagination.
- `monitor-bridge/bridge.mjs`: begrenzte Antworten, Retry-Backoff, Cursor-Checkpoint erst nach persistenter Monitor-Bestätigung, stabile Event-IDs und Replay-Schutz.

**Nachweisgrenze:** Die dokumentierten 205 Ereignisse sind synthetische Integrationstest-Ereignisse. Sie beweisen die Software-Übertragung, nicht den Anschluss eines tatsächlich erkennenden Kameraproduzenten oder reale biologische Beobachtungen.

### Mobile PWA
- Lokale IndexedDB, manuelle Beobachtung, optionale Foto-/GPS-/Orientierungsaufnahme und expliziter Metadatenexport.
- Private Notizen, Fotos, GPS und Sensorwerte bleiben lokal; der Export enthält nur sechs Felder des Source-API-Vertrags.
- Bluetooth-, USB-, Serial- und NFC-Adapter sind nicht implementiert; die API-Erkennung ist nur eine Browser-Fähigkeitsanzeige.

**Optimierung in PR #86:** Der Kompasslistener wartete zuvor nur auf das erste Sensorereignis. Ein anfänglicher Wert ohne gültigen Winkel konnte so einen späteren gültigen Wert verpassen. `waitForOrientationSample()` ignoriert jetzt uninitialisierte Werte, beendet sich nach einem gültigen Sample oder Timeout und entfernt Listener/Timer. Zusätzlich wurden IndexedDB-Upgrade-, Blockierungs- und Transaktionsfehler gehärtet. Drei Regressionstests decken Sensorstart und Timeout ab.

### Triangulation und MeshCore
- Triangulation gewichtet Peilungen nach Winkelunsicherheit, prüft Zeitbezug und Geometrie und liefert eine Suchhypothese mit angenäherter 95-%-Unsicherheitsellipse.
- MeshCore-Pakete sind Ed25519-signiert; Stationshashes werden gegen lokale Schlüssel-Allowlisten geprüft. Exakte Stationskoordinaten und Medien werden nicht über Funk übertragen.
- Deduplizierung und lokale Speicherung sind implementiert.

**Freigabegrenze:** Es liegen keine Feldmessungen mit realen Funkgeräten, Antennen, mehreren Stationen und vermessenen Zielpositionen vor. Die Triangulation ist nicht feldvalidiert und darf keinen bestätigten Neststandort behaupten.

## 3. Automatisierte Prüfungen

PR #86 wurde vor dem Merge auf Commit `2ff6d011a74eae5b08f65e65c1bdc4f3ed525156` geprüft:

- Quality Gates: erfolgreich – Python-Kern/Sicherheit, MeshCore-Protokoll/Receiver/Store/Transport, Kamera-Outbox Linux und Windows, Bridge und Mobile-PWA-Vertragstests.
- CodeQL Python: erfolgreich.
- CodeQL JavaScript/TypeScript: erfolgreich.

PR #86 wurde als Squash-Merge in `main` übernommen; Merge-Commit: `dbd4f69274cb95707e1c52605bf06c409c1011b5`.

Diese Prüfungen sind Softwaretests. Sie ersetzen keine Kamera-, Radio-, GPS-/Kompass-Kalibrierungs-, Datenschutz- oder Feldabnahme.

## 4. Offene reale Einsatzvoraussetzungen

1. **Kameradaten:** echte, lizenziell geklärte und fachlich annotierte Bilddaten je Zielklasse fehlen; keine Modellgewichte freigegeben.
2. **Biologische Qualität:** unabhängige Testdaten aus unbekannten Standorten/Kameras/Jahreszeiten und Klassenmetriken fehlen.
3. **Feldstation:** Windows-/Linux-Installation, reale Capture-Hardware, Dauerbetrieb, Wetter-/Nacht-/Gegenlichtfälle und Restore-Drill sind nicht vollständig abgenommen.
4. **Triangulation:** Peilgeräte, Stationskoordinaten, Kompasskalibrierung, Zeit-Synchronität und vermessene Zielpunkte fehlen.
5. **MeshCore:** reale Firmware-/Geräteinteroperabilität, Reichweite, Antennen, Airtime, Paketverlust, Energie und zulässige Funkparameter sind nicht gemessen.
6. **Lizenz-/Rechtsfreigabe:** historische Upstream-Quellen und vollständige Rechtekette müssen vor Veröffentlichung/Vertrieb geklärt sein; Funk-/Hardwareeinsatz braucht separate Prüfung.

## 5. Gesamturteil

Die lokale Metadatenpipeline, Journal-/Cursor-Übertragung, mobile Offline-Erfassung, Kamera-Laufzeitgerüste, MeshCore-Protokoll und mathematische Triangulationskomponente sind softwareseitig vorhanden und durch automatisierte Tests teilweise abgesichert. Der Schritt von einer funktionierenden Softwarestrecke zu einem real einsetzbaren Hornissen-Frühwarnsystem ist noch nicht abgeschlossen: reale Bildbestände, Fachannotation, freigegebene Modellgewichte, Hardware und unabhängige Feldvalidierung bleiben zwingende Freigabegates.

Es wurden keine Testbilder als echte Trainingsdaten ausgegeben, keine Kennzahlen erfunden und keine physischen Tests behauptet.
