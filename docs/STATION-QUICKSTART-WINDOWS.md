# BeeKeeper3000 – lokale Station unter Windows 10/11 einrichten

Diese Anleitung startet die drei bereits implementierten Basisdienste:
1. Lokale Beekeeper-Monitor-PWA mit authentifiziertem SQLite-Empfänger.
2. Authentifiziertes SQLite-Quelljournal von BeeKeeper3000.
3. Node.js-Bridge von BeeKeeper3000 mit verpflichtender Cursor-Paginierung.

**Nicht enthalten:** automatische Installation von Kameratreibern, Start des ursprünglichen Hornet3000-C++-Dienstes, MeshCore-Funk oder eines Freenet-Knotens. Die optionale ONNX-Kamera benötigt ein lokal beschafftes, rechtlich geprüftes Modell und wird separat gestartet; siehe [Kameradokumentation](../camera/README.md).

## Voraussetzungen
- Windows 10 oder 11 mit Benutzerprofil.
- Python 3.11 oder neuer.
- Node.js 20 oder neuer.
- Lokale Kopien beider Repositories, möglichst als Nachbarverzeichnisse `BeeKeeper3000` und `Beekeeper-Monitor`.
- PowerShell 5.1 oder neuer.

## Starten
PowerShell im Verzeichnis `BeeKeeper3000` öffnen:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\Start-BeeKeeperStation.ps1 -MonitorRepo "C:\path\to\Beekeeper-Monitor"
```

Liegt `Beekeeper-Monitor` direkt neben `BeeKeeper3000`, kann `-MonitorRepo` entfallen.

Beim ersten Start werden drei unabhängige Zufallsschlüssel erzeugt und mit Windows-DPAPI als geschützte SecureString-Werte gespeichert:

`%LOCALAPPDATA%\BeeKeeper3000\station-secrets.clixml`

Nur das aktuelle Windows-Benutzerkonto kann sie entschlüsseln. Die Datei nicht auf andere Benutzerkonten oder Rechner kopieren. Sie muss bei Neustarts erhalten bleiben: Wird der Signaturschlüssel ersetzt, während ein alter Bridge-Prüfpunkt existiert, ist dieser ungültig.

Der Starter setzt restriktive Zugriffsrechte für Benutzer und SYSTEM auf das lokale Datenverzeichnis. SQLite-Datenbanken, Bridge-Status und Protokolle liegen unter `%LOCALAPPDATA%\BeeKeeper3000\`. Sie sind nicht anwendungsseitig verschlüsselt; BitLocker oder ein verschlüsseltes Laufwerk verwenden.

## PWA-Anmeldeschlüssel sicher übernehmen
Der Monitor-Empfangsschlüssel liegt ausschließlich DPAPI-geschützt in der lokalen Schlüsseldatei. Für die Anmeldung kann er gezielt in die Windows-Zwischenablage kopiert werden:

```powershell
.\scripts\Copy-BeeKeeperStationToken.ps1
```

Den Schlüssel nur im Feld „Lokaler Empfangsschlüssel“ unter http://127.0.0.1:8765/ einfügen. Die PWA hält ihn nur im Arbeitsspeicher. Anschließend die Zwischenablage leeren:

```powershell
Set-Clipboard -Value ''
```

Für diesen Vorgang keine Zwischenablage-Synchronisierung oder -Historie verwenden. Schlüssel niemals in Chats, Tickets, Screenshots, Protokolle oder fremde Webseiten einfügen.

## Öffnen und beenden
Die lokale PWA auf demselben Rechner öffnen: http://127.0.0.1:8765/

Die Quell-API ist ausschließlich lokal auf Port 8787 erreichbar. Keinen der beiden HTTP-Dienste ins öffentliche Internet stellen.

Mit diesem Befehl nur die vom Starter erzeugten Prozesse beenden:

```powershell
.\scripts\Stop-BeeKeeperStation.ps1
```

Das Skript prüft vor dem Beenden die aufgezeichnete ausführbare Datei und Befehlszeile. Eine anderweitig wiederverwendete Prozess-ID wird nicht blind beendet.

Der Starter verwaltet Prozesse pro Benutzer, ist aber **kein Windows-Dienst und kein automatischer Autostart**. Nach der Anmeldung erneut starten, sofern die optionale Autostart-Aufgabe nicht eingerichtet wurde. Protokolle bleiben lokal gespeichert; für Dauerbetrieb Aufbewahrungs- und Rotationsregeln festlegen.

## Optionale Kamera
Vor dem KI-Betrieb mit `scripts/Test-BeeKeeperCamera.ps1` einen sicheren Einzelbild-Hardwaretest durchführen (verdeckte Quellenangabe, kein gespeichertes Bild); siehe [Kamera-Abnahme](CAMERA-ACCEPTANCE.md).

Nach dem Start der Basisstation die optionalen Abhängigkeiten aus `camera/requirements.txt` in einer eigenen Python-Umgebung installieren. Modellmanifest und Kameraquelle nur in der aktuellen PowerShell-Sitzung setzen:

~~~powershell
$env:BEEKEEPER_MODEL_MANIFEST = 'C:\secure\beekeeper\model-manifest.json'
$env:BEEKEEPER_CAMERA_SOURCE = '0' # alternativ lokale Datei / RTSP-Adresse
.\scripts\Start-BeeKeeperCamera.ps1 -ModelManifest $env:BEEKEEPER_MODEL_MANIFEST -CameraSource $env:BEEKEEPER_CAMERA_SOURCE -StationId 'station-01' -PythonExe '.\.venv-camera\Scripts\python.exe'
~~~

Der Starter liest den Quell-API-Schlüssel aus der DPAPI-Datei des aktuellen Benutzers. Der Schlüssel muss nicht in Befehle oder Dateien kopiert werden. Die Kamera läuft getrennt von den drei Basisdiensten. Das Beispielmanifest funktioniert erst, wenn ein echtes Modell, Prüfsumme, Herkunft, Lizenz und Prüfstatus eingetragen sind. **Jede vorhergesagte Art bleibt unbestätigt.** Kamera mit `Ctrl+C` stoppen.

## Verifiziertes lokales Backup
Bei laufenden Diensten einen konsistenten Schnappschuss des Quelljournals, der Monitor-Datenbank, der optionalen Kamera-Versandwarteschlange und des Bridge-Prüfpunkts erstellen:

```powershell
.\scripts\Backup-BeeKeeperStation.ps1 -MonitorRepo "C:\path\to\Beekeeper-Monitor"
```

Das Skript erstellt unter `%LOCALAPPDATA%\BeeKeeper3000\backups\` einen zeitgestempelten Sicherungssatz, prüft beide SQLite-Schnappschüsse, prüft und kopiert Bridge-Prüfpunkt und gegebenenfalls Kamera-Warteschlange und schreibt ein SHA-256-Manifest. Es erstellt den Sicherungssatz zunächst geschützt und veröffentlicht ihn erst nach erfolgreichen Prüfungen. Sicherungsziele außerhalb des geschützten Stationsverzeichnisses werden abgewiesen.

Die DPAPI-Schlüsseldatei wird **bewusst nicht mitgesichert**, da sie an Benutzer und Rechner gebunden ist. Sie muss separat geschützt und wiederhergestellt werden. Sicherungen enthalten sensible Stationsmetadaten; BitLocker und eine Aufbewahrungsfrist verwenden. Einzelheiten: [Sicherung und Wiederherstellung](SOURCE-JOURNAL-BACKUP.md).

## Prüfung ohne Dienststart
```powershell
.\scripts\Start-BeeKeeperStation.ps1 -MonitorRepo "C:\path\to\Beekeeper-Monitor" -ValidateOnly
```

Dieser Modus prüft Repository-Dateien sowie Python-/Node-Versionen und erstellt weder Schlüssel noch Prozesse.

## Grenzen der Ende-zu-Ende-Funktion
Quell-API, Bridge und Monitor-Empfänger sind lokale Softwarebausteine. Ein vertrauenswürdiger Detektor muss geprüfte Metadaten noch per HTTP POST an die Quell-API übergeben. Der signierte MeshCore-Richtungsempfänger und der lokale Triangulationsspeicher sind separate Module; Richtungsdaten erscheinen nicht automatisch in der Monitor-Ereignisliste. Vor einem operativen Einsatz fehlen weiterhin echte Kamera- und Funkprüfungen, Feldtests mit drei Stationen, Neustart-/Rückstautests und eine Abnahme eines öffentlichen Netzwerk-Gateways.

## Konsistentes Stations-Backup und Wiederherstellung
Während die Station läuft, lässt sich mit `Backup-BeeKeeperStation.ps1` ein konsistenter SQLite-Schnappschuss erstellen. Live-Datenbanken werden nicht direkt kopiert oder verändert. Das Skript verweigert Sicherungsziele außerhalb des geschützten Stationsverzeichnisses.

**Wichtig:** Die Datei `%LOCALAPPDATA%\BeeKeeper3000\station-secrets.clixml` wird nicht gesichert und ist nicht auf andere Windows-Benutzerkonten oder Rechner übertragbar. Die Backups sind nicht automatisch verschlüsselt; zusätzlich geschützte Sicherungen aufbewahren.

### Wiederherstellung auf demselben Rechner und Benutzerkonto
1. Station mit `.\scripts\Stop-BeeKeeperStation.ps1` stoppen.
2. Manifest und SHA-256-Prüfsummen kontrollieren; Dateien mit `network.source_backup verify` und `integrations.store_backup verify` prüfen.
3. Beide Datenbanken mit den jeweiligen `restore`-Unterbefehlen zunächst in **neue Dateien** wiederherstellen; die Befehle überschreiben keine bestehenden Dateien.
4. Nach Integritätsprüfung bei gestoppten Diensten die aktiven Datenbanken kontrolliert ersetzen und die bisherigen Dateien separat aufbewahren.
5. Bestehende DPAPI-Schlüsseldatei und zugehörigen Bridge-Prüfpunkt nicht austauschen. Station neu starten und Ereignisstände kontrollieren.

### Umzug auf anderen Rechner oder anderes Windows-Konto
1. Quell- und Monitor-Datenbanken aus verifizierten Sicherungen wiederherstellen.
2. Alte `station-secrets.clixml` und `data\bridge-state.json` **nicht übernehmen**. Falls bereits kopiert, vor dem ersten Start aus dem neuen Stationsprofil entfernen; Originale auf dem alten Gerät erhalten.
3. Starter auf dem neuen Gerät ausführen. Er erzeugt neue unabhängige Schlüssel.
4. Ohne alten Prüfpunkt beginnt die Bridge beim ältesten noch vorhandenen Quellereignis. Bereits bekannte Ereignisse werden im Monitor anhand stabiler IDs dedupliziert.

Nur noch vorhandene, gesicherte Quellereignisse lassen sich wiederherstellen. Gelöschte oder abgelaufene Daten werden durch neue Schlüssel nicht zurückgewonnen. Vor produktivem Betrieb eine Wiederherstellung anhand einer Testkopie und kontrollierter Wiederholung prüfen.

## Optionaler Start nach Windows-Anmeldung
Standardmäßig startet die Station manuell. Optional eine Aufgabe der Windows-Aufgabenplanung für den aktuellen Benutzer registrieren:

```powershell
.\scripts\Register-BeeKeeperStationStartup.ps1 -MonitorRepo "C:\path\to\Beekeeper-Monitor"
```

Der Befehl prüft zunächst die Voraussetzungen, ohne etwas zu verändern. Danach wird eine Aufgabe für die interaktive Anmeldung des aktuellen Benutzers mit 30 Sekunden Verzögerung erstellt. Sie speichert kein Passwort, nutzt die DPAPI-Schlüssel des Benutzers und läuft ohne Administratorrechte. Der Basisstarter richtet diese Aufgabe **nicht automatisch** ein.

Aufgabe ohne Löschung von Stationsdaten oder Schlüsseln entfernen:

```powershell
.\scripts\Register-BeeKeeperStationStartup.ps1 -Unregister
```

Das ist ein Anmeldestart, **kein Windows-Dienst und keine automatische Neustartüberwachung**. Der Windows-Starter prüft die drei Prozesse beim Start, startet einen später abgestürzten Einzelprozess aber nicht automatisch neu. Für verwaltete Dienstneustarts Linux/systemd verwenden oder die Windows-Station bis zur gesonderten Abnahme eines Diensthosts beaufsichtigen. Kamera-KI und MeshCore-Funk werden durch diese Aufgabe niemals gestartet.
