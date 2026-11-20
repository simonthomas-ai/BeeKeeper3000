# Archiv- und Lizenzherkunftsprüfung — 20.11.2026

## Ergebnis der Byte- und Archivprüfung

Die folgenden Projektarchive wurden aus der persönlichen Projektbibliothek in eine isolierte Prüfumgebung kopiert und lokal geprüft:

| Artefakt | Soll-SHA-256 | Ist-SHA-256 | Ergebnis |
|---|---|---|---|
| `Hornet3000-1.6.0-source.zip` | `ffb4040bf1facf2d08f880b73c06c3933f801e5de2a97a497bfabaa9ca9c007a` | identisch | PASS |
| `Hornet3000-1.6.1-hardened-source.zip` | `44ec3d919b5dcf668d12591814733d315916f42b5b1af3dbc225e8867094cf98` | identisch | PASS |

- Die 1.6.0-Prüfsumme stimmt mit `SHA256SUMS.txt` überein.
- Die 1.6.1-Prüfsumme stimmt mit `Hornet3000-1.6.1-hardened-source.zip.sha256` überein.
- Beide ZIP-Archive bestanden den ZIP-Integritätstest.
- Vor dem Entpacken wurden absolute Pfade und `..`-Pfadeinträge ausgeschlossen.
- 1.6.0 enthält 82 Dateien; 1.6.1 enthält 85 Dateien.

Die Prüfung belegt die Integrität der vorhandenen Archive gegenüber den mitgelieferten Prüfsummen. Sie beweist nicht, wer jede einzelne enthaltene Datei ursprünglich erstellt hat oder ob sämtliche Drittanbieterrechte korrekt sind.

## Lizenzbefund des Originalarchivs 1.6.0

Die Datei `Hornet3000-1.6.0/README.md` enthält die Erklärung:

- Copyright © 2026 Simon Thomas.
- Projektcode unter GPL-3.0-or-later.
- Drittanbieter-Komponenten behalten ihre jeweiligen Rechte und Lizenzen.

Die beigefügte `LICENSE` ist der vollständige GNU GPL Version 3 Lizenztext. SHA-256 der extrahierten Lizenzdatei:

`3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`

Die beigefügte `LICENSES.md` enthält eine Abhängigkeitsliste, weist aber selbst noch offene Versions-, Build- und Drittanbieter-Nachweise aus. Der Lizenztext ist kein automatischer Rechtebeweis für fremde Assets oder Bibliotheken.

## 1.6.1-Härtungsableitung

Die geprüfte 1.6.1-Ableitung enthält `PROVENANCE.md`, `LICENSES.md`, `SECURITY.md` und den GPL-3.0-Lizenztext. Ihre Provenienznotiz erklärt ausdrücklich:

- 1.6.1 wurde aus dem genannten 1.6.0-Archiv abgeleitet.
- Die GPL-3.0-or-later-Erklärung gilt nur für das abgegrenzte Unterprojekt und nicht pauschal für das übergeordnete BeeKeeper3000-Repository.
- `assets/alert.ogg` wurde wegen fehlendem eigenständigem Rechte-/Herkunftsnachweis aus 1.6.1 ausgeschlossen.
- Es sind keine Modellgewichte enthalten.
- Die Node-Transitivabhängigkeiten sind ohne geprüfte Lockfiles nicht reproduzierbar.

Diese Einschränkungen werden beibehalten. Der Ton aus 1.6.0 wird nicht in das aktuelle Projekt übernommen.

## Verbleibende Lizenzentscheidung für das GitHub-Root

Der Quellarchivfund verbessert die Beweislage erheblich. Er ersetzt aber nicht den Datei-für-Datei-Abgleich zwischen dem vollständigen 1.6.0/1.6.1-Quellbaum und dem heutigen BeeKeeper3000-Repository. Ebenso fehlen für einzelne Drittanbieter-Abhängigkeiten, Firmware-/SDK-Builds, Medien, Modelle und Datensätze weiterhin vollständige Artefaktnachweise.

Deshalb bleibt die Root-Lizenz des gesamten GitHub-Repositories bis zum vollständigen Rechteabgleich und zur Bestätigung der Rechteinhaberschaft offen. Die GPL-3.0-or-later-Erklärung darf nicht ohne Weiteres auf alle neuen, externen oder fremden Dateien ausgedehnt werden.

## Nicht freigegeben

- Das Originalarchiv 1.6.0 nicht ungeprüft als fertiges Produkt oder Installer verteilen.
- `assets/alert.ogg` nicht übernehmen oder weitergeben, solange die Asset-Rechte nicht belegt sind.
- Keine Modellgewichte oder Trainingsdaten aus bloßen Code-Repositories ableiten.
- Keine Root-Lizenz oder pauschale Copyright-Erklärung für das gesamte BeeKeeper3000-Repository ohne Rechtekettenprüfung.

## Prüfumfang und Grenzen

Die Prüfung umfasste Archiv-Hashes, ZIP-Integrität, sichere Pfadstruktur, Dateiliste sowie die enthaltenen README-, Lizenz-, Provenienz- und Sicherheitsdokumente. Sie war keine anwaltliche Urheberrechtsprüfung, kein vollständiger Quellcodevergleich, kein Dependency-SBOM und keine Produktfreigabe.

Review date: 2026-11-20.
