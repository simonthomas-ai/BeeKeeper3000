# BeeKeeper3000 – Multi-source and hardware compatibility matrix

Status: architecture and integration contract; **not** a claim that every listed device has been implemented or tested.

## Objective
Connect existing phones, cameras, computers, sensors and network transports without coupling the core pipeline to one vendor. Each input is an adapter that normalizes data into existing BeeKeeper event contracts. Raw media stays local by default; the network protocol carries small signed metadata only.

## Compatibility levels
| Level | Meaning | Release wording |
|---|---|---|
| A – software-tested | Adapter exists and automated contract tests pass | Software-tested |
| B – hardware-tested | A real device has opened/read/connected | Hardware-tested for named model/firmware only |
| C – field-validated | Repeatable environmental and failure tests documented | Field-validated for stated setup |
| D – candidate | Interface is plausible; no adapter or acceptance evidence | Planned / experimental |

Never describe a generic interface as universal plug-and-play. Record exact device, firmware, backend and test evidence.

## Source classes

### Smartphones and tablets
- Android phones/tablets: responsive PWA for manual reports, user-authorized camera capture while active, photo picker, GPS/compass where browser and OS permit, offline drafts. Native background capture is a separate future feature.
- iPhone/iPad: PWA/manual report, user-selected photo/video, optional location and compass where permissions and browser APIs permit. Do not assume background camera capture.
- USB-C/Lightning accessories only where the OS exposes a supported interface; external thermal/USB cameras require per-device validation.
- Smartphone-only participation remains possible; no radio or AI camera purchase is required.

### Cameras and optical sensors
- USB UVC webcams, microscope and borescope cameras.
- CSI/MIPI camera modules on supported SBCs.
- RTSP/ONVIF IP cameras; HTTP MJPEG/HLS only through explicit adapters.
- HDMI capture devices exposed as UVC, subject to driver/backend tests.
- GigE Vision/industrial cameras through a separately maintained GenICam/vendor adapter.
- Stereo/depth cameras (OAK-class) through device-specific SDKs and license review.
- Thermal/IR cameras as supplementary evidence only, never sole species confirmation.

### Compute and inference hardware
- Windows 10/11 x64 PCs and mini-PCs.
- Linux x86_64 mini-PCs and servers.
- Raspberry Pi-class ARM64 SBCs; camera paths depend on exact board and OS.
- NVIDIA Jetson-class edge systems; CUDA/TensorRT are optional backends.
- Intel/AMD CPU inference; optional OpenVINO where supported.
- Coral/Edge TPU and Hailo-class accelerators only with explicit model conversion/runtime tests.
- NAS/Docker/Podman hosts for storage/bridge roles; not automatically suitable for inference.
- Android/iOS as reporting clients, not assumed to run the full station daemon.

### Environmental and positioning sensors
- GNSS/GPS via OS location API, USB, UART or NMEA 0183.
- Compass/IMU via phone sensor API, BLE, USB, I2C or SPI; bearings require calibration, declination and uncertainty.
- Temperature, humidity, pressure, light, rain and wind via BLE, USB, UART, I2C/SPI, Modbus RTU/TCP or MQTT.
- Microphones and arrays as optional local research inputs; no always-on audio upload and no audio-only nest-location claim.
- Radar/telemetry receivers require a separate lawful, animal-welfare-reviewed specialist workflow.

### Transport and backhaul
- USB/serial, Ethernet, Wi-Fi and VPN.
- HTTPS API and MQTT over authenticated TLS.
- BLE for short-range phone/sensor/radio accessory links.
- LoRa adapters: MeshCore, Meshtastic and LoRaWAN are distinct stacks, not wire-compatible.
- MeshCore companion radios may expose BLE, USB serial, Wi-Fi or Ethernet depending on board/firmware.
- Cellular 4G/5G routers and phone tethering as optional IP backhaul.
- Satellite IP backhaul as an optional ordinary IP transport with cost/latency limits.
- Freenet or another P2P overlay is a separate optional IP synchronization adapter, not a radio protocol.
- Every intermittent transport needs store-and-forward, deduplication, expiry and bounded queues.

## Adapter contract
Every adapter must declare a stable ID/version, class, device/backend, capabilities and permissions; normalize typed validated observations; attach provenance and calibration metadata; keep raw media local unless a separately reviewed export is explicitly enabled; enforce bounded timeouts, rate/payload limits, cancellation and reconnect backoff; fail closed when permissions/calibration/provenance are missing; never execute received payloads or arbitrary commands; and redact credentials, media and exact private coordinates from diagnostics.

The shared asynchronous lifecycle baseline now exists in `adapters/lifecycle.py`: discovery, capability and permission gates, bounded calls, health checks, mandatory stop, capped exponential reconnect and allowlisted diagnostics. It rejects event payloads containing raw media, credentials or exact coordinates before forwarding. This is a software contract, not evidence that a named camera, sensor or radio has been tested.

Existing camera/contracts.py and network/protocol-v1.schema.json remain authoritative event boundaries until a versioned migration is reviewed. Do not bypass signature, expiry, verification-status or privacy checks.

## Smartphone-PWA – current implementation boundary

The client in `mobile-pwa/` is the first implemented multi-source participant endpoint. It stores reports and optional media/location/sensor values locally; there is no server upload, remote API key, auto-sync, background capture or radio pairing. The metadata export intentionally emits only the existing six-field source API v1 event contract. Device interfaces such as Web Bluetooth, WebUSB, Web Serial and NFC are feature-detected only; the browser capability list is not a connection test or compatibility guarantee. See [Mobile PWA acceptance plan](MOBILE-PWA-ACCEPTANCE.md).
The shared lifecycle implementation in `adapters/lifecycle.py` adds asynchronous discovery, declared capabilities, permission checks, bounded calls, health, stop and reconnect policy for future adapters. It rejects event payloads containing raw media, credentials or precise location fields and emits only allowlisted diagnostics. Its state is software-tested only; no hardware adapter is thereby considered connected or field-validated.
The new `adapters/local_media.py` consumes one explicitly selected local image/video file under an approved root. It rejects symlink/traversal paths and oversized sources; image dimensions are checked before decode, video reads have FFmpeg timeouts plus frame/duration ceilings, and only unverified metadata enters the local SQLite outbox. It is software-tested, not yet validated against every real codec, camera, model or workstation; see [local media import](LOCAL-MEDIA-IMPORT.md).

Triangulation estimates can be exported by `network/geojson.py` as a point plus a closed local linearized 95% uncertainty ellipse. Both GeoJSON features are marked `search_hypothesis` with an explicit approximation warning; the polygon is not a legal boundary or an instruction for intervention.

## Proposed adapter inventory
| Adapter | Target | State |
|---|---|---|
| adapter-lifecycle | Shared discovery, capability/permission gates, health, timeouts, stop and reconnect supervisor | Implemented; automated contract tests; named-device acceptance pending |
| mobile-pwa | Manual report, local photo, optional one-shot GPS/compass, offline queue, metadata-only export | Implemented; browser-independent tests pass; physical Android/iOS acceptance pending |
| camera-uvc | USB webcam / microscope | Planned |
| camera-rtsp | RTSP/ONVIF | Partial existing source path; hardware acceptance pending |
| camera-files | User-selected JPEG/PNG/WebP and MP4/M4V/MOV/MKV/AVI/WebM; local ONNX inference; metadata-only SQLite outbox | Software adapter and boundary tests; real file/codec/model acceptance pending |
| camera-csi | Raspberry Pi CSI | Planned |
| camera-depth | OAK/depth device | Planned |
| thermal | Thermal sensor/frame analysis | Planned |
| sensors-ble | BLE environmental/IMU sensors | Planned |
| sensors-modbus | RS-485/Modbus gateway | Planned |
| gnss-nmea | USB/UART NMEA 0183 GNSS + true/magnetic heading | Software-tested parser/serial adapter; actual receiver, compass calibration and surveyed-bearing acceptance pending |
| transport-mqtt | MQTT TLS bridge | Planned |
| transport-meshcore | MeshCore companion transport | Separate existing work; hardware acceptance pending |
| transport-meshtastic | Meshtastic transport | Planned; not MeshCore-compatible |
| transport-lorawan | LoRaWAN gateway integration | Planned |
| transport-freenet | P2P batch sync over IP | Planned; not radio |

The NMEA adapter in `adapters/nmea.py` parses checksum-verified GGA/RMC and HDT/HDM/HDG sentences. It requires paired active GNSS fixes, bounded sentence/fix age, adequate satellite count and HDOP, and an explicit calibrated heading sigma. Only the MeshCore-compatible unverified bearing event leaves the parser; the exact GNSS position remains local and is resolved on a receiver from its local station registry. See [NMEA GNSS/heading adapter](NMEA-GNSS-HEADING-ADAPTER.md). This is software-tested only; no physical receiver, antenna, compass calibration or survey bearing has been accepted.

## Mobile permission and privacy rules
Ask for camera/photo/location/motion/Bluetooth permission only at point of use. Explain purpose, precision, retention and recipient first. Default to coarse public location; exact private coordinates stay local or restricted to authorized search teams. Do not request contacts, microphone, background location or broad photo-library access for basic reporting. Provide manual location and allow GPS-free submission. Feature-detect browser APIs and degrade gracefully. Do not claim continuous/background capture on iOS or Android without separate implementation and OS acceptance tests.

## Model/runtime portability
ONNX Runtime CPU is the baseline where the model operator set is supported. CUDA/TensorRT, OpenVINO, CoreML, TFLite/Edge TPU and vendor accelerators are optional execution providers, not interchangeable guarantees. Every model/backend pair needs hash, exact runtime version, tensor contract, rights review and accuracy/latency evaluation on target hardware. Faster inference does not prove biological accuracy.

## Device acceptance record
Record exact device/revision, firmware/OS, adapter version, driver/runtime, physical interface, power supply, stream/sensor format, calibration, permissions/data path, 2-hour stability, disconnect/reconnect, queue overflow/restart, CPU/RAM/temperature/power, raw-media retention, network-egress audit, limitations and test date.

A device absent from the evidence register is unverified, even if it uses a familiar connector.
