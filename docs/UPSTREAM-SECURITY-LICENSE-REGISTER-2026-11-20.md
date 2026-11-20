# Upstream license and security register — 2026-11-20

This is a dated engineering review of optional components named in this project. It is not legal advice, a complete product SBOM, or permission to copy upstream code, firmware, models or datasets. None of the optional components below is silently added to the current runtime by this register.

## Status matrix

| Component | Upstream license evidence | Current use here | Security/release evidence reviewed 2026-11-20 | Decision |
|---|---|---|---|---|
| MeshCore firmware | MIT, upstream `license.txt` | Optional adapter uses the separately pinned Python binding `meshcore==2.3.19`; no firmware binary is vendored | Upstream latest release observed: Companion/Repeater/Room Server v1.18.0, release 2026-10-15. Target radio/board firmware must be pinned independently by SHA-256 and board ID. | Keep optional. Do not call the hardware adapter field-ready until the exact device firmware, region settings, radio permissions and repeaters are field-tested. |
| Meshtastic firmware | GPL-3.0 | Not integrated | Upstream security policy says only 2.8.x is supported. The most recent 2.8.2 listing observed is Alpha (2026-11-04). GHSA-mjx5-98jq-q736 (Critical, published 2026-04-20) documents fork-code execution from a `pull_request_target` CI workflow; no patched version is listed. GHSA-7ph5-2mjv-69h8 (High, published 2026-07-09; CVE-2026-42566) affects versions <=2.7.22.96dd647; advisory says firmware input sanitization/regression tests have since been added, but no patched-version field is supplied. | Do not adopt an unsupported 2.7.x build. Select only a supported 2.8.x release after checking its exact current tag, firmware security model, hardware and region settings. Avoid treating an Alpha build as a production baseline. |
| Freenet Core | AGPL-3.0 | Not integrated | Upstream `LICENSE.md` explains that clients linking only to `freenet-stdlib` (LGPL-3.0) or communicating by HTTP/WebSocket do not automatically make the client app AGPL; a modified deployed core remains under AGPL obligations. | Optional IP/P2P research only. Use a protocol client boundary; do not embed/fork core without a separate license and deployment review. Freenet is not LoRa radio transport. |
| Insect Detect | GPL-3.0 | Not integrated; benchmark/reference only | Repository source license does not establish rights for separately downloaded model weights, images or datasets. | Do not reuse model binaries/data until each artifact has source, version/hash, license and use rights recorded. |
| Insect Detect ML | AGPL-3.0 | Not integrated | Training notebooks and datasets/models are separate artifacts; repository license alone is not sufficient provenance. | Keep isolated until network-copyleft, training data, model-weight and commercial/public-service use conditions are reviewed. |
| Eclipse Mosquitto | EPL-2.0 / EDL-1.0 | Not integrated | GHSA-6j8m-r32v-4h38 / CVE-2026-110486 (Critical, published 2026-11-17): 2.1.0–2.1.2 built-in WebSocket listener vulnerable; patched 2.1.3. GHSA-878w-672v-qwmf / CVE-2026-126708 (High, published 2026-11-17): affected 2.0.0–2.0.22 and 2.1.0–2.1.2; patched 2.0.23 and 2.1.3. | Optional MQTT candidate only. If later adopted, deny affected versions; prefer 2.1.3 or a newer reviewed fix and separately harden listener/auth/TLS configuration. No current project exposure because Mosquitto is not a dependency. |
| MapLibre GL JS | BSD-3-Clause | Not integrated | GHSA-jrc7-96c5-q579 / CVE-2026-85061 (Critical, published 2026-08-19): versions <=6.4.0 affected by DOM sanitizer XSS bypass; fixed in 6.4.1. | If adopted, require >=6.4.1 and review style/attribution input plus tile-provider terms. No current project exposure because package is absent. |
| QGIS | GPL-2.0 | External expert workflow only | No QGIS code or binary is included in this repository. | Keep as an external workflow; account separately for plugins, providers and data. |

## Current repository dependency evidence

- The optional MeshCore Python binding is pinned in `network/meshcore/requirements.lock` for Linux CI: `meshcore==2.3.19` plus its captured transitive packages. This is not a universal cross-platform lock.
- The Node bridge uses Node built-ins only. Its committed npm lockfile currently contains no third-party npm package entries.
- `.github/workflows/supply-chain.yml` runs pinned `pip-audit==2.10.1` against the optional Python lock, generates a CycloneDX 1.6 artifact with pinned `cyclonedx-bom==9.0.0`, and runs `npm audit` against the Node lock.
- These checks cover only those exact manifests. They do not cover missing inherited C++/CMake sources, hardware firmware, operating-system packages, model runtimes, weights, datasets, image/audio assets or future adapters.
- CI action references are still not consistently pinned to immutable commit SHAs; treat this as supply-chain hardening work before a public release.
- The project root LICENSE and full inherited source archive are absent. The provenance notes describe the inherited 1.6.0 baseline as GPL-3.0-or-later, but a project-wide license cannot be declared until the full source/notice chain is restored and reconciled. Do not add a blanket root license by inference.

## Adoption gate

Before any optional component becomes a production dependency, record:
1. Exact release/tag and immutable commit SHA (or firmware binary SHA-256 plus hardware revision).
2. SPDX identifier and the actual upstream license text/hash.
3. Complete direct/transitive SBOM and vulnerability audit for the selected platform.
4. Relevant advisory IDs, affected ranges, fixed version and a tested minimum version.
5. Separate provenance/license for firmware, models, weights, datasets, imagery, map tiles and generated artifacts.
6. Runtime permissions, data egress, storage limits and rollback strategy.
7. Device-level and field tests on the actual supported station hardware.

## Sources reviewed

- [MeshCore source license](https://github.com/meshcore-dev/MeshCore/blob/main/license.txt)
- [MeshCore releases](https://github.com/meshcore-dev/MeshCore/releases)
- [Meshtastic supported versions/security policy](https://github.com/meshtastic/firmware/security)
- [Meshtastic GHSA-mjx5-98jq-q736](https://github.com/meshtastic/firmware/security/advisories/GHSA-mjx5-98jq-q736)
- [Meshtastic GHSA-7ph5-2mjv-69h8](https://github.com/meshtastic/firmware/security/advisories/GHSA-7ph5-2mjv-69h8)
- [Freenet Core license explanation](https://github.com/freenet/freenet-core/blob/main/LICENSE.md)
- [Freenet stdlib license](https://github.com/freenet/freenet-stdlib)
- [Insect Detect](https://github.com/maxsitt/insect-detect)
- [Insect Detect ML](https://github.com/maxsitt/insect-detect-ml)
- [Mosquitto GHSA-6j8m-r32v-4h38](https://github.com/eclipse-mosquitto/mosquitto/security/advisories/GHSA-6j8m-r32v-4h38)
- [Mosquitto GHSA-878w-672v-qwmf](https://github.com/eclipse-mosquitto/mosquitto/security/advisories/GHSA-878w-672v-qwmf)
- [MapLibre GHSA-jrc7-96c5-q579](https://github.com/maplibre/maplibre-gl-js/security/advisories/GHSA-jrc7-96c5-q579)

Review date: 2026-11-20. Re-check upstream advisories and release tags at every deployment/release.
