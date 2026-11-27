# License inventory

This is a preliminary engineering inventory, not legal advice and not a complete release clearance.

- The inherited Hornet3000 Wächter 1.6.0 source baseline is documented as GPL-3.0-or-later in the provenance notes. Preserve all original copyright and license notices.
- The original `Hornet3000-1.6.0-source.zip` and hardened `Hornet3000-1.6.1-hardened-source.zip` were located in the project Library and their SHA-256 values were verified against their accompanying checksum files on 2026-11-20. The archives are not currently committed to this GitHub tree. The original README declares the bounded Hornet3000 project code as GPL-3.0-or-later and © 2026 Simon Thomas. The 1.6.1 provenance note explicitly limits that declaration to its bounded subproject; it does not license the whole BeeKeeper3000 repository automatically. See [archive provenance audit](docs/ARCHIVE-PROVENANCE-AUDIT-2026-11-20.md). The root `LICENSE` remains intentionally absent until the complete file-by-file rights chain and ownership are confirmed.
- The optional MeshCore binding is pinned to `meshcore==2.3.19`; its upstream Python project declares MIT. Its transitive dependencies are captured in the optional Linux CI lock file, but the complete product SBOM and all-platform lockfiles remain release tasks.
- The Beekeeper-Monitor bridge uses Node.js built-in modules only. `monitor-bridge/package-lock.json` now records its empty third-party dependency graph; npm audit is run in CI.
- `.github/workflows/supply-chain.yml` runs pinned `pip-audit==2.10.1` against the optional MeshCore lock, optional NMEA serial lock, optional camera runtime requirements and the separately declared training runtime requirements. It generates CycloneDX 1.6 CI artifacts using `cyclonedx-bom==9.0.0`; the camera SBOM is generated from an isolated installed Python environment, while the training SBOM covers declared direct requirements only. These SBOMs do not cover the unpublished inherited C++ source, OS libraries, camera firmware/SDKs, model weights, datasets or media assets. See `SUPPLY_CHAIN.md`.
- No model weights or training datasets are bundled here. Model weights, datasets, photos, audio, firmware binaries, map tiles and generated assets require separate source, hash, license and redistribution checks.
- The direct training runtime dependencies are pinned in `training/requirements-training.txt` and audited separately by the supply-chain workflow. Their declared-requirements SBOM is not a complete installed-environment SBOM and does not cover model weights or datasets.
- PyTorch 2.15.0 has a composite package license expression in its [PyPI release metadata](https://pypi.org/project/torch/2.15.0/) and the release page reports no PyPI provenance attestation as of 2026-11-26. Verify the official artifact and bundled third-party notices before installing the optional training runtime.
- The optional components in `OPEN_SOURCE_COMPONENTS.md` are not automatically copied or bundled simply because a license is permissive.

The dated upstream license/security review is maintained in [docs/UPSTREAM-SECURITY-LICENSE-REGISTER-2026-11-20.md](docs/UPSTREAM-SECURITY-LICENSE-REGISTER-2026-11-20.md). It records optional upstream projects and their advisory status as reviewed on that date; it does not grant permission to bundle their code, firmware, models or datasets.

Before a release, produce an SPDX or CycloneDX SBOM for every runtime/build, include authoritative full license texts and notices, verify all transitive dependencies, and have the inherited source/license chain reviewed.


## External Waspinator candidate – checksum-only, not integrated

The optional Waspinator review is limited to the following immutable upstream snapshot:

- Repository: [gitDew/waspinator](https://github.com/gitDew/waspinator)
- Reviewed source revision: `7251be99a69dfc38f82abb062e22a0062ff5c58c`
- Repository licence: the GitHub repository metadata identifies `AGPL-3.0`; the pinned snapshot contains `LICENSE.txt` with the GNU Affero General Public License v3 text.
- Candidate weight: `models/yolo26n-waspinator-chamber_ncnn_model/model.ncnn.bin`; its adjacent `metadata.yaml` declares `AGPL-3.0 License` for the YOLO26n model.
- The upstream `models/attributions.txt` file exists (4,040,560 bytes), but this project has not reviewed it row-by-row or verified it as a complete per-image dataset rights/provenance manifest. The reviewed upstream README does not provide a machine-readable per-image dataset licence and redistribution record.

The repository-level AGPL declaration and model metadata are useful source evidence, **not a complete clearance of the model's training images, embedded attributions, weights, or intended downstream use**. AGPL-3.0 obligations require a separate legal review before incorporation or distribution. Do not treat this candidate as MIT/Apache or as automatically redistributable.

The former workflow `.github/workflows/waspinator-weight-sha256.yml` was removed because run [#45893210187](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/45893210187) fetched the pinned 9,602,112-byte upstream weight file to calculate SHA-256. The runner did not load, execute, convert, train, install, activate or redistribute it; only a 658-byte checksum report was uploaded as artifact [#15151838571](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/45893210187/artifacts/15151838571), expiring 2026-12-26. To avoid further retrieval of an unapproved external model, the replacement workflow `.github/workflows/waspinator-metadata-audit.yml` checks only the pinned commit, file path, declared byte count and Git blob ID through the GitHub metadata API. It does not fetch model bytes, compute SHA-256 or upload an artifact. The Git blob ID is not a SHA-256 digest and does not prove licensing, training-data provenance, class semantics, accuracy or field suitability. The candidate remains absent from production manifests and unavailable to runtime.

**Status: rights and dataset provenance pending; no runtime approval; no field use.** Keep the model out of production manifests until the complete model and training-data rights chain, technical output contract, and independent field evaluation are separately reviewed.
