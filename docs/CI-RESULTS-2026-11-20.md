# CI-, Lieferketten- und Herkunftsprüfbericht — 20.11.2026

**Aktueller geprüfter Main-Stand:** `55c4f601e9d55ddbec2aaafe9e1b8263b2341b69`

Die Ergebnisse wurden direkt aus GitHub Actions, Job-Protokollen und den erzeugten Audit-/SBOM-Artefakten geprüft. Sie gelten nur für die jeweiligen Commits und ausdrücklich erfassten Komponenten.

## 1. Verifizierte GitHub-Actions-Läufe

| Workflow | Commit | Ergebnis | Lauf |
|---|---|---|---|
| Quality gates (Linux + Windows) | `55c4f601e9d55ddbec2aaafe9e1b8263b2341b69` | alle 4 Jobs erfolgreich | [44760615794](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44760615794) |
| CodeQL Python + JavaScript/TypeScript | `55c4f601e9d55ddbec2aaafe9e1b8263b2341b69` | beide Analysejobs erfolgreich abgeschlossen | [44760615851](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44760615851) |
| Windows station launcher validation | `cb092e30e0f63517bd98a49ae5e64b794cd140fe` | PowerShell-Prüfung und Backup-/Restore-Test erfolgreich | [44760606808](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44760606808) |
| Supply-chain audit and SBOM | `e59c0989dc452674cba7666a8725e82de2a42135` | alle 5 Jobs erfolgreich | [44760358858](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44760358858) |
| Network reference tests | `66c9e030401ec3939fd9f5c7c8e011e59bc89626` | alle 3 Jobs erfolgreich | [44759998784](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44759998784) |

CodeQL-Analysejobs erfolgreich bedeutet nicht automatisch, dass null offene Code-Scanning-Alerts existieren. Die Alert-Liste muss im GitHub-Sicherheitsbereich separat geprüft werden.

## 2. Automatisierte Testausführungen

### Quality gates

| Bereich | Ausführungen | Ergebnis |
|---|---:|---|
| Python-Kern, Triangulation und LLM-Sicherheitsprüfungen | 20 | bestanden |
| MeshCore-Protokoll, Receiver, persistenter Speicher und Transport | 34 | bestanden |
| Kamera-Runtime, Modellmanifest, ONNX-Ausgabe, Evaluator, Outbox und Source-Client auf Linux | 37 | bestanden |
| Dieselben Kamera-/Outbox-Tests auf Windows | 37 | bestanden |
| Monitor-Bridge (Node.js) | 32 | bestanden |
| **Gesamt** | **160** | **alle bestanden** |

Die Kamera-Testfälle wurden auf Linux und Windows wiederholt; 160 sind Testausführungen, nicht 160 unterschiedliche Testfälle.

### Network reference tests

| Bereich | Ausführungen | Ergebnis |
|---|---:|---|
| Python-Netzwerk-, API-, Backup-, Kamera- und Stations-Preflight-Tests | 77 | bestanden |
| Read-only Stations-Preflight | 7 | bestanden |
| MeshCore-Protokoll, Receiver, persistenter Speicher, Transport und Hardware-Probe | 39 | bestanden |
| Monitor-Bridge (Node.js) | 32 | bestanden |
| **Gesamt** | **155** | **alle bestanden** |

Diese Tests verwenden synthetische Ereignisse, simulierte Backends und/oder lokale Testdienste. Sie ersetzen keine physische Kamera-, Funk- oder Feldabnahme.

## 3. Supply-Chain-Audit und SBOM

Der aktuelle Supply-Chain-Lauf erzeugte vier Artefakte:

- CycloneDX-SBOM für Kamera-Runtime
- CycloneDX-SBOM für MeshCore-Runtime
- Python-Abhängigkeitsbericht für Kamera-Runtime
- Python-Abhängigkeitsbericht für MeshCore-Runtime

Ergebnisse der tatsächlich heruntergeladenen Audit-Berichte:

- Kamera-Runtime: 5 geprüfte Python-Pakete, keine bekannten Advisory-Treffer.
- MeshCore-Runtime: 8 geprüfte Python-Pakete, keine bekannten Advisory-Treffer.
- Node.js: `npm audit` erfolgreich, 0 gemeldete Schwachstellen.
- Beide CycloneDX-JSON-Dateien wurden erzeugt und syntaktisch validiert.

Die Artefakte sind im [Supply-Chain-Lauf](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44760358858) abrufbar. GitHub-Artefakte sind zeitlich befristet.

**Wichtige Einschränkung:** Die SBOMs sind keine vollständige Lizenzfreigabe. In den erzeugten CycloneDX-Daten fehlen Lizenzmetadaten bei mehreren Komponenten (unter anderem Teilen des MeshCore-Graphen und `protobuf`). Die Audits erfassen nur die deklarierten Dependency-Graphen; sie erfassen nicht das geerbte C++-Projekt, Betriebssystempakete, Kamera-/Funkfirmware, Modellgewichte, Trainingsdaten, Medien oder Hardware.

## 4. Umgesetzte technische Härtungen

- Modellmanifest verlangt jetzt SHA-256, HTTPS-Quellnachweis, HTTPS-Lizenzbeleg, verantwortlichen Prüfer, zeitzonenbehaftetes Prüfdatum und explizite Nutzungs-/Weitergaberechte.
- ONNX-Detektor hat Tests für normalisierte und Matrix6-Ausgabe, Tensor-/Graphnamen, ungültige Boxen, unbekannte Klassen und Konfidenzschwellen.
- `camera/evaluate_detections.py` berechnet pro Klasse TP/FP/FN, Precision, Recall, F1 und AP bei einem IoU-Schwellwert für unabhängig annotierte Held-out-Daten.
- Netzwerk-/Dateiquellen verwenden angeforderte 5-Sekunden Open-/Read-Timeouts; OpenCV-Builds ohne diese Unterstützung werden abgelehnt, statt unbeschränkte Netzwerk-Reads zu verwenden.
- SQLite-Outbox-, Backup- und Restore-Verbindungen werden deterministisch geschlossen.
- `scripts/Test-BeeKeeperCamera.ps1` führt einen Ein-Frame-Hardwaretest mit verborgener Quelleingabe aus. Die RTSP-URL wird nicht als Kommandozeilenargument ausgegeben, und das Testbild wird nicht gespeichert.
- PowerShell-Parser- und Windows-Backup-/Restore-Validierung liefen erfolgreich.

## 5. Verifizierte Quellarchiv-Herkunft

Die Archive `Hornet3000-1.6.0-source.zip` und `Hornet3000-1.6.1-hardened-source.zip` wurden gegen ihre jeweiligen SHA-256-Dateien geprüft; ZIP-Integrität und Pfadstruktur waren erfolgreich. Die abgegrenzte 1.6.0-Projektcode-Erklärung nennt GPL-3.0-or-later und © 2026 Simon Thomas. Die 1.6.1-Provenienznotiz beschränkt diese Erklärung ausdrücklich auf das Unterprojekt.

Details: [Archiv- und Lizenzherkunftsprüfung](ARCHIVE-PROVENANCE-AUDIT-2026-11-20.md). Die Root-Lizenz des gesamten BeeKeeper3000-Repositories bleibt ungeklärt, bis der aktuelle Baum vollständig abgeglichen und die Rechtekette bestätigt ist.

## 6. Nicht durch CI nachgewiesen

- Physische Kamera, konkreter RTSP-Stream und zweistündige Stabilität.
- Tatsächliche Art-Erkennungsqualität; es ist kein freigegebenes ONNX-Modell vorhanden.
- Unabhängig annotierter, repräsentativer Feldtestdatensatz und veröffentlichte Fehlalarm-/Übersehensraten.
- Reale Funkverbindung, Antennen-/Frequenz-/Sendeleistungs- und Duty-Cycle-Konformität.
- Feldgenauigkeit der Triangulation mit bekannten Zielpositionen und kalibrierten Stationen.
- Vollständige Produkt-SBOM und Lizenzmetadaten aller Komponenten.
- Vollständige Rechtekette des gesamten aktuellen Repository-Baums.
- Datenschutzrechtliche Betreiberfreigabe, Gemeinnützigkeit, Rechtsgutachten oder persönliche Haftungsfreistellung.

**Freigabestatus: BLOCKIERT für öffentlichen Pilot, Produktivbetrieb, Installer-/Hardware-Verteilung und Übertragung personenbezogener oder exakter privater Standortdaten.** Maßgeblich bleibt [RELEASE-LEGAL-GATE.md](RELEASE-LEGAL-GATE.md).
