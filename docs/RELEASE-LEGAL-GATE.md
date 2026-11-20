# Release- und Pilotfreigabe: rechtliche und organisatorische Mindestprüfung

**Status: BLOCKIERT, bis alle anwendbaren Punkte belegt und freigegeben wurden.**

Diese Checkliste ist ein Governance-Werkzeug, keine Rechtsberatung oder Konformitätsbescheinigung.

## A. Träger und Verantwortlichkeit
- [ ] Betreiber, Hersteller, Maintainer, Datenverantwortliche und lokale Stationsbetreiber sind rollenbezogen geklärt.
- [ ] Geklärt, ob eine natürliche Person, ein Verein oder eine andere juristische Person veröffentlicht, hostet, Hardware vertreibt oder Dienste anbietet.
- [ ] Vertretungsbefugnis, Beschlüsse, Verträge, Konten und Haftpflicht-/Cyberversicherung sind geklärt.
- [ ] Keine Gemeinnützigkeit, Spendenabzugsfähigkeit oder amtliche Partnerschaft wird ohne Nachweis behauptet.
- [ ] Rechts- und Steuerberatung hat Organisationsform, Satzung und tatsächliche Geschäftsführung geprüft.

## B. Lizenz, Herkunft und Lieferkette
- [ ] Eine Lizenz wurde nach Prüfung der gesamten Rechtekette ausgewählt.
- [ ] Lizenzdatei und Copyright-Hinweise passen zu allen enthaltenen Dateien.
- [ ] Jede Abhängigkeit, jedes Modell, jeder Datensatz, jedes Bild und jedes Logo hat Quelle, Version, Lizenz und Weitergabestatus.
- [ ] SBOM ist für alle ausgelieferten Komponenten vollständig; Ausnahmen sind dokumentiert.
- [ ] Keine unklaren oder inkompatiblen Komponenten im Release.
- [ ] Contributor-Rechte und Herkunft aller Beiträge sind dokumentiert.

## C. Datenschutz
- [ ] Datenflusskarte, Zwecke, Rechtsgrundlagen, Rollen und Aufbewahrungsfristen sind dokumentiert.
- [ ] Informationspflichten, Betroffenenrechte, Lösch- und Vorfallprozesse sind implementiert.
- [ ] Auftragsverarbeitung/gemeinsame Verantwortlichkeit ist geregelt, soweit erforderlich.
- [ ] Datenschutz-Folgenabschätzung wurde geprüft und bei Bedarf durchgeführt.
- [ ] Keine Audio-, Personen-, Gesichts- oder Kennzeichenerkennung.
- [ ] Rohbilder, exakte Koordinaten und private Daten verlassen Stationen nicht ohne dokumentierte Rechtsgrundlage und Freigabe.
- [ ] Logs, Backups, Exporte, Browser-Speicher und LLM-Prompts sind einbezogen.

## D. Produktsicherheit und Betrieb
- [ ] Software-/Hardware-Rolle und Anwendbarkeit von CRA, Produkthaftung, Funkanlagen-, EMV- und sonstigem Produktrecht wurden geprüft.
- [ ] Keine unbelegte Aussage zu Zertifizierung, Erkennungsgenauigkeit oder Einsatzreife.
- [ ] Sichere Voreinstellungen, Authentifizierung, Verschlüsselung, Updates, Backup und Wiederherstellung wurden getestet.
- [ ] Sicherheitskontakt und Prozess für koordinierte Schwachstellenoffenlegung sind vorhanden.
- [ ] Notfallabschaltung, Rollback und Datenlöschung sind getestet.
- [ ] Funkparameter, Frequenzen, Leistung und Duty-Cycle sind für die konkrete Konfiguration geprüft.

## E. Fachlicher und praktischer Einsatz
- [ ] Erkennungsqualität wurde mit repräsentativen, rechtmäßig nutzbaren und unabhängig annotierten Daten gemessen.
- [ ] Fehlalarm-/Übersehensraten und Unsicherheiten sind veröffentlicht.
- [ ] Artbestimmung und Nestverdacht bleiben bis zur fachkundigen Bestätigung vorläufig.
- [ ] Triangulation wurde mit bekannten Testpositionen, Zeit-/Winkelkalibrierung und Fehlermaßen geprüft.
- [ ] Keine autonome Nestzerstörung, Giftfreisetzung, Grundstücksbetretung oder andere gefährliche Handlung.
- [ ] Pilotbetreiber, Behördenkontakte, Einsatzgrenzen und Rückmeldeverfahren sind festgelegt.

## F. Kosten und Gemeinnützigkeit
- [ ] Hosting, Domains, CI, Modell-APIs, SMS/Telegram, Karten, Funkgeräte, Backups und Support haben dokumentierte Kostenstellen.
- [ ] Kein Dienst wird als kostenlos bezeichnet, wenn Limits, Zahlungsdaten oder kostenpflichtige Fallbacks bestehen.
- [ ] Spenden, Fördermittel und Sponsoring werden nur über eine rechtlich/steuerlich geprüfte Struktur angenommen.
- [ ] Mittelverwendung, Buchführung und Interessenkonflikte sind dokumentiert.

## Freigabeprotokoll
- Release/Commit:
- Datum:
- Verantwortliche juristische Person/Organisation:
- Rechtsprüfung (Name/Kanzlei, Datum, Umfang):
- Datenschutzprüfung:
- Lizenz-/SBOM-Prüfung:
- Sicherheitsprüfung:
- Fachliche Pilotfreigabe:
- Offene Risiken und akzeptierte Restgefahren:
- Freigabeentscheidung: BLOCKIERT / FREIGEGEBEN

Checkboxen nur mit konkretem Nachweis abhaken. Bei ungeklärter Haftungs-, Datenschutz-, Lizenz- oder Produktsicherheitsfrage bleibt der Release blockiert.
