# BeeKeeper3000 Mobile PWA

Responsive installable participant client for Android, iPhone and tablets. It supports manual insect reports, an optional user-selected photo (resized through canvas), optional one-shot GPS, optional raw device orientation (waits for a valid sensor sample, but remains uncalibrated), local IndexedDB storage and an explicit metadata-only JSON export.

## Run locally

From the repository root:

```sh
python -m http.server 8000 --directory mobile-pwa
```

Open `http://127.0.0.1:8000/` on the same device. For a phone on another device, use an HTTPS host; browser location/sensor APIs and service workers require a secure context except for localhost. Never expose Python's development server to the public Internet. For iPhone, open the HTTPS site in Safari and use Share → Add to Home Screen. Android installation depends on the browser.

## Privacy and limits

- Nothing is uploaded and no API key exists in the PWA. There is no auto-sync or background capture.
- Photo, note, exact GPS and orientation values are stored only in local IndexedDB. Images are re-encoded as JPEG to remove original metadata where browser image decoding permits.
- Export uses the seven-field source API v2 metadata contract and explicitly marks `origin=manual_observation`; no photos, private notes, GPS, compass data, tokens or diagnostics are exported.
- Observer confidence is not model confidence and does not confirm a species.
- API presence detection is informational, not a device compatibility or hardware connection test. Bluetooth/USB/Serial/NFC adapters are not implemented yet.
- Local browser storage can be cleared by the OS/browser and is not a backed-up station database. Delete records from the app when no longer needed.

See [mobile hardware acceptance](../docs/MOBILE-PWA-ACCEPTANCE.md).
## Übergabe an eine lokale Windows-Station

1. Exportiere in der PWA `beekeeper-mobile-events.json`.
2. Übertrage diese Datei kontrolliert auf den Stations-PC. Der Export enthält keine Fotos, Notizen, GPS- oder Kompassdaten.
3. Auf dem Stations-PC muss BeeKeeper zuvor mit demselben Windows-Benutzer gestartet worden sein, damit die DPAPI-geschützte Station-API-Zugangsdaten-Datei vorhanden ist.
4. Im Projektverzeichnis ausführen:

```powershell
.\scripts\Import-BeeKeeperMobileExport.ps1 -ExportFile "$env:USERPROFILE\Downloads\beekeeper-mobile-events.json"
```

Der PowerShell-Wrapper liest den API-Schlüssel kurzzeitig aus der DPAPI-Datei, setzt ihn nur für den Importprozess und stellt die vorherige Prozessumgebung danach wieder her. Der Python-Importer akzeptiert keine Ziel-URL und sendet nur an `http://127.0.0.1:8787/api/events`. Er folgt keinen HTTP-Weiterleitungen und überträgt keine privaten PWA-Felder. Bei Unterbrechung denselben Export erneut importieren; die serverseitige Ereignis-ID-Deduplizierung verhindert doppelte Einträge.
