# Waspinator: independent real-image evaluation gate

**Status: BLOCKED — no independent held-out, rights-cleared, expert-annotated real-image test set has been established.**

## Audit history and current controls – 27.11.2026

- In historical run [#45893210187](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/45893210187), the former checksum workflow downloaded exactly 9,602,112 bytes from the pinned upstream NCNN weight solely to calculate SHA-256. The job log confirms the bytes were **not loaded, imported, executed, converted, trained, installed, activated or redistributed**.
- That run uploaded only a 658-byte checksum report, artifact [#15151838571](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/45893210187/artifacts/15151838571); it did not upload the model weights. At the 27.11.2026 audit this report artifact still existed and was due to expire on 26.12.2026.
- PR [#134](https://github.com/simonthomas-ai/BeeKeeper3000/pull/134) removed the byte-downloading workflow. The current [pinned metadata audit](../.github/workflows/waspinator-metadata-audit.yml) checks commit, path, byte count and Git blob metadata through the GitHub API; it does not fetch model bytes or compute SHA-256.
- The [upstream tree audit](../.github/workflows/waspinator-upstream-audit.yml) also reads metadata only. This change removes its 30-day Actions artifact upload; its report remains in the job summary rather than becoming a separate public artifact.
- A Git blob ID is not a file SHA-256. Neither metadata audit establishes licensing, image provenance, accuracy, runtime compatibility or field suitability.

The old 658-byte report is historical and remains publicly accessible until it is deleted or expires. The model weights themselves are not present in the repository or the report artifact.

## Requirements before any inference benchmark

1. Collect actual photographs from rights-cleared sources, independently annotated by qualified reviewers. No synthetic, generated, duplicated or guessed labels. Do not commit private photos or location metadata to this public repository.
2. Include **Vespa velutina** and **Vespa crabro** as the two upstream model classes. Bees, bumblebees and other wasps must be included as *out-of-distribution negative examples*; the upstream two-class model does not have dedicated labels for these.
3. Record original image hashes, source, rights, annotation review, sampling, capture conditions, train/test separation and exclusion of leakage.
4. Execute inference **only in an isolated, unprivileged environment**, using a compatible NCNN runtime with pinned dependency versions and a verified model file obtained only after a separate human rights approval. Do not load upstream PyTorch `.pt` files through unsafe deserialization.
5. Produce one JSONL record per real image using the schema in [MODEL-EVALUATION.md](MODEL-EVALUATION.md), with independently established `ground_truth` and actual model `predictions`; preserve the exact mapping `0=Vespa_velutina`, `1=Vespa_crabro` only after verifying upstream metadata.
6. Evaluate using `python -m camera.evaluate_detections --annotations <private-test.jsonl> --output <private-report.json> --iou 0.5 --confidence 0.25`. Publish only aggregate metrics after privacy and license review.
7. Record TP/FP/FN, precision, recall, AP@IoU 0.5 per class, false alerts on negative examples, confidence calibration, device performance, and field failures. Review dataset, model and Ultralytics/AGPL attribution and distribution requirements before any integration.

**No 99% accuracy claim, production model approval, or PWA deployment is authorized by metadata or checksum audits.** The evaluation must remain blocked until the real test set, complete rights chain and licensed inference runtime are available.
