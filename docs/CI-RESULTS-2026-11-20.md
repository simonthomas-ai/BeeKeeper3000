# CI- und Lieferketten-Prüfbericht — 20.11.2026

## Verifizierte GitHub-Actions-Läufe

Die folgenden Ergebnisse wurden am 20.11.2026 direkt aus den GitHub-Actions-Läufen und Job-Protokollen abgerufen. Sie gelten nur für die jeweils genannten Commits und den erfassten Projektumfang.

| Workflow | Commit | Ergebnis | Lauf |
|---|---|---|---|
| Quality gates | `58b7fd30d022f2f0b0c5b14fd598f449adb2f5ce` | erfolgreich | [44757451490](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44757451490) |
| Supply-chain audit and SBOM | `58b7fd30d022f2f0b0c5b14fd598f449adb2f5ce` | erfolgreich | [44757451376](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44757451376) |
| CodeQL Python + JavaScript/TypeScript | `58b7fd30d022f2f0b0c5b14fd598f449adb2f5ce` | beide Analysejobs erfolgreich abgeschlossen | [44757451403](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44757451403) |

## Ausgeführte Tests

| Bereich | Tests | Ergebnis |
|---|---:|---|
| Triangulation und LLM-Council-Sicherheitsprüfungen | 20 | bestanden |
| MeshCore-Protokoll, Receiver, persistenter Speicher und Transport | 34 | bestanden |
| Kamera-Runtime, Manifest, Outbox und Source-Client | 25 | bestanden |
| Monitor-Bridge (Node.js) | 32 | bestanden |
| **Summe** | **111** | **alle bestanden** |

Die Kamera-Tests verwenden synthetische Ereignisse und simulierte Kamera-Backends. Die Windows-DirectShow-Auswahl wird im Test simuliert; das ist kein Nachweis einer echten Kamera auf einem Windows-PC.

## Abhängigkeitsprüfung und SBOM

Im Supply-Chain-Lauf wurden folgende Ergebnisse protokolliert:

- MeshCore-Python-Abhängigkeiten: `No known vulnerabilities found`.
- Kamera-Runtime-Abhängigkeiten: `No known vulnerabilities found`.
- Node.js-Abhängigkeiten: `found 0 vulnerabilities`.
- CycloneDX-SBOM für MeshCore-Runtime erzeugt.
- CycloneDX-SBOM für isolierte Kamera-Runtime erzeugt.
- Vulnerability-Reports und SBOM-Dateien wurden als GitHub-Actions-Artefakte gespeichert.

Die Artefakte sind über den [Supply-Chain-Lauf](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44757451376) abrufbar. GitHub-Artefakte haben eine begrenzte Aufbewahrungsdauer und sind keine dauerhafte Projektarchivierung.

Diese Ergebnisse bedeuten ausschließlich, dass die genannten Abhängigkeitsversionen zum Zeitpunkt des Laufs in den verwendeten Advisory-Datenbanken keine bekannten Treffer hatten. Sie beweisen weder Fehlerfreiheit noch Lizenzkompatibilität, vollständige Herkunft oder Sicherheit der gesamten Anwendung.

## Zusätzliche Windows-Prüfung

Am 20.11.2026 wurde anschließend ein Windows-spezifischer Job ergänzt:
- Installation der optionalen CPU-Kamera-Abhängigkeiten auf `windows-latest`.
- `pip check`.
- Syntaxanalyse von `scripts/Start-BeeKeeperCamera.ps1`, ohne das Skript auszuführen.
- Kamera-/Outbox-Tests unter Windows.

Der Lauf auf dem neueren Commit `e6002af26da38e7008bce6c57afb927928b518f7` wird hier erst als bestanden eingetragen, wenn sein GitHub-Actions-Ergebnis abgeschlossen und geprüft ist. Bis dahin gilt die Windows-Prüfung als ausstehend.

## Nicht durch CI nachgewiesen

- Physische Kamera, konkrete RTSP-Kamera oder reale Stream-Stabilität.
- Tatsächliche Art-Erkennungsqualität; kein freigegebenes Modell und keine unabhängige Feldvalidierung.
- Reale Funkverbindung, Antennen-/Frequenz-/Sendeleistungs- und Duty-Cycle-Konformität.
- Feldgenauigkeit und Zuverlässigkeit der Nest-Triangulation.
- Vollständige Lizenz- und Rechtekette des nicht vollständig enthaltenen geerbten Hornet3000-Quellbaums.
- Vollständige Produkt-SBOM für Firmware, Betriebssystem, Modellgewichte, Datensätze, Medien und Hardware.
- Datenschutzrechtliche Freigabe, Gemeinnützigkeitsstatus oder persönliche Haftungsfreistellung.

**Freigabestatus: BLOCKIERT für öffentlichen Pilot, Produktivbetrieb, Installer-/Hardware-Verteilung und Übertragung personenbezogener oder exakter privater Standortdaten.** Maßgeblich bleibt [RELEASE-LEGAL-GATE.md](RELEASE-LEGAL-GATE.md).
