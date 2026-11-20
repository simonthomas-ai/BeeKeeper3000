# Smartphone PWA – acceptance plan

Status: source implementation and browser-independent contract tests exist. No physical Android/iPhone model has yet been field-validated.

## Software functions

- Manual sightings remain explicitly unverified.
- Photo picker/camera intent is user initiated; local image re-encoding is attempted and no media upload exists.
- GPS and orientation permissions are asked only when the user clicks the corresponding control.
- IndexedDB stores offline reports; export is manual and excludes photos, notes, precise location and sensor data.
- Service worker caches only same-origin static assets. CSP has no remote connect target.

## Device acceptance checklist

For each exact phone model, OS build and browser version, record date and evidence:

- Install from an HTTPS origin; reload once offline and confirm the shell opens.
- Create, review, delete and export a report with no permissions granted.
- Deny then grant photo, location and orientation separately; confirm the app still works when denied.
- Verify the re-encoded photo opens; verify photo, EXIF, GPS and compass are absent from exported JSON.
- Confirm airplane-mode reports persist through app/browser restart and that pending/saved state is visible.
- Use browser developer tools or a network monitor to verify that no unexpected external request, upload or beacon occurs.
- Measure storage growth, app stability and permission persistence. Test storage clearing and recovery.

A passed browser unit test is not a device acceptance. iOS background execution, continuous camera access, BLE, WebUSB, Web Serial and Web NFC are not promised. Any future native bridge must undergo separate privacy, security and store-policy review.

## Current user path

1. Host `mobile-pwa/` as static files over HTTPS.
2. Open the address on the phone and add it to the home screen.
3. Create an observation; optional camera/photo and location permissions are requested only when selected.
4. Export the metadata JSON and transfer it deliberately to a trusted station operator for reviewed ingestion. Do not upload private media or exact coordinates to public services.