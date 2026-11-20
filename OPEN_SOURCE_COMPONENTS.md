# Open-source component evaluation

Status: engineering register, not blanket approval to copy or bundle dependencies. Exact versions, transitive dependencies, firmware, weights and datasets must be reviewed independently.

## Current implementation state

| Component | Observed license | State in BeeKeeper3000 | Controls / decision |
|---|---|---|---|
| [MeshCore](https://github.com/meshcore-dev/MeshCore) | MIT (upstream project) | Optional serial adapter uses Python binding `meshcore==2.3.19` | Signed binary metadata profile v1, Ed25519, 128-bit fingerprints, no exact GPS/media; simulated transport tests only; hardware/firmware/FCC/RED and field tests remain required |
| [Meshtastic firmware](https://github.com/meshtastic/firmware) | GPL-3.0 | Not integrated | Keep as separate optional alternative; assess upstream advisories and firmware release before any adapter |
| [Freenet Core](https://github.com/freenet/freenet-core) | AGPL-3.0 for core; `freenet-stdlib` is separately licensed | Not integrated | Research only; distinguish network-protocol client from linking/bundling core; exact API/release and obligations require review |
| [Insect Detect](https://github.com/maxsitt/insect-detect) | GPL-3.0 | Not integrated | Benchmark/reference only; model weights and datasets need their own license/provenance review |
| [Insect Detect ML](https://github.com/maxsitt/insect-detect-ml) | AGPL-3.0 | Not integrated | Keep isolated until network-copyleft and dataset/weight conditions are reviewed |
| [Eclipse Mosquitto](https://github.com/eclipse-mosquitto/mosquitto) | EPL-2.0 / EDL-1.0 | Not integrated | Optional MQTT candidate only; pin an advisory-reviewed release before adoption |
| [MapLibre GL JS](https://github.com/maplibre/maplibre-gl-js) | BSD-3-Clause | Not integrated | Browser map candidate; require patched XSS-safe release and assess tile-source terms separately |
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
