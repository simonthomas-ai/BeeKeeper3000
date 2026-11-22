# Upstream license and security register — baseline 2026-11-20, refresh 2026-11-22

> Refresh note (2026-11-22): release-channel and advisory information for Meshtastic, Mosquitto and Freenet was rechecked against official upstream pages. This supplements, and does not replace, the immutable source/license snapshot table below.

This is a dated engineering review of optional components named in this project. It is not legal advice, a complete product SBOM, or permission to copy upstream code, firmware, models or datasets. None of the optional components below is silently added to the current runtime by this register.

## Status matrix

| Component | Upstream license evidence | Current use here | Security/release evidence reviewed 2026-11-20 | Decision |
|---|---|---|---|---|
| MeshCore firmware | MIT, upstream `license.txt` | Optional adapter uses the separately pinned Python binding `meshcore==2.3.19`; no firmware binary is vendored | Upstream latest release observed: Companion/Repeater/Room Server v1.18.0, release 2026-10-15. Target radio/board firmware must be pinned independently by SHA-256 and board ID. | Keep optional. Do not call the hardware adapter field-ready until the exact device firmware, region settings, radio permissions and repeaters are field-tested. |
| Meshtastic firmware | GPL-3.0 | Not integrated | Official Downloads page reviewed 2026-11-22 lists 2.7.26.54e0d8d as the Stable channel (Beta-labelled build) and 2.8.2.d5f1619 as Alpha; 2.8.3 is only Nightly. GHSA-mjx5-98jq-q736 (Critical, published 2026-04-20) concerns a `pull_request_target` workflow/fork-checkout RCE in upstream CI; this is an upstream development-pipeline risk, not proof of a firmware runtime exploit. GHSA-7ph5-2mjv-69h8 (High, published 2026-07-09; CVE-2026-42566) lists affected firmware <=2.7.22.96dd647. | Do not classify 2.8.2 Alpha or Nightly as stable. Keep Meshtastic isolated and optional; if a target is selected, record exact board, firmware file SHA-256, region/radio settings and review advisories for that exact release. Recheck the upstream security policy at deployment. |
| Freenet Core | AGPL-3.0 | Not integrated | Upstream `LICENSE.md` explains that clients linking only to `freenet-stdlib` (LGPL-3.0) or communicating by HTTP/WebSocket do not automatically make the client app AGPL; a modified deployed core remains under AGPL obligations. | Optional IP/P2P research only. Use a protocol client boundary; do not embed/fork core without a separate license and deployment review. Freenet is not LoRa radio transport. |
| Insect Detect | GPL-3.0 | Not integrated; benchmark/reference only | Repository source license does not establish rights for separately downloaded model weights, images or datasets. | Do not reuse model binaries/data until each artifact has source, version/hash, license and use rights recorded. |
| Insect Detect ML | AGPL-3.0 | Not integrated | Training notebooks and datasets/models are separate artifacts; repository license alone is not sufficient provenance. | Keep isolated until network-copyleft, training data, model-weight and commercial/public-service use conditions are reviewed. |
| Eclipse Mosquitto | EPL-2.0 / EDL-1.0 | Not integrated | GHSA-6j8m-r32v-4h38 / CVE-2026-110486 (Critical, 2026-11-17): 2.1.0–2.1.2 built-in WebSocket listener vulnerable; security fix in 2.1.3. GHSA-878w-672v-qwmf / CVE-2026-126708 (2026-11-17): affected 2.0.0–2.0.22 and 2.1.0–2.1.2; fixed in 2.0.23/2.1.3. Upstream then released 2.1.4 on 2026-11-17 to fix a legacy SHA-512 password-authentication regression introduced in 2.1.3. | No current exposure because Mosquitto is not a dependency. If later adopted, prefer 2.1.4 or later in the 2.1 line, or 2.0.23+ in the 2.0 line; disable WebSockets if no security-reviewed listener is required. Pin and audit the exact package and TLS/auth configuration. |
| MapLibre GL JS | BSD-3-Clause | Not integrated | GHSA-jrc7-96c5-q579 / CVE-2026-85061 (Critical, published 2026-08-19): versions <=6.4.0 affected by DOM sanitizer XSS bypass; fixed in 6.4.1. | If adopted, require >=6.4.1 and review style/attribution input plus tile-provider terms. No current project exposure because package is absent. |
| QGIS | GPL-2.0 | External expert workflow only | No QGIS code or binary is included in this repository. | Keep as an external workflow; account separately for plugins, providers and data. |

## Current repository dependency evidence

- The optional MeshCore Python binding is pinned in `network/meshcore/requirements.lock` for Linux CI: `meshcore==2.3.19` plus its captured transitive packages. This is not a universal cross-platform lock.
- The Node bridge uses Node built-ins only. Its committed npm lockfile currently contains no third-party npm package entries.
- `.github/workflows/supply-chain.yml` runs pinned `pip-audit==2.10.1` against the optional Python lock, generates a CycloneDX 1.6 artifact with pinned `cyclonedx-bom==9.0.0`, and runs `npm audit` against the Node lock.
- These checks cover only those exact manifests. They do not cover missing inherited C++/CMake sources, hardware firmware, operating-system packages, model runtimes, weights, datasets, image/audio assets or future adapters.
- GitHub Actions references in the reviewed first-party workflows are now pinned to immutable 40-character commit SHAs: BeeKeeper3000 (4 workflow files, 6 external action references) and Beekeeper-Monitor (19 workflow files, 13 external action references), verified against both repositories' `main` branches on 2026-11-20. Future workflow additions must keep this SHA-pinning rule; Dependabot updates should be reviewed and tested before merge.
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

## Upstream refresh — 2026-11-22

- Meshtastic official Downloads currently presents `2.7.26.54e0d8d Beta` under the Stable heading, `2.8.2.d5f1619 Alpha` under Alpha and Nightly builds separately. Do not describe 2.8.x as the only stable branch or treat the 2.8.2 Alpha as a production release. Each actual board firmware must be chosen and hashed independently.
- Eclipse Mosquitto upstream published 2.1.4, 2.1.3 and 2.0.23 on 2026-11-17. 2.1.3 contains the critical WebSocket-frame security fixes; 2.1.4 additionally repairs a legacy SHA-512 password regression introduced by 2.1.3. New adoption floor: 2.1.4+ (preferred 2.1 branch) or 2.0.23+ (2.0 branch), subject to fresh advisory review.
- Freenet Core release page currently lists `v0.2.151` as Latest (2026-10-27). This is a candidate version snapshot only: Freenet remains unin­tegrated, its actual client/core topology and AGPL/LGPL boundary must be reviewed before implementation.

## Immutable upstream source and license-file references

The following values were retrieved from the upstream GitHub Content/Commit APIs on 2026-11-20. The commit SHA is an immutable snapshot of the upstream default branch at review time; it is **not** a declaration that this arbitrary HEAD is the product's approved runtime version. The license SHA is GitHub's Git blob object ID for the named license file (not a raw-file SHA-256). Tags/releases must still be selected and pinned deliberately at integration time.

| Upstream repository | Default-branch commit SHA reviewed | License file | License blob SHA |
|---|---|---|---|
| `meshcore-dev/MeshCore` | `75b04ef06def54b348400cb1b138afb6749ffd4f` | `license.txt` (MIT) | `4b1f85cefcf80306f65e5066af20950bca0fff33` |
| `meshtastic/firmware` | `bb3c25eb6701ebec89e8ad6c4d01c35d0d3b5e62` | `LICENSE` (GPL-3.0) | `10926e87f113fb026c366866d6fa466061562870` |
| `freenet/freenet-core` | `3965e511e36f845381cf13cee4fc1a64f5bff07e` | `LICENSE.md` (AGPL-3.0; includes upstream explanatory section) | `434fbfa8db3c1c6bd9b525d4e0e42111d3369b8e` |
| `freenet/freenet-stdlib` | `7782c176a622efc3f284ce4710b4f184c4986405` | `LICENSE.md` (LGPL-3.0) | `6fb6a01ee0c21468ff46438fb765f0ae1e5bd98e` |
| `maxsitt/insect-detect` | `f1a70c997ed6430f4ce0b8fe852d2fbccf05c513` | `LICENSE` (GPL-3.0) | `e62ec04cdeece724caeeeeaeb6ae1f6af1bb6b9a` |
| `maxsitt/insect-detect-ml` | `23c772666cd8610646257292a8d91b4318ff08ee` | `LICENSE` (AGPL-3.0) | `0ad25db4bd1d86c452db3f9602ccdbe172438f52` |
| `eclipse-mosquitto/mosquitto` | `7ae66ca5cf5e75dca18ba2f6cbdd21453c8e51a5` | `LICENSE.txt` (EPL-2.0 OR EDL-1.0) | `aae2e8ccf529cef6b058f98ede72090f6ae92721` |
| `maplibre/maplibre-gl-js` | `7a6b265daecebb91e082f85d4fef09a8f75d84b0` | `LICENSE.txt` (BSD-3-Clause) | `1e8acbb54fa7baddc844377507cc5a79353174fb` |
| `qgis/QGIS` | `32f15392873079dfca31b0b8e327fe7f3013569a` | `COPYING` (GPL-2.0) | `8e2daf6bc046673223b197d859fa9609255ef13c` |

### Reproducibility limits

- Upstream default-branch commit snapshots and license blob IDs above can be re-fetched and compared; they do not replace release tags, signed releases, binary hashes or a software bill of materials for an actually selected integration.
- Freenet Core's explanatory license text is upstream-authored guidance. A real integration still needs a legal review of the actual linking, process, packaging and deployment arrangement.
- No model weights, datasets, photos, audio, firmware or map tiles were downloaded or incorporated as part of this review; their hashes and permissions remain unverified.
- The repository's inherited Hornet3000 root license chain remains unresolved because the full source archive and original notices are still not present.

## Current in-repository audit outcome

As of this review:
- Node dependency audit completed successfully for the committed lockfile, which contains no third-party package entries.
- Python vulnerability audit completed successfully for the exact optional MeshCore lock file.
- CycloneDX 1.6 generation and JSON validation completed successfully for that same optional Python lock.
- CodeQL Python and JavaScript/TypeScript analysis completed successfully for the component-register change.
- These results do not imply that unmanifested firmware/model/C++ dependencies or the full product are free of vulnerabilities.

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

Baseline review: 2026-11-20; upstream refresh: 2026-11-22. Re-check advisories, release channels, exact firmware tags and package hashes at every deployment/release.
