# Open-source component evaluation

Status: engineering register, not blanket approval to copy or bundle dependencies. Exact versions, transitive dependencies, firmware, weights and datasets must be reviewed independently. A dated upstream security/license evidence review is maintained in [docs/UPSTREAM-SECURITY-LICENSE-REGISTER-2026-11-20.md](docs/UPSTREAM-SECURITY-LICENSE-REGISTER-2026-11-20.md).

## Current implementation state

| Component | Observed license | State in BeeKeeper3000 | Controls / decision |
|---|---|---|---|
| [MeshCore](https://github.com/meshcore-dev/MeshCore) | MIT (firmware repository) | Optional serial adapter uses Python binding `meshcore==2.3.19` | Upstream firmware v1.18.0 observed 2026-10-15; signed metadata profile v1, station-bound Ed25519 keys, 128-bit fingerprints, no exact GPS/media; simulated transport tests only; hardware/firmware/RED and field tests remain required |
| [Meshtastic firmware](https://github.com/meshtastic/firmware) | GPL-3.0 | Not integrated | Upstream security policy supports 2.8.x only; 2026 advisories include GHSA-mjx5-98jq-q736 (Critical CI fork-code execution) and GHSA-7ph5-2mjv-69h8 (High malformed long_name). Keep separate; do not use unsupported 2.7.x or unreviewed Alpha firmware |
| [Freenet Core](https://github.com/freenet/freenet-core) | AGPL-3.0 for core; [`freenet-stdlib`](https://github.com/freenet/freenet-stdlib) LGPL-3.0 | Not integrated | Research only; upstream license explanation distinguishes stdlib/protocol clients from modifying/deploying core; exact API/release and obligations still require review |
| [Insect Detect](https://github.com/maxsitt/insect-detect) | GPL-3.0 | Not integrated | Benchmark/reference only; model weights and datasets need their own license/provenance review |
| [Insect Detect ML](https://github.com/maxsitt/insect-detect-ml) | AGPL-3.0 | Not integrated | Keep isolated until network-copyleft and dataset/weight conditions are reviewed |
| [Eclipse Mosquitto](https://github.com/eclipse-mosquitto/mosquitto) | EPL-2.0 / EDL-1.0 | Not integrated | 2026-11-17 advisories CVE-2026-110486 and CVE-2026-126708 affect 2.1.0–2.1.2; also 2.0.0–2.0.22 for auth issue. Patched versions 2.1.3 / 2.0.23; optional MQTT only |
| [MapLibre GL JS](https://github.com/maplibre/maplibre-gl-js) | BSD-3-Clause | Not integrated | GHSA-jrc7-96c5-q579 / CVE-2026-85061: <=6.4.0 critical DOM sanitizer XSS; fixed 6.4.1. Require >=6.4.1 and assess tile-source terms |
| [QGIS](https://github.com/qgis/QGIS) | GPL-2.0 | External expert workflow only | No QGIS code is embedded |

## Architecture choice

1. Keep the event schema and application logic transport-neutral.
2. MeshCore is the first optional LoRa adapter; Meshtastic remains a separate alternative.
3. Add HTTPS/IP replication only when an authenticated event store, paging/cursor and replay semantics are available.
4. Evaluate Freenet as a separate IP P2P adapter; it is not a LoRa modem or repeater.
5. Keep camera/AI processing local. Insect Detect is a benchmark, not a drop-in Vespa velutina classifier.
6. MapLibre remains an optional map UI candidate; review tile-provider terms separately.
7. No dependency may silently upload images, audio, GPS or personal data.

## Model and dataset rules

A software license does not automatically license pretrained weights, training images, annotations, photos or external datasets. Record origin, author, URL, version/hash, SPDX license, attribution and allowed use per artifact. Keep detections as candidates until expert verification.

## Acceptance gates before adoption

- Exact release/tag and commit pinned.
- SPDX license identifier and full license text captured.
- Direct and transitive dependencies locked and included in an SBOM.
- Upstream security advisories reviewed; affected versions denied by CI.
- Model/data/firmware provenance reviewed separately.
- Offline operation and network egress tested.
- Resource footprint and rollback measured on target hardware.
- Real radio and field tests completed before field deployment.
