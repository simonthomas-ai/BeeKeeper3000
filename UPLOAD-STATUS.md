# Upload and integration status

## Published to GitHub

- New repository: https://github.com/simonthomas-ai/BeeKeeper3000
- Published: project overview, provenance/licensing/security notes, and the `monitor-bridge/` adapter with setup guide and tests.
- Published monitor-side connection guide: https://github.com/simonthomas-ai/Beekeeper-Monitor/blob/main/integrations/HORNET3000-CONNECTION.md

## Not yet published

The complete 1.6.0 source tree (C++ service, web UI, firmware, bridges, packaging, and full test suite) is prepared as a local source archive but has **not** been committed into this GitHub repository. Do not mistake the adapter/documentation commits for a complete source upload.

## Network implementation added

- `NETWORK-ARCHITECTURE.md`: bundesweite Architektur mit Teilnehmerklassen, LoRa/MeshCore, Freenet-P2P, IP-Fallback, Datenschutz und Pilot-Abnahme.
- `network/triangulation.py`: gewichtete Peilungs-Triangulation mit Zeitfenster-, Geometrie-, Rückwärtsstrahl- und Restfehlerprüfung.
- `network/protocol-v1.schema.json`: versionierter Ereignisrahmen für künftige Funk-/IP-Adapter.
- `network/test_triangulation.py`: synthetische Regressionstests; lokale numerische Referenzprüfung durchgeführt. GitHub Actions führt die Tests bei Push/PR aus.

Diese Komponenten sind ein Software-Referenzstart, noch kein fertig installierbares bundesweites Funknetz. Hardware-/Feldtests und echte Funkadapter fehlen.

## Validation

- C++ release build: passed.
- C++ core tests: 1/1 passed.
- Freenet, MeshCore, and Monitor-bridge Node tests: 12/12 passed.
- ONNX Runtime was unavailable in the baseline environment; model inference is therefore not confirmed active.

## Integration boundary

The adapter maps Hornet3000 events to the existing Monitor authenticated ingestion schema and omits image/audio/GPS data. The Monitor receiver currently validates and logs accepted metadata but does not yet persist it into PWA IndexedDB or display it in the dashboard. No live end-to-end deployment test has been performed.

## Release blockers

- Complete source tree upload and repository verification.
- Monitor-side persistence and dashboard UI integration.
- Runtime retention/deletion implementation and deployment-specific GDPR assessment.
- Model weights/dataset rights audit, full SBOM, and real camera/field validation.
- Real secrets must be provisioned locally; never commit API keys, camera credentials, captures, audio, or GPS traces.
