# BeeKeeper3000 Mobile PWA

Responsive installable participant client for Android, iPhone and tablets. It supports manual insect reports, an optional user-selected photo (resized through canvas), optional one-shot GPS, optional raw device orientation, local IndexedDB storage and an explicit metadata-only JSON export.

## Run locally

From the repository root:

```sh
python -m http.server 8000 --directory mobile-pwa
```

Open `http://127.0.0.1:8000/` on the same device. For a phone on another device, use an HTTPS host; browser location/sensor APIs and service workers require a secure context except for localhost. Never expose Python's development server to the public Internet. For iPhone, open the HTTPS site in Safari and use Share → Add to Home Screen. Android installation depends on the browser.

## Privacy and limits

- Nothing is uploaded and no API key exists in the PWA. There is no auto-sync or background capture.
- Photo, note, exact GPS and orientation values are stored only in local IndexedDB. Images are re-encoded as JPEG to remove original metadata where browser image decoding permits.
- Export includes only the six-field source API v1 metadata contract; no photos, private notes, GPS, compass data, tokens or diagnostics.
- Observer confidence is not model confidence and does not confirm a species.
- API presence detection is informational, not a device compatibility or hardware connection test. Bluetooth/USB/Serial/NFC adapters are not implemented yet.
- Local browser storage can be cleared by the OS/browser and is not a backed-up station database. Delete records from the app when no longer needed.

See [mobile hardware acceptance](../docs/MOBILE-PWA-ACCEPTANCE.md).