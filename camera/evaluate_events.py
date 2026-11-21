"""Evaluate event-level detections and false alarms per monitored camera-hour.

Input is reviewed event metadata only. No images or exact locations are read.
Matching is performed within each camera session using temporal interval IoU.
This reports offline held-out-set metrics; it does not certify a model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_BYTES = 128 * 1024 * 1024
MAX_SESSIONS = 100_000
MAX_EVENTS_PER_SESSION = 10_000
MAX_SESSION_SECONDS = 31 * 24 * 60 * 60
SHA256_HEX = frozenset("0123456789abcdef")


class EventEvaluationError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EventEvaluationError("duplicate JSON key")
        result[key] = value
    return result


def _finite(value, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EventEvaluationError(f"{field} must be a finite number")
    try:
        numeric = float(value)
    except (OverflowError, ValueError) as exc:
        raise EventEvaluationError(f"{field} must be a finite number") from exc
    if not math.isfinite(numeric):
        raise EventEvaluationError(f"{field} must be a finite number")
    return numeric


def _required_text(value, field: str, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise EventEvaluationError(f"{field} is required and must be at most {max_length} characters")
    if any(ord(char) < 32 for char in value):
        raise EventEvaluationError(f"{field} contains control characters")
    return value.strip()


def _sha256(value, field: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in SHA256_HEX for char in value)):
        raise EventEvaluationError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _utc_timestamp(value) -> datetime:
    text = _required_text(value, "start_time_utc", 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EventEvaluationError("start_time_utc must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EventEvaluationError("start_time_utc must include a timezone")
    return parsed.astimezone(timezone.utc)


def _parse_events(value, field: str, duration: float, *, predictions: bool):
    if not isinstance(value, list):
        raise EventEvaluationError(f"{field} must be an array")
    if len(value) > MAX_EVENTS_PER_SESSION:
        raise EventEvaluationError(f"{field} exceeds the per-session event limit")

    parsed = []
    seen_ids = set()
    for index, item in enumerate(value):
        prefix = f"{field}[{index}]"
        if not isinstance(item, dict):
            raise EventEvaluationError(f"{prefix} must be an object")
        event_id = _required_text(item.get("event_id"), f"{prefix}.event_id")
        if event_id in seen_ids:
            raise EventEvaluationError(f"{field} contains a duplicate event_id")
        seen_ids.add(event_id)

        class_id = item.get("class_id")
        if type(class_id) is not int or class_id < 0:
            raise EventEvaluationError(f"{prefix}.class_id must be a non-negative integer")
        start = _finite(item.get("start_seconds"), f"{prefix}.start_seconds")
        end = _finite(item.get("end_seconds"), f"{prefix}.end_seconds")
        if start < 0 or end <= start or end > duration:
            raise EventEvaluationError(f"{prefix} must be a positive interval inside its camera session")

        event = {
            "event_id": event_id,
            "class_id": class_id,
            "start_seconds": start,
            "end_seconds": end,
        }
        if predictions:
            confidence = _finite(item.get("confidence"), f"{prefix}.confidence")
            if not 0.0 <= confidence <= 1.0:
                raise EventEvaluationError(f"{prefix}.confidence must be in 0..1")
            event["confidence"] = confidence
        parsed.append(event)
    return parsed


def load_sessions(path: str | Path):
    """Load, validate and hash reviewed session-level event JSONL."""
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file() or source.stat().st_size > MAX_BYTES:
        raise EventEvaluationError("event annotation file must be a regular file under 128 MiB")
    with source.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise EventEvaluationError("event annotation file exceeds the 128 MiB limit")
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EventEvaluationError("event annotation file must be UTF-8 JSONL") from exc

    sessions = []
    session_ids = set()
    model_digest = None
    camera_intervals = defaultdict(list)

    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(
                line,
                object_pairs_hook=_unique_object,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    EventEvaluationError("non-finite JSON number")
                ),
            )
        except (json.JSONDecodeError, EventEvaluationError) as exc:
            raise EventEvaluationError(f"line {line_number}: invalid JSON session") from exc
        if not isinstance(row, dict):
            raise EventEvaluationError(f"line {line_number}: session must be an object")

        session_id = _required_text(row.get("session_id"), "session_id")
        camera_id = _required_text(row.get("camera_id"), "camera_id")
        if session_id in session_ids:
            raise EventEvaluationError(f"line {line_number}: duplicate session_id")
        session_ids.add(session_id)

        current_model_digest = _sha256(row.get("model_sha256"), "model_sha256")
        if model_digest is None:
            model_digest = current_model_digest
        elif current_model_digest != model_digest:
            raise EventEvaluationError("one evaluation file must reference exactly one model SHA-256")

        if row.get("ground_truth_review_status") != "verified":
            raise EventEvaluationError(f"line {line_number}: ground-truth events must be human-reviewed")
        reviewer_id = _required_text(row.get("reviewer_id"), "reviewer_id")

        start_time = _utc_timestamp(row.get("start_time_utc"))
        duration = _finite(row.get("duration_seconds"), "duration_seconds")
        if not 0.0 < duration <= MAX_SESSION_SECONDS:
            raise EventEvaluationError("duration_seconds must be greater than zero and at most 31 days")
        end_time = start_time + timedelta(seconds=duration)

        ground_truth = _parse_events(
            row.get("ground_truth_events"), "ground_truth_events", duration, predictions=False
        )
        predictions = _parse_events(
            row.get("predicted_events"), "predicted_events", duration, predictions=True
        )
        if len(ground_truth) + len(predictions) > MAX_EVENTS_PER_SESSION:
            raise EventEvaluationError("combined session events exceed the per-session event limit")

        camera_intervals[camera_id].append((start_time, end_time, session_id))
        sessions.append({
            "session_id": session_id,
            "camera_id": camera_id,
            "model_sha256": current_model_digest,
            "start_time_utc": start_time,
            "duration_seconds": duration,
            "reviewer_id": reviewer_id,
            "ground_truth_events": ground_truth,
            "predicted_events": predictions,
        })
        if len(sessions) > MAX_SESSIONS:
            raise EventEvaluationError("event annotation file exceeds the 100,000-session limit")

    if not sessions:
        raise EventEvaluationError("event annotation file contains no sessions")

    # Overlapping sessions from one camera would double-count monitored hours.
    for camera_id, intervals in camera_intervals.items():
        ordered = sorted(intervals, key=lambda item: item[0])
        for previous, current in zip(ordered, ordered[1:]):
            if current[0] < previous[1]:
                raise EventEvaluationError(
                    f"overlapping monitoring sessions for camera_id {camera_id}"
                )

    return sessions, digest, model_digest


def _temporal_iou(a, b) -> float:
    intersection = max(
        0.0,
        min(a["end_seconds"], b["end_seconds"])
        - max(a["start_seconds"], b["start_seconds"]),
    )
    duration_a = a["end_seconds"] - a["start_seconds"]
    duration_b = b["end_seconds"] - b["start_seconds"]
    union = duration_a + duration_b - intersection
    return intersection / union if union > 0 else 0.0


def _metrics(tp: int, fp: int, fn: int, camera_hours: float) -> dict:
    prediction_count = tp + fp
    ground_truth_count = tp + fn
    precision = tp / prediction_count if prediction_count else None
    recall = tp / ground_truth_count if ground_truth_count else None
    if precision is not None and recall is not None:
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    else:
        f1 = None
    return {
        "ground_truth_events": ground_truth_count,
        "predicted_events_at_threshold": prediction_count,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 6) if precision is not None else None,
        "recall": round(recall, 6) if recall is not None else None,
        "f1": round(f1, 6) if f1 is not None else None,
        "false_alarms_per_camera_hour": round(fp / camera_hours, 6) if camera_hours else None,
    }


def evaluate_sessions(
    sessions,
    *,
    temporal_iou_threshold: float = 0.5,
    confidence_threshold: float = 0.5,
) -> dict:
    """Match events within each session and report event recall and false alarms/hour."""
    temporal_iou_threshold = _finite(temporal_iou_threshold, "temporal IoU threshold")
    confidence_threshold = _finite(confidence_threshold, "confidence threshold")
    if not 0.1 <= temporal_iou_threshold <= 1.0:
        raise EventEvaluationError("temporal IoU threshold must be in 0.1..1.0")
    if not 0.0 <= confidence_threshold <= 1.0:
        raise EventEvaluationError("confidence threshold must be in 0..1")
    if not sessions:
        raise EventEvaluationError("at least one validated camera session is required")

    camera_hours = sum(session["duration_seconds"] for session in sessions) / 3600.0
    class_ids = sorted({
        event["class_id"]
        for session in sessions
        for event in session["ground_truth_events"] + session["predicted_events"]
    })
    totals = {class_id: {"tp": 0, "fp": 0, "fn": 0} for class_id in class_ids}

    for session in sessions:
        for class_id in class_ids:
            targets = [
                event for event in session["ground_truth_events"]
                if event["class_id"] == class_id
            ]
            candidates = [
                event for event in session["predicted_events"]
                if event["class_id"] == class_id
                and event["confidence"] >= confidence_threshold
            ]
            candidates.sort(key=lambda event: event["confidence"], reverse=True)
            matched = set()
            tp = fp = 0
            for prediction in candidates:
                best_index = None
                best_overlap = 0.0
                for index, target in enumerate(targets):
                    if index in matched:
                        continue
                    overlap = _temporal_iou(prediction, target)
                    if overlap > best_overlap:
                        best_index, best_overlap = index, overlap
                if best_index is not None and best_overlap >= temporal_iou_threshold:
                    matched.add(best_index)
                    tp += 1
                else:
                    fp += 1
            totals[class_id]["tp"] += tp
            totals[class_id]["fp"] += fp
            totals[class_id]["fn"] += len(targets) - tp

    class_results = {
        str(class_id): _metrics(values["tp"], values["fp"], values["fn"], camera_hours)
        for class_id, values in totals.items()
    }
    total_tp = sum(item["tp"] for item in totals.values())
    total_fp = sum(item["fp"] for item in totals.values())
    total_fn = sum(item["fn"] for item in totals.values())

    return {
        "metric_version": 1,
        "matching": "same-camera-session, same-class, greedy confidence order, temporal IoU",
        "temporal_iou_threshold": temporal_iou_threshold,
        "confidence_threshold": confidence_threshold,
        "sessions": len(sessions),
        "cameras": len({session["camera_id"] for session in sessions}),
        "monitoring_camera_hours": round(camera_hours, 6),
        "model_sha256": sessions[0]["model_sha256"],
        "overall": _metrics(total_tp, total_fp, total_fn, camera_hours),
        "classes": class_results,
        "warning": (
            "Reviewed offline event-level metrics only; not an independent field "
            "certification, species-accuracy guarantee or deployment approval."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Evaluate reviewed BeeKeeper events and false alarms per camera-hour"
    )
    parser.add_argument("--sessions", required=True, help="UTF-8 JSONL with reviewed GT and model events")
    parser.add_argument("--output", required=True, help="JSON report path; keep private session metadata protected")
    parser.add_argument("--temporal-iou", type=float, default=0.5)
    parser.add_argument("--confidence", type=float, default=0.5)
    args = parser.parse_args(argv)
    try:
        sessions, digest, model_digest = load_sessions(args.sessions)
        report = evaluate_sessions(
            sessions,
            temporal_iou_threshold=args.temporal_iou,
            confidence_threshold=args.confidence,
        )
        report["annotation_sha256"] = digest
        report["model_sha256"] = model_digest
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    except (OSError, EventEvaluationError) as exc:
        print(f"event evaluation failed: {exc}", file=sys.stderr)
        return 2
    print(
        f"evaluated {report['sessions']} camera sessions "
        f"({report['monitoring_camera_hours']} camera-hours); report: {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
