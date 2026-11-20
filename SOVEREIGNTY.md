# Neutralität, digitale Souveränität und Datenkontrolle

## Leitprinzipien

BEEKEEPER3000 soll hersteller- und cloud-unabhängig betrieben werden können. Betreiber behalten Kontrolle über Installation, Konfiguration, Datenhaltung, Zugriffe, Sicherungen und Löschung.

1. **Local-first:** Kernfunktionen sollen lokal im eigenen Netzwerk oder auf eigener Hardware laufen können.
2. **Keine Cloud-Pflicht:** Ein externer Anbieter darf keine Voraussetzung für lokale Erfassung, Auswertung oder Anzeige sein.
3. **Keine ungefragte Telemetrie:** Keine stillen Nutzungs-, Geräte-, Bild-, Audio- oder Standortübertragungen.
4. **Offene Schnittstellen:** Dokumentierte, versionierte APIs und austauschbare Adapter statt proprietärer Bindung.
5. **Datenminimierung:** Nur erforderliche Ereignismetadaten übertragen. Bilder, Audio und GPS bleiben standardmäßig am Ursprungsort.
6. **Betreiberkontrolle:** Betreiber verwalten Schlüssel, Rollen, Aufbewahrung, Export, Sicherung und Löschung.
7. **Nachvollziehbarkeit:** Datenherkunft, Modellversion, Lizenz und Verarbeitungsstatus müssen erkennbar sein.
8. **Interoperabilität:** Export in dokumentierten, maschinenlesbaren Formaten; keine absichtliche Datenbindung.

## Betriebsmodell

- Standardmäßig Loopback- oder privater LAN-Betrieb.
- Fernzugriff nur über abgesichertes VPN oder HTTPS-Reverse-Proxy.
- Keine offenen HTTP-Dienste im öffentlichen Internet.
- Getrennte Zugangsdaten für jede Komponente.
- Geheimnisse ausschließlich in lokaler Umgebung oder einem Secret-Store; niemals im Repository.
- Externe Benachrichtigungs- und Funkdienste sind optional und einzeln aktivierbar.
- Keine Übertragung von Rohbildern, Audio oder GPS durch die aktuelle Monitor-Bridge.

## Datenhoheit und Datenschutz

Der Betreiber muss Zweck, Rechtsgrundlage, Speicherort, Empfänger, Aufbewahrungsfrist und Zugriffsberechtigungen für seine konkrete Installation festlegen. Das Projekt ersetzt keine rechtliche Prüfung und behauptet keine pauschale DSGVO-Konformität.

Vor Produktivbetrieb müssen insbesondere umgesetzt und getestet sein:
- konfigurierbare Aufbewahrungsfristen,
- automatisierte Löschung und nachvollziehbarer Export,
- rollenbasierte Zugriffssteuerung,
- Sicherungs- und Wiederherstellungsverfahren,
- Datenschutzinformationen und ggf. erforderliche Folgenabschätzung.

## Neutralität

Die Software soll keine politische, kommerzielle oder herstellerbezogene Empfehlung erzwingen. Produkt- und Anbieterbezeichnungen dienen ausschließlich der technischen Identifikation von Schnittstellen. Integrationen müssen austauschbar bleiben.

## Aktueller Umsetzungsstand

Diese Datei beschreibt verbindliche Entwicklungsziele. Sie ist keine Behauptung, dass alle genannten Funktionen bereits implementiert sind. Der aktuelle Monitor-Empfänger protokolliert akzeptierte Ereignismetadaten, persistiert sie jedoch noch nicht in der PWA. Automatische Aufbewahrung und Löschung sind im geprüften Quellstand noch nicht vollständig implementiert.
