# VespaGuard: priorisierte Kamera-Integration (21.11.2026)

## Entscheidung

Die bestehende BeeKeeper3000-Kamera-/ONNX-Pipeline und die lokale Monitor-Bridge zuerst fertigstellen. Kein unkontrollierter Import fremder Quellbäume, Gewichte oder Bilddatensätze. Keine neue öffentliche Website aktivieren.

## Vorhandene, konkret geprüfte Schnittstellen

- `camera/`: OpenCV-Aufnahme, ONNX Runtime, streng geprüftes Modellmanifest, lokale SQLite-Outbox. Ohne tatsächlich freigegebene ONNX-Gewichte **keine** Erkennung.
- `network/source_api.py`: authentifizierte lokale Quell-API mit signierter Cursor-Paginierung.
- `monitor-bridge/`: Node.js-Übertragung ausschließlich notwendiger Metadaten, Wiederholung und dauerhafte Checkpoints.
- `Beekeeper-Monitor/integrations/local_ingest.py`: authentifizierter lokaler SQLite-Empfang, PWA-Ereignisansicht.
- `Beekeeper-Monitor/integrations/external_detector_adapter.py`: strikte Umwandlung bereits normalisierter Detektormetadaten; **noch nicht** mit einer realen vespCV-/VespAI-Ausgabe verbunden.

## Warum zunächst kein Fremdmodell automatisch aktivieren?

Die Kamera-Pipeline verlangt eine verifizierte Modell-SHA-256, überprüfte Modelllizenz, dokumentierte Modellherkunft und eines der implementierten ONNX-Ausgabeformate. Das aktuelle `camera/model-manifest.example.json` ist absichtlich nicht startfähig. Ein beliebiges YOLO-PyTorch-Gewicht ist damit nicht automatisch kompatibel. Die Artklassen des Modells müssen einzeln auf den internen Kandidatenvertrag abgebildet werden; unbekannte Labels sind abzulehnen.

## Konkrete Abnahme in sinnvoller Reihenfolge

1. **Lizenz und Modell**: Originalquelle, exakte Version, SHA-256, zulässige Inferenz/Weitergabe, Klassenliste und ONNX-Tensorformat schriftlich belegen. VespAI verlangt laut Publikation für den Zugang zu Code/Validierungsdaten ein Anfrageverfahren und ist CC BY-NC-SA 4.0; vespCV-Code ist GPLv3, Modell-/Bildrechte separat prüfen.
2. **ONNX-Kompatibilität**: Form der Eingaben und Ausgaben maschinell kontrollieren; nur explizit unterstützte `xyxy_normalized_post_nms`- oder `matrix6`-Varianten verwenden; keine geratenen Achsen oder Klassenindizes.
3. **Isolierter Test**: `python -m unittest discover -s camera -p 'test_*.py' -v` und `python -m unittest discover -s integrations -p 'test_*.py' -v` (im jeweiligen Repository) ausführen; danach vollständige lokale Quelle→Bridge→Monitor-Kette mit gekennzeichneten Testereignissen.
4. **Realer Kameratest**: Kamera, Belichtung, Stromverbrauch, Offline-Ausfälle, Warteschlange, Neustarts und Netzwerkunterbrechung messen.
5. **Feldabnahme**: Unabhängige, fachlich annotierte Bilder anderer Standorte und Jahreszeiten; insbesondere Vespa crabro, Wespen, Bienen, Hummeln und Schwebfliegen. Precision/Recall und Fehlalarmrate pro Art dokumentieren.
6. **Erst danach** eine auf unbestätigte Hinweise begrenzte Pilotfunktion freigeben; keine automatische Nestzerstörung oder unkontrollierte Fanghardware.

## Internationale Referenzen

- vespCV: https://github.com/vespCV/vespcv
- VespAI: https://pmc.ncbi.nlm.nih.gov/articles/PMC10991484/
- Waspinator: https://waspinator.dev/
- Hornet3000 (archiviert): https://github.com/vespCV/hornet3000

**Status:** Architektur und Teilmodule vorhanden; kein durch echte Modellgewichte und Hardware nachgewiesener produktiver End-to-End-Detektor. Grüne CI-Tests ersetzen keine Modell- und Feldabnahme.
