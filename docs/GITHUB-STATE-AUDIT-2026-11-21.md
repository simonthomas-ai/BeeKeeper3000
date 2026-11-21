# GitHub-Status- und Auditbericht – 21.11.2026

## Prüfbereich

Geprüft wurden die beiden verbundenen VespaGuard-Repositories:

- BeeKeeper3000: https://github.com/simonthomas-ai/BeeKeeper3000
- Beekeeper-Monitor: https://github.com/simonthomas-ai/Beekeeper-Monitor

Die Repository-Bäume, aktuelle Hauptbranch-Commits, Pull Requests, offene Issues, Workflows, relevante Quell- und Konfigurationsdateien sowie die jüngsten CI-Protokolle wurden eingesehen.

## Verifizierte Hauptbranch-Stände

| Repository | Hauptbranch-Commit | Letzter bestätigter Stand |
|---|---|---|
| BeeKeeper3000 | `33f232bebfda97e7334a3a7b4533a4eee19865dd` | Quality Gates und CodeQL erfolgreich |
| Beekeeper-Monitor | `360e668d4aaf27c27655986e2f7bfc2f108fc167` | Ein-Klick-Gesamttest erfolgreich |

BeeKeeper3000 CI-Nachweise:

- Quality Gates: https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44822224541
- CodeQL: https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44822224538

Beekeeper-Monitor CI-Nachweis nach Merge von PR #190:

- Ein-Klick-Gesamttest: https://github.com/simonthomas-ai/Beekeeper-Monitor/actions/runs/44881193728

## Umgesetzte Änderung

PR #190 wurde in Beekeeper-Monitor gemergt:

https://github.com/simonthomas-ai/Beekeeper-Monitor/pull/190

Merge-Commit: `360e668d4aaf27c27655986e2f7bfc2f108fc167`

Enthaltene Änderungen:

- Der Bildimport-/Lizenztestblock verwendet explizit Bash mit `set -euo pipefail`.
- Ein Fehler in einem frühen Unittest kann nicht mehr durch einen später erfolgreichen Test verdeckt werden.
- Der Duplikat-Regressionstest prüft zusätzlich, dass beide Kandidaten im Ergebnis gezählt werden.

Der veraltete PR #186 wurde als durch PR #190 ersetzt geschlossen.

## KI- und Datenstatus

Die Monitor-PWA, lokalen Integrationsverträge, Bildimport-Sicherheitsprüfungen, Browser-/WebKit-/iPhone-Tests, Taxonomieprüfung und Bridge-Integration sind softwareseitig erfolgreich geprüft.

Die KI-Freigabe bleibt ausdrücklich BLOCKIERT:

- Der Ordner `datasets/beekeeper/` ist im Repository nicht vorhanden.
- Ein vollständiges Provenienzmanifest pro Bild fehlt.
- Fachlich freigegebene siebenklassige Annotationen fehlen.
- Es gibt keine freigegebenen und unabhängig validierten Modellgewichte.
- Eine reale Erkennungsgenauigkeit ist nicht nachgewiesen.

Im Ein-Klick-Gesamttest werden fehlende Trainingsdaten und Review-Annotationen als gesonderte blockierte KI-Reifegrade ausgewiesen. Der erfolgreiche Software-Gesamttest ist keine Modell- oder Einsatzfreigabe.

Sieben Zielklassen:

1. `vespa_velutina`
2. `vespa_crabro`
3. `other_vespidae`
4. `apis_mellifera`
5. `bombus_spp`
6. `syrphidae`
7. `other_insect`

Offene Datengrundlagen- und Freigabearbeit:

https://github.com/simonthomas-ai/Beekeeper-Monitor/issues/191

## GitHub-Governance

Die Branch-Metadaten zeigten zum Prüfzeitpunkt, dass die jeweiligen `main`-Branches nicht geschützt waren. Ein GitHub-Issue hält die erforderliche Administrationsarbeit fest:

https://github.com/simonthomas-ai/BeeKeeper3000/issues/84

Dieses Issue ist offen. Branch-Schutzregeln sind mit diesem Audit nicht gesetzt worden.

## Technische und operative Grenzen

Folgende Nachweise bleiben unabhängig von grüner Software-CI erforderlich:

- Physische Kamera-/Dauerlauftests mit konkreter Hardware.
- MeshCore-Funkbetrieb mit realen Geräten, Antennen und Relais.
- Feldkalibrierung und Genauigkeitsmessung der Triangulation.
- Vollständige Rechtekette, Lizenz- und Produkt-SBOM.
- Einsatzbezogene Datenschutz- und Betreiberprüfung.
- Hardware-, Wiederherstellungs- und Pilotabnahme.

Es gibt derzeit keine freigegebene Aussage über bundesweite Funkabdeckung, validierte Nestlokalisierung oder eine einsatzfertige KI-Erkennung.

## Zugangsdaten und Autorisierung

Der GitHub-Zugriff erfolgt über die verbundene GitHub-Integration. Persönliche Zugangstoken, Passwörter und private Schlüssel werden nicht in diesem Repository gespeichert. Dieser Bericht enthält keine Geheimnisse oder privaten Standortdaten.

## Ergebnis

Die lokale Softwarearchitektur und die automatisierten Softwaretests sind weiter stabilisiert. Die offenen Aufgaben sind jetzt konkret nachverfolgbar. Das System ist weiterhin ein Entwicklungs- und Beobachtungssystem; die KI-, Hardware-, Funk-, Datenschutz- und Release-Freigaben sind nicht abgeschlossen.

Prüfdatum: 21.11.2026
