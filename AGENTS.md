# BeeKeeper3000 agent work charter

This repository is a privacy-first, local-first monitoring system for the invasive species *Vespa velutina*. Work must be modular, testable, and license-compliant.

## Agent roles / workstreams

1. **Network transport:** MeshCore first; Meshtastic as optional alternative; IP/HTTPS and MQTT adapters; Freenet only after exact API/license review.
2. **Detection and evidence:** camera ingestion, local inference, tracking, confidence calibration, false-positive evaluation, model/data provenance.
3. **Geospatial analysis:** timestamped bearings, robust multi-station estimation, uncertainty polygons, geometry checks, field validation.
4. **Station runtime:** install/update, configuration, health, offline queue, resource limits, Windows/Linux/Raspberry Pi support.
5. **Monitor and user experience:** accessible PWA, map, observation entry, role-based sharing, export and deletion.
6. **Security, privacy and licensing:** threat model, signatures, key rotation/revocation, retention, SBOM, license and dataset audit.
7. **Integration and QA:** end-to-end tests, hardware-in-loop test plan, CI, reproducible builds and release packaging.

## Non-negotiable constraints

- Do not claim a feature works until automated tests and/or a reproducible field test prove it.
- Never upload raw image/audio/GPS by default. Explicit consent and purpose limitation are required.
- LoRa is a constrained metadata transport, not a media channel. Never assume nationwide coverage.
- Freenet is an IP peer-to-peer layer, not a LoRa radio protocol.
- A hornet does not transmit LoRa. Bearing triangulation or professional radio telemetry is required for localization.
- Every location estimate is a hypothesis with uncertainty; no automatic nest confirmation or eradication action.
- Never label an AI output as expert-confirmed.
- Preserve GPL-3.0-or-later project obligations and upstream copyright/license notices.
- Check licenses of models, weights, datasets, firmware, generated assets and transitive dependencies independently.
- Do not bundle Reticulum until its custom license has been reviewed for the intended use.
- No secrets, API keys, private coordinates or personal data in commits, logs or test fixtures.
- Default to localhost/private network; remote access requires authenticated encrypted transport.
- Keep adapters replaceable; do not make one vendor, cloud or radio network mandatory.

## Required delivery format for each work item

- Short design note and threat/data-flow impact.
- Small implementation commits with tests.
- Exact dependency versions and SPDX license IDs.
- Reproduction commands and test results.
- Known limitations and rollback steps.
- Update documentation and provenance notices.
