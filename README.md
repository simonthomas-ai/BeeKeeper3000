# BEEKEEPER3000

**Lokale, herstellerneutrale und datenhoheit-orientierte Plattform für Beobachtung und Ereignisverarbeitung rund um Bienenstände und Insekten.**

Dieses Repository verbindet die Quellbasis Hornet3000 Wächter 1.6.0 mit einem dokumentierten Adapter zum bestehenden Beekeeper-Monitor. Die Bezeichnung BEEKEEPER3000 beschreibt das Integrationsziel; sie bedeutet nicht, dass bereits alle geplanten Erkennungs-, Sensor- und Dashboard-Funktionen vollständig umgesetzt sind.

## Grundsätze

- Local-first und ohne verpflichtende Cloud betreibbar.
- Offene, dokumentierte Schnittstellen und austauschbare Adapter.
- Keine ungefragte Telemetrie.
- Bild-, Audio- und GPS-Daten werden durch die aktuelle Monitor-Bridge nicht übertragen.
- Betreiberkontrolle über Schlüssel, Datenhaltung und externe Integrationen.
- Lizenz- und Herkunftshinweise bleiben erhalten.

Details: [SOVEREIGNTY.md](SOVEREIGNTY.md), [SECURITY.md](SECURITY.md), [PROVENANCE.md](PROVENANCE.md), [LICENSES.md](LICENSES.md).

## Bundesweites Velutina-Messnetz

Die technische Zielarchitektur, die Grenzen von LoRa/Freenet und die Betriebs-/Datenschutzanforderungen stehen in [NETWORK-ARCHITECTURE.md](NETWORK-ARCHITECTURE.md). Ein erster, dependency-freier Peilungs-Triangulationsbaustein mit Tests liegt unter [network/](network/). Er berechnet einen Suchhinweis aus mindestens drei zeitlich synchronisierten Peilungen; er bestätigt kein Nest und ersetzt keine fachliche Prüfung.

## Monitor-Anbindung

Die lokale Adapter-Komponente in [monitor-bridge/](monitor-bridge/) liest Ereignisse aus Hornet3000 und sendet ausgewählte Metadaten an den authentifizierten Eingang von [Beekeeper-Monitor](https://github.com/simonthomas-ai/Beekeeper-Monitor).

Die Schnittstelle ist transportseitig vorbereitet. Der vorhandene Monitor-Empfänger validiert und protokolliert Ereignisse, speichert sie derzeit aber noch nicht in der PWA-Datenbank und zeigt sie nicht im Dashboard an. Eine vollständige End-to-End-Integration ist daher noch nicht bestätigt.

## Build und Tests

Der geprüfte Quellstand ließ sich als C++ Release-Build kompilieren. Die Core-Tests bestanden (1/1); die vorhandenen Freenet-/MeshCore-Bridge-Tests bestanden (10/10). Die zusätzlichen Tests des Monitor-Adapters sind unter `monitor-bridge/` abgelegt.

ONNX Runtime war in der geprüften Umgebung nicht verfügbar. Eine aktive KI-Inferenz oder eine belastbare Erkennungsgenauigkeit wird deshalb nicht behauptet.

## Sicherheit und Datenschutz

Keine echten Zugangsdaten, Kamerapasswörter, privaten Aufnahmen, Audiodateien oder GPS-Spuren einchecken. Dienste lokal oder hinter VPN und HTTPS betreiben. Vor einem realen Kameraeinsatz sind Speicherfristen, Löschung, Zugriffsrechte und die konkrete datenschutzrechtliche Situation zu prüfen.

## Herkunft und Lizenz

Die zugrunde liegende Quellbasis ist Hornet3000 Wächter 1.6.0. Ursprüngliche Lizenz- und Copyright-Hinweise bleiben erhalten. Es wird keine pauschale Neulizenzierung oder vollständige rechtliche Freigabe behauptet. Siehe [PROVENANCE.md](PROVENANCE.md), [LICENSES.md](LICENSES.md) und [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
