# Open-source component evaluation

Status: engineering register, not blanket approval to copy or bundle dependencies. Exact versions, transitive dependencies, firmware, weights and datasets must be reviewed independently. A dated upstream security/license evidence review is maintained in [docs/UPSTREAM-SECURITY-LICENSE-REGISTER-2026-11-20.md](docs/UPSTREAM-SECURITY-LICENSE-REGISTER-2026-11-20.md).

## Current implementation state

| Component | Observed license | State in BeeKeeper3000 | Controls / decision |
|---|---|---|---|
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | MIT | Optional CPU runtime for the local camera adapter; pinned `onnxruntime==1.32.0` | Optional and disabled unless an independently rights-reviewed ONNX artifact and manifest are supplied |
| [OpenCV](https://github.com/opencv/opencv) | Apache-2.0 (4.5.0+) | Optional headless camera capture/preprocessing; pinned `opencv-python-headless==4.14.0.94` | Optional direct packages only; platform-specific transitive SBOM and camera/codec compatibility checks remain required |
| [MeshCore](https://github.com/meshcore-dev/MeshCore) | MIT (firmware repository) | Optional serial adapter uses Python binding `meshcore==2.3.19` | Upstream firmware v1.18.0 observed 2026-10-15; signed metadata profile v1, station-bound Ed25519 keys, 128-bit fingerprints, no exact GPS/media; simulated transport tests only; hardware/firmware/RED and field tests remain required |
| [Meshtastic firmware](https://github.com/meshtastic/firmware) | GPL-3.0 | Not integrated | Official downloads checked 2026-11-22: 2.7.26.54e0d8d Beta is shown under Stable; 2.8.2.d5f1619 remains Alpha and 2.8.3 is Nightly. GHSA-mjx5-98jq-q736 concerns upstream `pull_request_target` CI/fork checkout; GHSA-7ph5-2mjv-69h8 affects <=2.7.22.96dd647. Keep separate; never equate Alpha/Nightly with production-stable firmware; pin board firmware SHA-256 and regional radio config |
| [Freenet Core](https://github.com/freenet/freenet-core) | AGPL-3.0 for core; [`freenet-stdlib`](https://github.com/freenet/freenet-stdlib) LGPL-3.0 | Not integrated | Research only; upstream license explanation distinguishes stdlib/protocol clients from modifying/deploying core; exact API/release and obligations still require review |
| [Insect Detect](https://github.com/maxsitt/insect-detect) | GPL-3.0 | Not integrated | Benchmark/reference only; model weights and datasets need their own license/provenance review |
| [Insect Detect ML](https://github.com/maxsitt/insect-detect-ml) | AGPL-3.0 | Not integrated | Keep isolated until network-copyleft and dataset/weight conditions are reviewed |
| [Eclipse Mosquitto](https://github.com/eclipse-mosquitto/mosquitto) | EPL-2.0 / EDL-1.0 | Not integrated | 2026-11-17 advisories: CVE-2026-110486 affects 2.1.0–2.1.2 (critical WebSocket issue), CVE-2026-126708 affects 2.0.0–2.0.22 and 2.1.0–2.1.2. Fixes in 2.1.3 / 2.0.23; 2.1.4 fixes a legacy SHA-512 auth regression introduced in 2.1.3. If ever adopted, prefer 2.1.4+ (2.1 branch) or 2.0.23+ (2.0 branch); not currently a dependency |
| [MapLibre GL JS](https://github.com/maplibre/maplibre-gl-js) | BSD-3-Clause | Not integrated | GHSA-jrc7-96c5-q579 / CVE-2026-85061: <=6.4.0 critical DOM sanitizer XSS; fixed 6.4.1. Require >=6.4.1 and assess tile-source terms |
| [QGIS](https://github.com/qgis/QGIS) | GPL-2.0 | External expert workflow only | No QGIS code is embedded |

**Freshness note (2026-11-22):** The release-channel and advisory refresh is recorded in [the upstream security/license register](docs/UPSTREAM-SECURITY-LICENSE-REGISTER-2026-11-20.md). The versions above are adoption guards, not a declaration that these optional components are installed or approved.

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
