# Training runtime dependency review

The training entry point `training/train_multilabel.py` checks these direct runtime
versions before training:

- Pillow 12.0.0
- ONNX 1.20.1
- PyTorch 2.9.1

The direct pins are declared in `training/requirements.txt`. The supply-chain
workflow runs `pip-audit` against that file with dependency resolution and
emits a CycloneDX artifact for the declared requirements. The audit is a
dependency-vulnerability check, not a model, dataset or license approval.

The declared-requirements SBOM is not a complete installed-environment SBOM.
The full transitive dependency graph and any platform-specific wheel/runtime
components must be reviewed before a training environment is approved.

CI does not install PyTorch, run training, download weights or access a dataset.
No model or training-data permission is implied by these package pins.
