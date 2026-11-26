# Training runtime dependency review

The training entry point `training/train_multilabel.py` checks these direct runtime
versions before training:

- Pillow 13.0.0
- ONNX 1.23.2
- PyTorch 2.15.0

The direct pins are declared in `training/requirements-training.txt`. The supply-chain
workflow runs `pip-audit` against that file with dependency resolution and
emits a CycloneDX artifact for the declared requirements. The previous pins
(Pillow 12.0.0, ONNX 1.20.1 and PyTorch 2.9.1) produced 103 advisory findings
in the initial audit; the current pins were selected from patched releases and
must pass the rerun before merge. The audit is a
dependency-vulnerability check, not a model, dataset or license approval.

The declared-requirements SBOM is not a complete installed-environment SBOM.
The full transitive dependency graph and any platform-specific wheel/runtime
components must be reviewed before a training environment is approved.

As of 2026-11-26, the PyPI release page reports provenance metadata for Pillow
13.0.0 and ONNX 1.23.2, but no PyPI provenance attestation for PyTorch 2.15.0.
PyTorch's package metadata also lists a composite license expression, not only
BSD-3-Clause. Verify the official PyTorch artifact origin and all bundled
third-party notices before installing the optional training runtime. A clean
pip-audit result is not a publisher-authenticity or license approval.

CI does not install PyTorch, run training, download weights or access a dataset.
No model or training-data permission is implied by these package pins.
