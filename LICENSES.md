# License inventory

This is a preliminary engineering inventory, not legal advice and not a complete release clearance.

- The inherited Hornet3000 Wächter 1.6.0 source baseline is documented as GPL-3.0-or-later in the provenance notes. Preserve all original copyright and license notices.
- The currently published BeeKeeper3000 repository tree must be checked against the complete upstream source package before redistribution. A root `LICENSE` file and the full source archive are not present in the reviewed published tree; do not infer that the repository-wide license metadata is complete.
- The optional MeshCore binding is pinned to `meshcore==2.3.19`; its upstream Python project declares MIT. Its transitive dependencies are captured in the optional Linux CI lock file, but the complete product SBOM and all-platform lockfiles remain release tasks.
- The Beekeeper-Monitor bridge uses Node.js built-in modules only. `monitor-bridge/package-lock.json` now records its empty third-party dependency graph; npm audit is run in CI.
- `.github/workflows/supply-chain.yml` runs pinned `pip-audit==2.10.1` against the optional MeshCore lock and optional camera runtime requirements; it generates a CycloneDX 1.6 JSON CI artifact for both Python dependency sets using `cyclonedx-bom==9.0.0`. The camera SBOM is generated from an isolated installed Python environment. These SBOMs do not cover the unpublished inherited C++ source, OS libraries, camera firmware/SDKs, model weights, datasets or media assets. See `SUPPLY_CHAIN.md`.
- No model weights or training datasets are bundled here. Model weights, datasets, photos, audio, firmware binaries, map tiles and generated assets require separate source, hash, license and redistribution checks.
- The optional components in `OPEN_SOURCE_COMPONENTS.md` are not automatically copied or bundled simply because a license is permissive.

The dated upstream license/security review is maintained in [docs/UPSTREAM-SECURITY-LICENSE-REGISTER-2026-11-20.md](docs/UPSTREAM-SECURITY-LICENSE-REGISTER-2026-11-20.md). It records optional upstream projects and their advisory status as reviewed on that date; it does not grant permission to bundle their code, firmware, models or datasets.

Before a release, produce an SPDX or CycloneDX SBOM for every runtime/build, include authoritative full license texts and notices, verify all transitive dependencies, and have the inherited source/license chain reviewed.
