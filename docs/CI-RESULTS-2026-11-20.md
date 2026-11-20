# CI- und Lieferketten-Prüfbericht — 20.11.2026

**Letzter vollständig geprüfter Quellstand:** `743752b97d968f40a7c5167946fb7cc82ae45ed1`

Die folgenden Ergebnisse wurden direkt aus GitHub Actions und den Job-Protokollen abgerufen. Sie gelten für die genannten Commits und den ausdrücklich erfassten Umfang.

## Verifizierte Workflow-Läufe

| Workflow | Commit | Ergebnis | Lauf |
|---|---|---|---|
| Quality gates (Linux + Windows) | `743752b97d968f40a7c5167946fb7cc82ae45ed1` | alle 4 Jobs erfolgreich | [44758077360](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44758077360) |
| Network reference tests | `743752b97d968f40a7c5167946fb7cc82ae45ed1` | alle 3 Jobs erfolgreich | [44758077536](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44758077536) |
| CodeQL Python + JavaScript/TypeScript | `743752b97d968f40a7c5167946fb7cc82ae45ed1` | beide Analysejobs erfolgreich abgeschlossen | [44758077509](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44758077509) |
| Supply-chain audit and SBOM | `58b7fd30d022f2f0b0c5b14fd598f449adb2f5ce` | alle 5 Jobs erfolgreich | [44757451376](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44757451376) |

## Ausgeführte Testmengen

### Quality gates

| Bereich | Testausführungen | Ergebnis |
|---|---:|---|
| Triangulation und LLM-Council-Sicherheitsprüfungen | 20 | bestanden |
| MeshCore-Protokoll, Receiver, persistenter Speicher und Transport | 34 | bestanden |
| Kamera-Runtime, Manifest, Outbox und Source-Client auf Linux | 25 | bestanden |
| Dieselben Kamera-/Outbox-Tests auf Windows | 25 | bestanden |
| Monitor-Bridge (Node.js) | 32 | bestanden |
| **Summe** | **136 Ausführungen** | **alle bestanden** |

Die Kamera-Testfälle wurden auf Linux und Windows wiederholt; daher sind 136 Testausführungen nicht 136 unterschiedliche Testfälle.

### Network reference tests

| Bereich | Testausführungen | Ergebnis |
|---|---:|---|
| Python-Netzwerk-, API-, Backup-, Kamera- und Stations-Preflight-Tests | 77 | bestanden |
| Read-only Stations-Preflight | 7 | bestanden |
| MeshCore-Protokoll, Receiver, persistenter Speicher, Transport und Hardware-Probe | 39 | bestanden |
| Monitor-Bridge (Node.js) | 32 | bestanden |
| **Summe** | **155 Ausführungen** | **alle bestanden** |

## Windows-Befund und Korrektur

Der erste Windows-Lauf deckte einen echten Portabilitätsfehler auf: SQLite-Verbindungen wurden nach Transaktionen nicht deterministisch geschlossen; Windows konnte dadurch temporäre Datenbanken nicht löschen. Zusätzlich wurde ein Linux-Gerätepfad beim plattformübergreifenden Test normalisiert.

Korrekturen:
- SQLite-Outbox-Verbindungen werden nach Commit/Rollback immer geschlossen.
- Backup- und Restore-Verbindungen werden ebenfalls explizit geschlossen.
- Das Backup-Testfixture schließt seine eigene SQLite-Verbindung.
- Linux-Gerätepfade bleiben im simulierten Linux-Backend-Test unverändert.

Der anschließende Quality-Gates-Lauf auf Commit `743752b...` bestand einschließlich Windows-Job, PowerShell-Syntaxprüfung und 25 Kamera-/Outbox-Tests.

## Abhängigkeitsprüfung und SBOM

Im Supply-Chain-Lauf wurden folgende Ergebnisse protokolliert:

- MeshCore-Python-Abhängigkeiten: `No known vulnerabilities found`.
- Kamera-Runtime-Abhängigkeiten: `No known vulnerabilities found`.
- Node.js-Abhängigkeiten: `found 0 vulnerabilities`.
- CycloneDX-SBOM für MeshCore-Runtime erzeugt.
- CycloneDX-SBOM für isolierte Kamera-Runtime erzeugt.
- Vulnerability-Reports und SBOM-Dateien als GitHub-Actions-Artefakte gespeichert.

Die Artefakte sind über den [Supply-Chain-Lauf](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44757451376) abrufbar. GitHub-Artefakte haben eine begrenzte Aufbewahrungsdauer.

Der Supply-Chain-Lauf fand auf Commit `58b7fd3...` statt. Die danach erfolgten Änderungen betrafen Kamera-/SQLite-Implementierung und Workflow-Prüfungen, nicht die in diesem Lauf geprüften Dependency-Manifeste. Das ist kein vollständiger Produkt-SBOM-Nachweis.

## CodeQL-Einordnung

Die Python- und JavaScript/TypeScript-Analysejobs wurden erfolgreich abgeschlossen und die Analyseergebnisse hochgeladen. Ein erfolgreicher CodeQL-Lauf ist **keine Aussage, dass es null Alerts gibt**. Offene Code-Scanning-Befunde müssen im GitHub-Sicherheitsbereich separat geprüft, bewertet und gegebenenfalls behoben werden.

## Nicht durch CI nachgewiesen

- Physische Kamera, konkrete RTSP-Kamera oder reale Stream-Stabilität.
- Tatsächliche Art-Erkennungsqualität; kein freigegebenes Modell und keine unabhängige Feldvalidierung.
- Reale Funkverbindung, Antennen-/Frequenz-/Sendeleistungs- und Duty-Cycle-Konformität.
- Feldgenauigkeit und Zuverlässigkeit der Nest-Triangulation.
- Vollständige Lizenz- und Rechtekette des nicht vollständig enthaltenen geerbten Hornet3000-Quellbaums.
- Vollständige Produkt-SBOM für Firmware, Betriebssystem, Modellgewichte, Datensätze, Medien und Hardware.
- Datenschutzrechtliche Freigabe, Gemeinnützigkeitsstatus oder persönliche Haftungsfreistellung.

**Freigabestatus: BLOCKIERT für öffentlichen Pilot, Produktivbetrieb, Installer-/Hardware-Verteilung und Übertragung personenbezogener oder exakter privater Standortdaten.** Maßgeblich bleibt [RELEASE-LEGAL-GATE.md](RELEASE-LEGAL-GATE.md).
