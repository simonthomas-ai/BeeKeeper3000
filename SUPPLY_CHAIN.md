# Supply-chain coverage and release limits

This register documents what automated checks actually cover. It is not a statement that the entire unpublished Hornet3000 source package or every optional upstream project has been cleared for redistribution.

## Automated checks

| Surface | Control | CI behaviour |
|---|---|---|
| Python optional MeshCore dependency set | `network/meshcore/requirements.lock` | Exact top-level and captured transitive versions are audited with pinned `pip-audit==2.10.1`; unresolved package collection is treated as failure |
| Python optional MeshCore dependency set | CycloneDX | A reproducible CycloneDX JSON SBOM is generated from the pinned requirements set and uploaded as a CI artifact (90-day retention) |
| Node.js bridge | `monitor-bridge/package-lock.json` | `npm ci` plus `npm audit --audit-level=low`; bridge currently has no third-party runtime dependencies |
| Source code | CodeQL | Python and JavaScript/TypeScript static analysis |
| Dependency update process | Dependabot | Weekly checks for npm, Python and GitHub Actions manifests |

The CI audit tool versions are pinned in `.github/workflows/supply-chain.yml`. The generated SBOM is a CI artifact, not yet a complete release SBOM for the inherited Hornet3000 product.

## Scope limitations that remain release blockers

- The repository contains only a staged subset of Hornet3000 Wächter 1.6.0. The complete inherited C++/CMake source and all original build manifests are not present in the currently published tree.
- The root `LICENSE` file and repository-level GitHub license metadata are missing. Do not assume the repository can be redistributed under a single license until the original full source archive and notices are restored and reviewed.
- The Python SBOM covers the optional MeshCore binding lock only. The bridge is a zero-external-dependency Node.js module. It does not inventory missing C++ build dependencies, firmware binaries, operating-system packages, inference runtime, camera SDKs, model weights, training datasets, photos, audio, map tiles or future adapters.
- The MeshCore requirements lock is a Linux CI lock captured for the current optional binding; other operating systems and hardware require independent resolution and testing.
- The SBOM generator and audit tools are themselves CI tools, not product runtime dependencies.
- All external GitHub Actions references in the reviewed workflow sets are pinned to immutable 40-character commit SHAs. Main-branch verification on 2026-11-20 covered 4 BeeKeeper3000 workflow files (6 references) and 19 Beekeeper-Monitor workflow files (13 references). New workflow actions must also be SHA-pinned; review Dependabot updates and rerun CI before merging.
- Secret scanning depends on repository/account feature availability; do not treat CodeQL or dependency auditing as a substitute for secret scanning.

## Reproducible local commands

From the repository root:

```sh
python -m pip install "pip-audit==2.10.1"
pip-audit --requirement network/meshcore/requirements.lock --no-deps --strict

python -m pip install "cyclonedx-bom==9.0.0"
cyclonedx-py requirements network/meshcore/requirements.lock \
  --spec-version 1.6 --output-format JSON --output-reproducible \
  --output-file meshcore-runtime.cdx.json

npm --prefix monitor-bridge ci --ignore-scripts --no-audit --no-fund
npm --prefix monitor-bridge audit --audit-level=low
```

A clean dependency audit is only an advisory-database result for the versions and package set named above. It does not prove license compatibility, source provenance, safe runtime behaviour or compliance.


## Dated upstream evidence

The component license/security review is maintained in [docs/UPSTREAM-SECURITY-LICENSE-REGISTER-2026-11-20.md](docs/UPSTREAM-SECURITY-LICENSE-REGISTER-2026-11-20.md). Changes to that register now trigger the supply-chain CI workflow.
