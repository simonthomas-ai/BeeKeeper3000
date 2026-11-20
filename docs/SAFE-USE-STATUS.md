# Sicher nutzbarer Projektumfang

**Stand: 20. November 2026**

Dieses Dokument trennt vorhandene Softwarefunktionen von einem realen, freigegebenen Feldbetrieb. „Nutzbar“ bedeutet hier: für Entwicklung und kontrollierte Tests mit synthetischen oder rechtmäßig erhobenen Testdaten. Es bedeutet nicht, dass die Gesamtanlage für öffentliche oder behördliche Einsätze freigegeben ist.

## Jetzt nutzbar – mit den genannten Grenzen

| Komponente | Zulässiger aktueller Einsatz | Grenze |
|---|---|---|
| Python-Triangulation | Lokale Berechnung mit synthetischen Peilungen und dokumentierter Unsicherheit | Suchhypothese, keine bestätigte Nestposition; keine Feldfreigabe |
| MeshCore-Protokoll | Signatur-, Ablauf-, Replay-, Speicher- und Transporttests mit Testschlüsseln | Kein realer Funk-/Antennen-/Repeater-Abnahmetest; reale Funkparameter vorher prüfen |
| Monitor-Bridge | Lokale Metadatenübertragung in eine kontrollierte Monitor-Instanz mit Testdaten | Keine Rohbilder, Audio oder GPS; nur mit passendem Cursor-Quellvertrag; Legacy-Modus ist verlustbehaftet |
| Kamera-/ONNX-Modul | Entwicklung und Tests mit rechtmäßig verwendeten Testvideos und einem selbst bereitgestellten, lizenzierten ONNX-Modell | Beispielmanifest ist absichtlich ungültig; kein freigegebenes Vespa-velutina-Modell und keine nachgewiesene Erkennungsqualität |
| LLM Council | Lokale Tests des Orchestrators und seiner Kosten-/Geheimnis-Sperren | Alle Online-Provider bleiben aus; keine externe KI-Anfrage ohne verifizierten Anbieter-Hard-Cap von 0 EUR und Datenschutzprüfung |
| CI, CodeQL, SBOM | Automatisierte Softwaretests, statische Analyse und Inventarisierung der erfassten Abhängigkeiten | Belegt weder vollständige Produkt-SBOM noch Sicherheit, Lizenzkompatibilität oder Einsatzreife |

## Sichere Standardregeln

1. Audioaufnahme, Gesichtserkennung, Personen-/Kennzeichenerkennung und dauerhafte Videoaufzeichnung bleiben deaktiviert.
2. Keine Rohbilder, Audiodaten, privaten Koordinaten, Zugangsdaten oder personenbezogenen Daten an MeshCore, öffentliche Dienste oder externe LLMs übertragen.
3. Keine exakten Nest- oder Privatgrundstückskoordinaten in öffentlichen Karten, Logs, Issues oder öffentlichen Testartefakten veröffentlichen.
4. Stationsschlüssel lokal erzeugen und schützen; öffentliche Schlüssel nur über einen vertrauenswürdigen separaten Kanal provisionieren. Niemals private Schlüssel in GitHub speichern.
5. Dienste standardmäßig nur an Loopback binden. Keine öffentliche Portfreigabe und kein ungeschütztes HTTP über das Internet.
6. SQLite-Datenbanken liegen unverschlüsselt auf Anwendungsebene vor. Betriebssystem-/Datenträgerverschlüsselung und restriktive Dateirechte sind erforderlich.
7. Erkennungen und Peilungen sind unverbindlich. Vor fachlichen Maßnahmen ist eine menschliche Bestätigung erforderlich.
8. Keine automatische Nestbekämpfung, Gift-/Pestizidausbringung, Fangaktion oder Grundstücksbetretung.
9. Keine kostenpflichtigen API-Aufrufe, Aufladungen, Hosting-Verträge, SMS oder kostenpflichtigen Fallbacks aktivieren.
10. Nur Quellcode, Modelle, Daten und Medien verwenden, deren Herkunft und Nutzungsrechte dokumentiert sind.

## Reproduzierbare lokale Softwaretests

Voraussetzungen: Python 3.12, Node.js 22 und Netzwerkzugang zum Installieren der in der Lockdatei festgelegten optionalen MeshCore-Abhängigkeiten.

```sh
python -m unittest network.test_triangulation tests.test_llm_council -v
python -m pip install --requirement network/meshcore/requirements.lock
python -m pip check
python -m unittest network.meshcore.test_protocol network.meshcore.test_receiver network.meshcore.test_event_store network.meshcore.test_transport -v
npm --prefix monitor-bridge ci --ignore-scripts --no-audit --no-fund
npm --prefix monitor-bridge test
```

Die gleiche Teststrecke wird durch `.github/workflows/quality-gates.yml` auf GitHub Actions ausgeführt. Die Workflows laufen auf dem öffentlichen Repository und verwenden keine API-Secrets oder kostenpflichtigen LLM-Dienste. Ergebnisse sind nach dem ersten erfolgreichen Workflow-Lauf zu prüfen; das bloße Vorhandensein der Workflow-Datei ist kein Testergebnis.

## Gesperrt bis zur belegten Freigabe

- Öffentlicher Pilot, Produktivbetrieb oder bundesweiter Stations-Rollout.
- Veröffentlichung von Installern, Images, Firmware-Bundles oder Hardware-Kits.
- Einsatz eines realen Erkennungsmodells ohne Rechte-, Herkunfts- und Qualitätsnachweis.
- Übermittlung personenbezogener oder exakter Standortdaten zwischen Betreibern.
- Reale Funkkonfiguration ohne Frequenz-, Leistungs-, Antennen- und Duty-Cycle-Prüfung.
- Externe KI-Anbieter, bis 0-EUR-Hard-Cap, Nutzungsbedingungen und Datenschutz nachgewiesen sind.
- Spenden, Sponsoring, Fördermittel, kostenpflichtige Leistungen oder Gemeinnützigkeitsbehauptungen ohne geeignete rechtliche/steuerliche Struktur.
- Jede Freigabe, die eine persönliche Haftungsfreiheit verspricht.

## Freigabe

Für die Sperrpunkte ist die Checkliste in [RELEASE-LEGAL-GATE.md](RELEASE-LEGAL-GATE.md) maßgeblich. Nur belegte Prüfungen dürfen abgehakt werden. Ein erfolgreicher Softwaretest hebt keinen rechtlichen, datenschutzrechtlichen, lizenzrechtlichen oder Feldtest-Blocker auf.
