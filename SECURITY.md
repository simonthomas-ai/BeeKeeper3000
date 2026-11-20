# Security and operational baseline

## Implemented in the published source

- Node.js bridge forwards metadata only and deliberately omits image, audio and GPS coordinates.
- Bridge requires separate source and receiver credentials, validates endpoint transport policy, validates source events, bounds source and receiver response sizes, rejects redirects and uses request timeouts.
- Bridge checkpoints source event IDs only after the Monitor returns HTTP 202 with an explicit `{"accepted":true}` durable-storage acknowledgement. If writing the local checkpoint fails, its in-memory ID is rolled back for retry.
- The bridge supports versioned v2 state with an opaque source cursor, bounded multi-page catch-up, per-page checkpointing after durable receiver acknowledgements, restart-safe replay, strict invalid-event handling and an opt-in `BRIDGE_REQUIRE_CURSOR=true` fail-closed mode. The old latest-100 source API remains supported only as an explicitly lossy compatibility fallback.
- Optional MeshCore profile signs compact event metadata using Ed25519. Receivers verify expiry and signatures, require an explicit station-hash-to-signing-key allowlist, reject private key material at receiver configuration, and downgrade expert status unless the key is separately trusted for expert verification. Multiple fingerprints may be temporarily authorized for a station during deliberate key rotation.
- MeshCore events omit exact location, media, credentials and free-form text. A receiver resolves station hashes using a local coordinate registry.
- `network/meshcore/event_store.py` persists verified MeshCore event IDs and metadata in local SQLite with bounded retention and row count. Duplicate delivery remains idempotent after receiver restart. Coordinates are stored only from the receiver-local station registry, not from the radio packet.
- Beekeeper-Monitor's current main branch provides a loopback-bound authenticated receiver, bounded request workers and body size, socket timeouts, rate limiting, strict event validation and local SQLite storage with idempotent event IDs.
- The Monitor local PWA displays server-side station events through the same-origin localhost interface; the token is held in memory for the session.

## Required deployment controls

- Keep services bound to loopback or a trusted private network by default.
- Use separate, randomly generated credentials for each service. Never commit credentials, camera passwords, private keys, personal data, private captures, audio or GPS traces.
- Protect Ed25519 private keys with operating-system ACLs or hardware-backed storage. Provision trusted public keys out of band and define key revocation/rotation.
- Remote access requires a private VPN and a reviewed HTTPS reverse proxy. Never expose plain-HTTP listeners directly to the public internet.
- SQLite data is not encrypted by the application. Use BitLocker, FileVault, LUKS or an approved encrypted volume; configure restricted filesystem ACLs.
- Backups, browser IndexedDB, exports, reverse-proxy logs and source-side events require their own retention and deletion handling.
- Keep exact nest/private-property coordinates off public maps; use aggregation and role-based disclosure.
- Keep dependencies pinned, generate SBOMs and review advisories before release. The CI supply-chain workflow audits the captured optional MeshCore requirements and zero-dependency bridge, and uploads a CycloneDX artifact; it is not a complete SBOM for the absent full C++ source/runtime. See `SUPPLY_CHAIN.md`.

## Known release gaps

- The bridge client now supports cursor pagination and backlog catch-up, but the actual Hornet3000 source API in this repository still exposes only the latest 100 events. The server-side cursor implementation, durable sequence, retention and live end-to-end acceptance are not present here. Until those ship, default compatibility mode remains lossy; deployments can set `BRIDGE_REQUIRE_CURSOR=true` to fail closed. See `monitor-bridge/SOURCE-CURSOR-CONTRACT.md` and BeeKeeper3000 issue #7.
- MeshCore has only simulated protocol/transport tests; no real radio, antenna, repeater or multi-station field test is claimed.
- Freenet, Meshtastic, Mosquitto and MapLibre are not active runtime dependencies of BeeKeeper3000.
- ONNX inference and the Vespa-velutina classifier are not validated as operational.
- Automated SQLite backup/verify/restore is available, but encrypted backup media, schedule/rotation and Windows ACL provisioning remain deployment responsibilities. Hardware field validation and the complete source/license inventory still require release acceptance.
- No GDPR compliance claim is made. A deployment-specific assessment of roles, purposes, legal basis, DPIA necessity, retention, rights handling and processors is still required.


## Coordinated vulnerability disclosure

Do not publish exploitable vulnerability details, credentials, personal data or live station locations in public issues. Use GitHub private vulnerability reporting for this repository if enabled. If private reporting is unavailable, first open a minimal issue asking maintainers for a secure contact channel without including exploit details. Do not test systems you do not own or have explicit permission to assess.

Maintainers should acknowledge reports, assess severity, coordinate a fix and disclosure timeline, and document affected versions. No response-time or remediation guarantee is made until a staffed security process and responsible legal entity exist.

## Legal and operational limitation

Security controls described here are design goals or implementation claims, not a certification or guarantee. Verify the actual release and deployment configuration before use.