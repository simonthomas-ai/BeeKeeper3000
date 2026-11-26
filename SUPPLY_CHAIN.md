# Supply-chain coverage and release limits

This register documents what automated checks actually cover. It is not a statement that the entire unpublished Hornet3000 source package or every optional upstream project has been cleared for redistribution.

## Automated checks

| Surface | Control | CI behaviour |
|---|---|---|
| Python optional MeshCore dependency set | `network/meshcore/requirements.lock` | Exact top-level and captured transitive versions are audited with pinned `pip-audit==2.10.1 --no-deps`; the lock file carries the reviewed dependency set |
| Optional NMEA serial adapter | `adapters/nmea-requirements.lock` | Exact pinned requirements are checked with `pip-audit --no-deps --strict`; the matching CycloneDX requirements SBOM is uploaded |
| Optional camera runtime | `camera/requirements.txt` | `pip-audit` resolves and checks direct plus transitive dependency vulnerabilities; camera runtime SBOM is generated from an isolated installed Python 3.12 environment |
| Optional training runtime | `training/requirements-training.txt` | `pip-audit` resolves and checks the declared training runtime and transitive dependencies; no training, model download or dataset access is performed by this audit |
| Python optional MeshCore dependency set | CycloneDX | A reproducible CycloneDX JSON SBOM is generated from the pinned requirements set and uploaded as a CI artifact (90-day retention) |
| Optional NMEA serial adapter | CycloneDX | A reproducible CycloneDX 1.6 requirements SBOM is generated and uploaded as a CI artifact (90-day retention) |
| Optional camera runtime | CycloneDX | A reproducible CycloneDX 1.6 SBOM is generated from the actual isolated Python 3.12 environment and uploaded as a CI artifact (90-day retention) |
| Optional training runtime | CycloneDX | A reproducible CycloneDX 1.6 SBOM covers the declared direct training requirements only; it is not a complete installed-environment SBOM |
| Node.js bridge | `monitor-bridge/package-lock.json` | `npm ci` plus `npm audit --audit-level=low`; bridge currently has no third-party runtime dependencies |
| Source code | CodeQL | Python and JavaScript/TypeScript static analysis |
| Dependency update process | Dependabot | Weekly checks for npm, Python and GitHub Actions manifests |
| External GitHub Actions references | `scripts/audit_workflow_action_pins.py` | Quality-gates CI scans all 10 workflow YAML files; external actions require full 40-character commit SHAs, local actions are allowed, Docker actions require SHA-256 digests |
| Workflow container images | `scripts/audit_workflow_action_pins.py` | Every YAML `image:` reference must use an immutable OCI SHA-256 digest; mutable tags block Quality-gates CI |
| Checkout credentials | `scripts/audit_workflow_action_pins.py` | Every `actions/checkout` step in all workflow YAML files must set `persist-credentials: false`; missing or true values block Quality-gates CI |

The CI audit tool versions are pinned in `.github/workflows/supply-chain.yml`. All workflow checkout steps disable persisted Git credentials; this removes the read-only `GITHUB_TOKEN` from the local Git configuration after checkout. The workflow path filters include this register so documentation changes to the declared audit scope are tested. Generated SBOMs are CI artifacts, not yet a complete release SBOM for the inherited Hornet3000 product.

## Scope limitations that remain release blockers

- The repository contains only a staged subset of Hornet3000 Wächter 1.6.0. The complete inherited C++/CMake source and all original build manifests are not present in the currently published tree.
- The root `LICENSE` file and repository-level GitHub license metadata are missing. Do not assume the repository can be redistributed under a single license until the original full source archive and notices are restored and reviewed.
- The Python SBOMs cover the optional MeshCore and NMEA requirement sets, the installed camera runtime, and the declared direct training requirements. The training SBOM is not a complete resolved environment inventory. The bridge is a zero-external-dependency Node.js module. These SBOMs do not inventory missing C++ build dependencies, firmware binaries, all operating-system packages, every inference runtime, camera SDKs, model weights, training datasets, photos, audio, map tiles or future adapters.
- PyTorch 2.15.0 is an optional training pin whose PyPI release page did not show a provenance attestation at the 2026-11-26 review; its package metadata has a composite license expression. Do not install it for training until the official artifact origin and bundled third-party notices have been independently verified. See `LICENSES.md` and `docs/TRAINING-DEPENDENCY-REVIEW.md`.
- The MeshCore requirements lock is a Linux CI lock captured for the current optional binding; other operating systems and hardware require independent resolution and testing.
- The SBOM generator and audit tools are themselves CI tools, not product runtime dependencies.
- All external GitHub Actions references and workflow container-image references are now checked automatically by `scripts/audit_workflow_action_pins.py` in the BeeKeeper3000 quality-gates workflow. The audit scans every workflow YAML file, requires a full 40-character commit SHA for external actions, permits local action paths, and requires SHA-256 digests for Docker actions and every `image:` field. Runtime dependencies, operating-system packages, firmware, model weights and datasets remain separate supply-chain surfaces and must be inventoried independently.
- Secret scanning depends on repository/account feature availability; do not treat CodeQL or dependency auditing as a substitute for secret scanning.

## Reproducible local commands

From the repository root:

```sh
python -m pip install "pip-audit==2.10.1"
pip-audit --requirement network/meshcore/requirements.lock --no-deps --strict
pip-audit --requirement adapters/nmea-requirements.lock --no-deps --strict
pip-audit --requirement camera/requirements.txt --strict
pip-audit --requirement training/requirements-training.txt --strict

python -m pip install "cyclonedx-bom==9.0.0"
cyclonedx-py requirements network/meshcore/requirements.lock \
  --spec-version 1.6 --output-format JSON --output-reproducible \
  --output-file meshcore-runtime.cdx.json

cyclonedx-py requirements adapters/nmea-requirements.lock --spec-version 1.6 --output-format JSON --output-reproducible --output-file nmea-serial.cdx.json
cyclonedx-py requirements training/requirements-training.txt --spec-version 1.6 --output-format JSON --output-reproducible --output-file training-declared-requirements.cdx.json

npm --prefix monitor-bridge ci --ignore-scripts --no-audit --no-fund
npm --prefix monitor-bridge audit --audit-level=low
```

A clean dependency audit is only an advisory-database result for the versions and package set named above. It does not prove license compatibility, source provenance, safe runtime behaviour or compliance.


## Dated upstream evidence

The component license/security review is maintained in [docs/UPSTREAM-SECURITY-LICENSE-REGISTER-2026-11-20.md](docs/UPSTREAM-SECURITY-LICENSE-REGISTER-2026-11-20.md). Changes to that register now trigger the supply-chain CI workflow.
