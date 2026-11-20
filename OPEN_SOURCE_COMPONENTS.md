# Open-source component evaluation

Status: engineering shortlist, not a blanket approval to copy or bundle dependencies. Review each repository, exact version, transitive dependency, model, dataset and firmware artifact before distribution. "Free to use" is not the same as "license compatible".

## Recommended candidates

| Area | Project | License observed | Proposed use | Decision |
|---|---|---|---|---|
| LoRa mesh | [MeshCore](https://github.com/meshcore-dev/MeshCore) | MIT | Primary candidate for compact event transport, repeaters and custom station integration | Prototype adapter first; preserve notices and verify firmware/hardware support |
| LoRa mesh alternative | [Meshtastic firmware](https://github.com/meshtastic/firmware) | GPL-3.0 | Optional compatibility adapter / field comparison | Keep as alternative; do not assume arbitrary app payloads or nationwide coverage |
| IP / intermittent network | [Freenet](https://freenet.org/) | License and API must be verified per exact Core release | Optional P2P event-batch distribution for IP-connected peers | Research adapter only until license, API stability, data retention and message semantics are confirmed |
| General resilient network alternative | [Reticulum](https://github.com/markqvist/Reticulum) | Custom Reticulum License | Possible independent transport experiment over LoRa, packet radio or IP | **Do not bundle yet.** License has explicit restrictions on harmful systems and AI/ML dataset creation; assess legal fit and ensure no Reticulum-derived data enters model training |
| Insect camera pipeline | [Insect Detect](https://github.com/maxsitt/insect-detect) | GPL-3.0 | Benchmark its capture/tracking architecture and camera pipeline | Reuse only after component-by-component review; model and dataset rights must be checked separately |
| Insect ML tooling | [Insect Detect ML](https://github.com/maxsitt/insect-detect-ml) | AGPL-3.0 | Offline benchmark and training workflow reference | Isolate as optional service/tool; AGPL network obligations need review before integration |
| Messaging broker | [Eclipse Mosquitto](https://github.com/eclipse-mosquitto/mosquitto) | EPL-2.0 / EDL-1.0 | Optional local MQTT bridge for LAN and IP gateways | Good optional adapter; never required for offline LoRa |
| GIS desktop validation | [QGIS](https://github.com/qgis/QGIS) | GPL-2.0 | Import/export GeoJSON/GeoPackage and verify search polygons | External tool workflow; no need to embed QGIS |
| Web mapping | [MapLibre GL JS](https://github.com/maplibre/maplibre-gl-js) | BSD-3-Clause | Candidate for interactive browser map | Use if current PWA mapping is insufficient; review map tile source terms separately |

## Architecture choice

1. Keep BeeKeeper3000's event schema and application logic transport-neutral.
2. Implement MeshCore as the first LoRa adapter; keep Meshtastic as a separately tested alternative.
3. Implement an IP adapter using HTTPS first; optionally MQTT/Mosquitto for local gateways.
4. Evaluate Freenet as a peer-to-peer replication adapter only after its current developer API and release license are verified.
5. Keep the camera/AI pipeline local. Insect Detect is a benchmark/reference, not a drop-in Vespa velutina classifier.
6. Use MapLibre in the web PWA; use QGIS for expert validation and exports.
7. No dependency is allowed to silently upload images, audio, GPS or personal data.

## Model and dataset rules

- A software license does not automatically license pretrained weights, training images, annotations or third-party datasets.
- Record origin, author, URL, version/hash, license, attribution and permitted use for every model and dataset.
- Keep all detections as candidates until expert verification.
- Never train on Reticulum-derived data unless the Reticulum license has been explicitly reviewed and permits the exact use.
- Preserve the existing BeeKeeper3000/Hornet3000 GPL-3.0-or-later obligations and all upstream notices.

## Acceptance gates before adoption

- Exact release/tag and commit pinned.
- SPDX license identifier and full license text captured.
- Dependency and model/data licenses reviewed.
- Security policy, release activity and known vulnerabilities reviewed.
- Offline operation demonstrated.
- Data flow documented and network egress tested.
- Resource footprint measured on target hardware.
- Integration tests and rollback path supplied.
