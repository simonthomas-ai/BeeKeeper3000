# Waspinator: independent real-image evaluation gate

**Status: BLOCKED — no independent held-out, rights-cleared, expert-annotated real-image test set has been established.**

The isolated upstream NCNN weights SHA-256 workflow and metadata audit verify downloaded bytes and upstream file existence only. They do not demonstrate model accuracy, safe inference, rights clearance or readiness for production.

## Requirements before any inference benchmark

1. Collect actual photographs from rights-cleared sources, independently annotated by qualified reviewers. No synthetic, generated, duplicated or guessed labels. Do not commit private photos or location metadata to this public repository.
2. Include **Vespa velutina** and **Vespa crabro** as the two upstream model classes. Bees, bumblebees and other wasps must be included as *out-of-distribution negative examples*; the upstream two-class model does not have dedicated labels for these.
3. Record original image hashes, source, rights, annotation review, sampling, capture conditions, train/test separation and exclusion of leakage.
4. Execute inference **only in an isolated, unprivileged environment**, using a compatible NCNN runtime with pinned dependency versions and the exact model SHA-256 from the verified artifact. Do not load upstream PyTorch `.pt` files through unsafe deserialization.
5. Produce one JSONL record per real image using the schema in [MODEL-EVALUATION.md](MODEL-EVALUATION.md), with independently established `ground_truth` and actual model `predictions`; preserve the exact mapping `0=Vespa_velutina`, `1=Vespa_crabro` only after verifying upstream metadata.
6. Evaluate using `python -m camera.evaluate_detections --annotations <private-test.jsonl> --output <private-report.json> --iou 0.5 --confidence 0.25`. Publish only aggregate metrics after privacy and license review.
7. Record TP/FP/FN, precision, recall, AP@IoU 0.5 per class, false alerts on negative examples, confidence calibration, device performance, and field failures. Review dataset, model and Ultralytics/AGPL attribution and distribution requirements before any integration.

**No 99% accuracy claim, production model approval, or PWA deployment is authorized by the checksum audit.** The evaluation must remain blocked until the real test set and licensed inference runtime are available.
