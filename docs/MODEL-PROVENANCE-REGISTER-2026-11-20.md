# External model and dataset provenance register — 20.11.2026

**Purpose:** identify reusable Vespa velutina detector assets without importing files whose exact model/data rights are not established. This is an engineering screening, not a legal opinion.

## Candidate review

| Candidate | Observed evidence | Decision |
|---|---|---|
| [vespCV/hornet3000](https://github.com/vespCV/hornet3000) | Public repository marked GPL-3.0; archived 07.06.2025. Tracks YOLOv8s `best.onnx` (44,737,849 bytes) and `best.pt`. README says training/validation images came mainly from waarnemingen.nl/Observation.org using “approved” and “shareable licenses”, with the dataset on Kaggle. No artifact-level weight license, per-image license manifest, immutable training-dataset snapshot or permission chain was found in the reviewed README/manual. | **HOLD — do not bundle, redistribute or mark approved.** Ask the maintainer for explicit weight licensing, source dataset version, per-image rights/attribution and the model's corresponding training source. Repository GPL marker alone does not prove the training-data rights or the exact weight artifact's status. |
| [vespCV/vespcv](https://github.com/vespCV/vespcv) | Repository has a `best.pt` artifact (19,174,547 bytes) and training results. GitHub repository metadata reports `NOASSERTION`; no complete model/dataset rights chain was established. | **HOLD — no import.** Obtain an explicit license and data provenance from the maintainers. |
| [andrw3000/vespai](https://github.com/andrw3000/vespai) | Repository LICENSE explicitly states CC BY-NC-SA 4.0 for repository material and AGPL-3.0 for constituent model code. It contains YOLOv5 model weights and references Plainsight labelling outputs. | **REJECT for general-purpose distribution.** NonCommercial and ShareAlike conditions restrict downstream uses; they do not satisfy the project's intended unrestricted free/open reuse. Do not combine these weights or code into BeeKeeper3000. |
| [PauMonterosa/vespa-velutina-tracker](https://github.com/PauMonterosa/vespa-velutina-tracker) | README reports experimental YOLOv8s metrics and says a `best.pt` exists locally, but the model binaries are ignored by Git. The README also says the exact dataset YAML and source-dataset licenses are missing. | **HOLD — no usable weight artifact or rights chain.** Reported metrics are not transferable evidence for this project. |
| [Roboflow ISR Vespa velutina dataset v1](https://universe.roboflow.com/institute-of-systems-and-robotics-isr/vespa-velutina-hihv9-upzpe/dataset/1) | Dataset page labels it CC BY 4.0 and lists 1,508 images in the version record; the generated dataset view reports augmentation and train/validation/test splits. | **CANDIDATE DATA ONLY — not imported.** Verify uploader authority, underlying image sources, per-image attribution, current terms, split leakage and whether redistribution of the processed set is permitted before use. CC BY 4.0 on the dataset page is not proof that every underlying photograph was licensed by its actual rights holder. |

## Licensing and technical rules

1. Do not assume that a repository's software license automatically covers separately trained weights, source photographs, third-party datasets or model outputs.
2. A model trained on a dataset may have rights/terms implications beyond the source code license. Require a documented legal review of the exact weight artifact and dataset.
3. NonCommercial terms are not accepted for the general BeeKeeper3000 distribution profile; a non-profit project can still have commercial users or uses.
4. Do not import models with missing, ambiguous or incompatible licensing into the public repository.
5. Before a model can pass `camera/model_manifest.py`, the local manifest must contain the exact model SHA-256, upstream artifact URL, license evidence URL, named reviewer, timezone-aware review timestamp, and explicit inference/redistribution permissions.
6. After rights clearance, convert the candidate to the supported ONNX output contract, record conversion tooling/versions and hashes, then evaluate it using an independently annotated held-out dataset with the documented evaluator.
7. Do not publish model metrics from the upstream README as BeeKeeper3000 results.

## Current outcome

**No external model is approved for BeeKeeper3000.** The fail-closed manifest therefore remains without an approved production model. The evaluation harness and camera pipeline are ready for a properly licensed candidate, but the project must not fabricate detections or imply that a model is installed.

## References

- vespCV/hornet3000 README, model files and GPL-3.0 repository license: https://github.com/vespCV/hornet3000
- vespCV/vespcv model tree and repository metadata: https://github.com/vespCV/vespcv
- VespAI license and weights: https://github.com/andrw3000/vespai
- Vespa Velutina Tracker README: https://github.com/PauMonterosa/vespa-velutina-tracker
- Roboflow ISR dataset v1: https://universe.roboflow.com/institute-of-systems-and-robotics-isr/vespa-velutina-hihv9-upzpe/dataset/1
- Kaggle Hornet3000+ dataset referenced by vespCV: https://www.kaggle.com/datasets/marcoryvandijk/vespa-velutina-v-crabro-vespulina-vulgaris
