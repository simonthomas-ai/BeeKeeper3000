# Supply-chain coverage and release limits

This register documents what automated checks actually cover. It is not a statement that the entire unpublished Hornet3000 source package or every optional upstream project has been cleared for redistribution.

## Automated checks

| Surface | Control | CI behaviour |
|---|---|---|
| Python optional MeshCore dependency set | `network/meshcore/requirements.lock` | Exact top-level and captured transitive versions are audited with pinned `pip-audit==2.10.1`; unresolved package collection is treated as failure |
| Optional camera runtime | `camera/requirements.txt` | `pip-audit` checks direct and resolved dependency vulnerabilities; camera runtime SBOM is generated from an isolated environment after installing the pinned requirements |
| Python optional MeshCore dependency set | CycloneDX | A reproducible CycloneDX JSON SBOM is generated from the pinned requirements set and uploaded as a CI artifact (90-day retention) |
| Optional camera runtime | CycloneDX | A reproducible CycloneDX 1.6 SBOM is generated from the actual isolated Python 3.12 environment and uploaded as a CI artifact (90-day retention) |
| Node.js bridge | `monitor-bridge/package-lock.json` | `npm ci` plus `npm audit --audit-level=low`; bridge currently has no third-party runtime dependencies |
| Source code | CodeQL | Python and JavaScript/TypeScript static analysis |
| Dependency update process | Dependabot | Weekly checks for npm, Python and GitHub Actions manifests |
| External GitHub Actions references | `scripts/audit_workflow_action_pins.py` | Quality-gates CI scans all 10 workflow YAML files; external actions require full 40-character commit SHAs, local actions are allowed, Docker actions require SHA-256 digests |
| Workflow container images | `scripts/audit_workflow_action_pins.py` | Every YAML `image:` reference must use an immutable OCI SHA-256 digest; mutable tags block Quality-gates CI |
| Checkout credentials | `scripts/audit_workflow_action_pins.py` | Every `actions/checkout` step in all workflow YAML files must set `persist-credentials: false`; missing or true values block Quality-gates CI |

The CI audit tool versions are pinned in `.github/workflows/supply-chain.yml`. All workflow checkout steps disable persisted Git credentials; this removes the read-only `GITHUB_TOKEN` from the local Git configuration after checkout. The generated SBOM is a CI artifact, not yet a complete release SBOM for the inherited Hornet3000 product.

## Scope limitations that remain release blockers

- The repository contains only a staged subset of Hornet3000 Wächter 1.6.0. The complete inherited C++/CMake source and all original build manifests are not present in the currently published tree.
- The root `LICENSE` file and repository-level GitHub license metadata are missing. Do not assume the repository can be redistributed under a single license until the original full source archive and notices are restored and reviewed.
- The Python SBOM covers the optional MeshCore binding lock only. The bridge is a zero-external-dependency Node.js module. It does not inventory missing C++ build dependencies, firmware binaries, operating-system packages, inference runtime, camera SDKs, model weights, training datasets, photos, audio, map tiles or future adapters.
- The MeshCore requirements lock is a Linux CI lock captured for the current optional binding; other operating systems and hardware require independent resolution and testing.
- The SBOM generator and audit tools are themselves CI tools, not product runtime dependencies.
- All external GitHub Actions references and workflow container-image references are now checked automatically by `scripts/audit_workflow_action_pins.py` in the BeeKeeper3000 quality-gates workflow. The audit scans every workflow YAML file, requires a full 40-character commit SHA for external actions, permits local action paths, and requires SHA-256 digests for Docker actions and every `image:` field. Runtime dependencies, operating-system packages, firmware, model weights and datasets remain separate supply-chain surfaces and must be inventoried independently.
- Secret scanning depends on repository/account feature availability; do not treat CodeQL or dependency auditing as a substitute for secret scanning.

## Reproducible local commands

From the repository root:

```sh
python -m pip install "pip-audit==2.10.1"
pip-audit --requirement network/meshcore/requirements.lock --no-deps --strict
pip-audit --requirement camera/requirements.txt --strict

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
