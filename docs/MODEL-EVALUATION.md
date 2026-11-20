# Model evaluation: independent held-out data

The repository provides `camera/evaluate_detections.py` to compute per-class TP/FP/FN, precision, recall, F1 and 101-point interpolated AP at a selected IoU threshold.

## Annotation format

One UTF-8 JSON object per line (JSONL). Keep images, exact locations and source media private. Example:

```json
{"image_id":"private-image-0001","image_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","ground_truth":[{"class_id":0,"bbox_xyxy":[10,10,100,100]}],"predictions":[{"class_id":0,"confidence":0.93,"bbox_xyxy":[12,12,98,98]}]}
```

Coordinates are pixel-space `[x1,y1,x2,y2]`, top-left origin, positive area. Ground truth must be independently annotated; predictions must be produced by the exact model build being evaluated. The same image must not occur twice. Use a held-out test split that was not used for training, fine-tuning, threshold selection or model selection. Record annotation protocol, annotator agreement, class mapping, camera conditions, image sampling method and dataset rights separately.

## Run

```sh
python -m camera.evaluate_detections --annotations private-test.jsonl --output private-report.json --iou 0.5 --confidence 0.25
```

The JSON report includes a SHA-256 of the annotation file. Store the report, annotation provenance, model SHA-256 and model manifest together in a controlled private evaluation record. Do not commit raw images, private location data or sensitive annotations to a public repository.

## Limits

- AP is computed per class using greedy confidence-ranked matching and 101-point interpolation at one IoU threshold; it is not COCO mAP across multiple IoU thresholds.
- The evaluator does not inspect images, verify annotations, detect train/test leakage or establish dataset/model licensing.
- Metrics are only as representative as the held-out data and annotation process.
- No model is bundled; no model performance claim or operational release follows from the existence of this tool.
- A field trial and expert confirmation remain mandatory.
