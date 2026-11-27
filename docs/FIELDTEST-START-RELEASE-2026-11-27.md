# Begrenzte Feldtestfreigabe – VespaGuard ohne KI

Stand: 27.11.2026  
Geltungsbereich: ausschließlich ein beaufsichtigter, lokaler No-AI-Feldtest.

## Freigabeumfang

Der Betreiber kann einen begrenzten Funktionstest am eigenen Bienenstand durchführen, sofern die lokalen Voraussetzungen und die Stop-Kriterien unten erfüllt sind:

- lokale Basisdienste (Monitor, Source API und Bridge) auf einem privaten Stationsgerät;
- optional genau ein bewusst ausgelöster Kamera-Verbindungstest (ein Frame lesen, danach Kamera schließen; kein Bild speichern);
- manuelle Beobachtungsnotizen in der lokalen Mobile-PWA, ohne automatische Synchronisierung;
- Prüfung von Offline-Verhalten, Neustart, lokaler Speicherung und Bedienbarkeit;
- Testdaten bleiben lokal und werden nicht in öffentliche Issues, Repositories, Actions-Artefakte oder Chats übertragen.

Dies ist eine **begrenzte technische Feldtestfreigabe**, keine Produktivfreigabe.

## Ausdrücklich nicht freigegeben

- automatische KI-Inferenz, Artenbestimmung oder produktive Modellalarme;
- fremde Modellgewichte oder Trainingsbilder ohne individuelle Rechte- und Lizenzprüfung;
- Import manueller PWA-Beobachtungen als Kameraereignisse oder automatische KI-/Warnereignisse; manuelle Sichtungen dürfen nur als eigener Typ `manual_observation` über den geprüften lokalen v2-Importer übernommen werden.
- öffentliche GitHub-Pages-Veröffentlichung, öffentliche Ports, Portweiterleitungen oder externe RTSP-Erreichbarkeit;
- Daueraufnahme, Audioaufzeichnung, automatische GPS-Erfassung oder Übermittlung von Fotos/Koordinaten;
- Nestlokalisierung oder Bekämpfungsentscheidungen auf Basis dieses Systems.

## Startvoraussetzungen vor Ort

- [ ] Betreiber und verantwortliche Testperson sind festgelegt; Test findet unter Aufsicht statt.
- [ ] Testgerät, Betriebssystem, Kamera und Firmware sind dokumentiert.
- [ ] Monitor-, Source-API- und Bridge-Dienste laufen lokal; Stationsdiagnose wurde ausgeführt und alle Fehler bewertet.
- [ ] API-Schlüssel wurden lokal und außerhalb von Shell-Historie, Logs und Repository eingerichtet.
- [ ] Netzwerkzugriff ist auf Loopback bzw. ein ausdrücklich geprüftes privates LAN beschränkt; keine öffentliche Freigabe.
- [ ] Geräte-/Datenträgerverschlüsselung und Zugriffsschutz sind aktiv; Exporte/Backups werden wie sensible Daten behandelt.
- [ ] Fotos, GPS und Freitextnotizen bleiben beim ersten Versuch ausgeschaltet, sofern sie nicht für eine konkrete Testfrage zwingend erforderlich sind.
- [ ] Es ist klar, dass ein einzelner erfolgreicher Frame nur die Kameraverbindung belegt, nicht Erkennung oder Dauerbetrieb.

## Durchführung

1. Zunächst die dokumentierte Validate-only-Prüfung aus `docs/NO-MODEL-FIELDTEST.md` durchführen.
2. Basisdienste starten und `scripts/station_doctor.py --no-model` ausführen. Der Schalter ignoriert auch ein gesetztes `BEEKEEPER_MODEL_MANIFEST`; Fehler nicht übergehen.
3. Optional den dokumentierten Einzelbild-Kameratest mit `--no-model` ausführen. Es wird kein Modell geladen und keine Inferenz ausgeführt.
4. Manuelle Sichtungen in der Mobile-PWA erfassen. Standardmäßig bleiben sie lokal in der Browser-IndexedDB; es gibt keine automatische Synchronisierung.
5. Nur wenn die lokale Bridge-Übergabe ausdrücklich Teil dieses Tests ist, darf der Betreiber einen v2-Metadatenexport bewusst über den dedizierten Importer übernehmen (`scripts/Import-BeeKeeperMobileExport.ps1` unter Windows oder `python3 scripts/import_mobile_export.py <export.json>` unter Linux). Der Importer verlangt `origin=manual_observation` und sendet ausschließlich die sieben begrenzten Metadatenfelder an die feste Loopback-Source-API. Fotos, GPS, Kompasswerte, Notizen und Zugangsdaten werden nicht exportiert. Die Bridge erhält den eigenen Typ `manual_observation`; daraus entstehen weder Kameraerkennung noch Hornissenwarnung. Keine künstlichen Ereignisse einspeisen; den API-Schlüssel nur aus einer geschützten lokalen Prozessumgebung beziehen, niemals als Befehlsargument oder in Shell-Historie/Logs.
6. Nur technische Beobachtungen notieren: Gerät/Revision, Betriebssystem, Kamera/Firmware, Verbindungsart, Start-/Endzeit, Doctor-Ergebnis, Frame erfolgreich ja/nein, Abbrüche und Bedienprobleme.
7. Dienste nach dem Test kontrolliert stoppen. Nicht mehr benötigte lokale Testbilder und Exporte nach Prüfung sicher löschen.

## Sofortige Abbruchkriterien

Test beenden und keine weiteren Daten erfassen, wenn:

- Fotos, Audio, GPS, Zugangsdaten oder private Notizen unerwartet das Gerät verlassen;
- Zugangsdaten in Logs, URLs, Shell-Historie oder Diagnosen erscheinen;
- ein manuelles Ereignis als automatische Kameraerkennung gespeichert wird;
- ein Modell unerwartet geladen oder Inferenz ausgeführt wird;
- ein Dienst öffentlich erreichbar ist oder ein Port unerwartet nach außen geöffnet wurde;
- Datenverlust, unkontrolliertes Wachstum der Warteschlange oder instabiles Geräteverhalten auftritt.

Bei einem Abbruch keine sensiblen Logs öffentlich hochladen. Fehler lokal sichern und vor einer erneuten Durchführung prüfen.

## Ergebnis richtig einordnen

Ein bestandener No-AI-Feldtest belegt ausschließlich die konkret getesteten Stations-, Kamera-Verbindungs-, PWA- und Bedienfunktionen auf genau diesem Gerät. Er belegt **nicht**:

- Vespa-velutina-Erkennung, Varroa-Erkennung oder irgendeine andere KI-Leistung;
- Genauigkeit, Recall, Fehlalarmrate oder Eignung als Warnsystem;
- Dauerbetrieb, Nacht-/Wettertauglichkeit, Hardwarekompatibilität anderer Geräte;
- vollständige DSGVO-Konformität oder Freigabe für öffentliche/kommerzielle Nutzung.

Für eine spätere KI-Freigabe bleiben ein rechtlich freigegebener Datensatz, ein konkret gehashtes und lizenzgeprüftes Modell, geprüfte Ein-/Ausgabesemantik, unabhängiger Feld-Holdout, fachliche Evaluation und dokumentierte Hardwareabnahme zwingend.

## Verbindliche Referenzen

- [No-AI-Feldtest: vollständige Startsequenz](NO-MODEL-FIELDTEST.md)
- [Kamera- und Modellabnahme](CAMERA-ACCEPTANCE.md)
- [Datenlebenszyklus und Datenschutz](https://github.com/simonthomas-ai/Beekeeper-Monitor/blob/main/docs/DATA-LIFECYCLE-AND-PRIVACY.md)
- [Beekeeper-Monitor: Status und Grenzen](https://github.com/simonthomas-ai/Beekeeper-Monitor/blob/main/STATUS.md)

Diese Freigabe gilt nur für den oben beschriebenen lokalen No-AI-Pilot. Sie aktiviert keine KI und keine öffentliche Bereitstellung.
