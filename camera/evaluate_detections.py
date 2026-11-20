"""Evaluate object-detection predictions against independently annotated held-out data.

Input is JSONL metadata only; image files are never read or uploaded. This tool
does not certify a model or approve operational use.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

MAX_BYTES = 128 * 1024 * 1024
MAX_IMAGES = 100_000
MAX_BOXES_PER_IMAGE = 2_000


class EvaluationError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationError("duplicate JSON key")
        result[key] = value
    return result


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise EvaluationError(f"{name} must be a finite number")
    return float(value)


def _box(value, name):
    if not isinstance(value, list) or len(value) != 4:
        raise EvaluationError(f"{name} must be [x1,y1,x2,y2]")
    x1, y1, x2, y2 = (_finite(v, name) for v in value)
    if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
        raise EvaluationError(f"{name} must have non-negative, positive-area xyxy coordinates")
    return (x1, y1, x2, y2)


def _iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def load_records(path: str | Path):
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file() or source.stat().st_size > MAX_BYTES:
        raise EvaluationError("annotation file must be a regular file under 128 MiB")
    digest = hashlib.sha256()
    records = []
    seen = set()
    with source.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise EvaluationError("annotation file exceeds the 128 MiB limit")
    digest.update(raw)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvaluationError("annotation file must be UTF-8 JSONL") from exc
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line, object_pairs_hook=_unique_object, parse_constant=lambda _: (_ for _ in ()).throw(EvaluationError("non-finite JSON number")))
        except (json.JSONDecodeError, EvaluationError) as exc:
            raise EvaluationError(f"line {line_no}: invalid JSON record") from exc
        if not isinstance(row, dict):
            raise EvaluationError(f"line {line_no}: record must be an object")
        image_id = row.get("image_id")
        image_hash = row.get("image_sha256")
        if not isinstance(image_id, str) or not image_id.strip() or len(image_id) > 256:
            raise EvaluationError(f"line {line_no}: image_id is required")
        if image_id in seen:
            raise EvaluationError(f"line {line_no}: duplicate image_id")
        if not isinstance(image_hash, str) or len(image_hash) != 64 or any(c not in "0123456789abcdef" for c in image_hash):
            raise EvaluationError(f"line {line_no}: image_sha256 must be lowercase SHA-256")
        seen.add(image_id)
        gt = row.get("ground_truth")
        pred = row.get("predictions")
        if not isinstance(gt, list) or not isinstance(pred, list):
            raise EvaluationError(f"line {line_no}: ground_truth and predictions must be arrays")
        if len(gt) + len(pred) > MAX_BOXES_PER_IMAGE:
            raise EvaluationError(f"line {line_no}: too many boxes")
        parsed_gt, parsed_pred = [], []
        for item in gt:
            if not isinstance(item, dict) or type(item.get("class_id")) is not int or item["class_id"] < 0:
                raise EvaluationError(f"line {line_no}: invalid ground-truth class_id")
            parsed_gt.append({"class_id": item["class_id"], "box": _box(item.get("bbox_xyxy"), "ground_truth bbox")})
        for item in pred:
            if not isinstance(item, dict) or type(item.get("class_id")) is not int or item["class_id"] < 0:
                raise EvaluationError(f"line {line_no}: invalid prediction class_id")
            confidence = _finite(item.get("confidence"), "confidence")
            if not 0 <= confidence <= 1:
                raise EvaluationError(f"line {line_no}: confidence must be in 0..1")
            parsed_pred.append({"class_id": item["class_id"], "confidence": confidence, "box": _box(item.get("bbox_xyxy"), "prediction bbox")})
        records.append({"image_id": image_id, "ground_truth": parsed_gt, "predictions": parsed_pred})
        if len(records) > MAX_IMAGES:
            raise EvaluationError("annotation file exceeds the 100,000-image limit")
    if not records:
        raise EvaluationError("annotation file contains no image records")
    return records, digest.hexdigest()


def _average_precision(tp_flags, fp_flags, total_gt):
    if total_gt == 0:
        return None
    tp, fp = 0, 0
    points = []
    for is_tp, is_fp in zip(tp_flags, fp_flags):
        tp += int(is_tp)
        fp += int(is_fp)
        points.append((tp / total_gt, tp / (tp + fp)))
    area = 0.0
    for step in range(101):
        recall = step / 100
        precision = max((p for r, p in points if r >= recall), default=0.0)
        area += precision / 101
    return round(area, 6)


def evaluate(records, *, iou_threshold=0.5, confidence_threshold=0.25):
    if not 0.1 <= iou_threshold <= 1.0:
        raise EvaluationError("IoU threshold must be in 0.1..1.0")
    if not 0 <= confidence_threshold <= 1:
        raise EvaluationError("confidence threshold must be in 0..1")
    class_ids = sorted({
        item["class_id"]
        for row in records
        for item in row["ground_truth"] + row["predictions"]
    })
    results = {}
    for class_id in class_ids:
        gt_by_image = {
            row["image_id"]: [item["box"] for item in row["ground_truth"] if item["class_id"] == class_id]
            for row in records
        }
        total_gt = sum(map(len, gt_by_image.values()))
        ranked = sorted(
            [(item["confidence"], row["image_id"], item["box"])
             for row in records for item in row["predictions"]
             if item["class_id"] == class_id],
            key=lambda item: item[0], reverse=True
        )
        matched = defaultdict(set)
        tp_flags, fp_flags = [], []
        for confidence, image_id, box in ranked:
            candidates = gt_by_image.get(image_id, [])
            best_index, best_iou = None, 0.0
            for index, target in enumerate(candidates):
                overlap = _iou(box, target)
                if index not in matched[image_id] and overlap > best_iou:
                    best_index, best_iou = index, overlap
            is_tp = best_index is not None and best_iou >= iou_threshold
            if is_tp:
                matched[image_id].add(best_index)
            tp_flags.append(is_tp)
            fp_flags.append(not is_tp)
        tp = fp = 0
        for (confidence, _, _), is_tp, is_fp in zip(ranked, tp_flags, fp_flags):
            if confidence < confidence_threshold:
                continue
            tp += int(is_tp)
            fp += int(is_fp)
        fn = total_gt - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / total_gt if total_gt else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        results[str(class_id)] = {
            "ground_truth": total_gt,
            "predictions_at_threshold": tp + fp,
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
            "ap_at_iou": _average_precision(tp_flags, fp_flags, total_gt),
        }
    return {
        "metric_version": 1,
        "iou_threshold": iou_threshold,
        "confidence_threshold": confidence_threshold,
        "images": len(records),
        "classes": results,
        "warning": "Offline held-out-set metrics only; not a field validation, legal review, or deployment approval.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate BeeKeeper ONNX detections against held-out annotations")
    parser.add_argument("--annotations", required=True, help="UTF-8 JSONL file; keep source images and exact locations private")
    parser.add_argument("--output", required=True, help="JSON report output path")
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--confidence", type=float, default=0.25)
    args = parser.parse_args(argv)
    try:
        records, digest = load_records(args.annotations)
        report = evaluate(records, iou_threshold=args.iou, confidence_threshold=args.confidence)
        report["annotation_sha256"] = digest
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, EvaluationError) as exc:
        print(f"evaluation failed: {exc}", file=sys.stderr)
        return 2
    print(f"evaluated {report['images']} images; report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
