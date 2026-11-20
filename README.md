# BEEKEEPER3000

This repository is the integration home for the Hornet3000 Wächter 1.6.0 source baseline and the Beekeeper-Monitor connector.

## Current scope

The current source baseline is inherited from Hornet3000 Wächter 1.6.0; it is not yet the complete multi-species BeeKeeper3000 product. No trained model weights or validated datasets are included. ONNX Runtime and field accuracy require separate installation and validation.

## Monitor connection

See [monitor-bridge/README.md](monitor-bridge/README.md). The adapter polls Hornet3000's authenticated `GET /api/events?limit=100` endpoint and sends metadata to the existing Beekeeper-Monitor authenticated ingestion endpoint `POST /api/v1/events`. It intentionally excludes image/audio/GPS data.

**Important:** the current monitor ingestion handler validates and logs events but does not yet persist them into the PWA's IndexedDB or show them in the dashboard. The connector is therefore transport-ready, not a completed end-to-end UI integration.

## Build and tests

See the staged source archive's `CMakeLists.txt`, `BUILD-STATUS.md`, and project documentation. Linux baseline verification previously passed the C++ build, 1/1 core test, and 10/10 Freenet/MeshCore bridge tests. Monitor connector tests are included here.

## Security and licensing

Never commit real secrets, camera credentials, private captures, audio, GPS traces, or unlicensed datasets/models. Keep services on loopback or behind a private VPN and HTTPS reverse proxy. See [SECURITY.md](SECURITY.md), [LICENSES.md](LICENSES.md), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and [PROVENANCE.md](PROVENANCE.md). The inherited GPL-3.0-or-later license and third-party notices are retained; no relicensing or blanket legal clearance is claimed.
