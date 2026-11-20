"""CPU ONNX detector for explicit, versioned post-NMS output contracts.

Supports either normalized xyxy + separate scores/class IDs, or Ultralytics
post-NMS matrix6 output: pixel xyxy, score, class_id. Raw frames stay in RAM.
"""
from __future__ import annotations

from pathlib import Path

from .contracts import Detection
from .model_manifest import ModelManifest, load_manifest


class DetectorError(RuntimeError):
    pass


class OnnxDetector:
    def __init__(self, manifest: ModelManifest, *, intra_op_threads: int = 2):
        if type(intra_op_threads) is not int or not 1 <= intra_op_threads <= 8:
            raise ValueError("intra_op_threads must be between 1 and 8")
        try:
            import cv2
            import numpy as np
            import onnxruntime as ort
        except ImportError as exc:
            raise DetectorError("Install optional dependencies from camera/requirements.txt") from exc
        self.cv2 = cv2
        self.np = np
        options = ort.SessionOptions()
        options.intra_op_num_threads = intra_op_threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        try:
            self.session = ort.InferenceSession(
                str(manifest.model_path), sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        except Exception as exc:
            raise DetectorError("ONNX model could not be loaded by the CPU runtime") from exc
        inputs = {item.name for item in self.session.get_inputs()}
        outputs = {item.name for item in self.session.get_outputs()}
        if manifest.input_name not in inputs:
            raise DetectorError("ONNX graph input name does not match the model manifest")
        expected_outputs = (
            {manifest.detections_output}
            if manifest.detections_output
            else {manifest.boxes_output, manifest.scores_output, manifest.class_ids_output}
        )
        if None in expected_outputs or not expected_outputs.issubset(outputs):
            raise DetectorError("ONNX graph output names do not match the model manifest")
        self.manifest = manifest

    @classmethod
    def from_manifest(cls, path: str | Path, *, intra_op_threads: int = 2):
        return cls(load_manifest(path, verify_model=True), intra_op_threads=intra_op_threads)

    def _preprocess(self, frame):
        np, cv2, manifest = self.np, self.cv2, self.manifest
        if frame is None or not hasattr(frame, "shape") or len(frame.shape) != 3 or frame.shape[2] != 3:
            raise ValueError("frame must be a three-channel BGR image")
        if frame.shape[0] < 1 or frame.shape[1] < 1:
            raise ValueError("frame dimensions must be positive")
        if manifest.resize_mode == "stretch":
            resized = cv2.resize(frame, (manifest.width, manifest.height), interpolation=cv2.INTER_LINEAR)
        else:
            original_h, original_w = frame.shape[:2]
            ratio = min(manifest.width / original_w, manifest.height / original_h)
            resized_w = max(1, min(manifest.width, int(round(original_w * ratio))))
            resized_h = max(1, min(manifest.height, int(round(original_h * ratio))))
            scaled = cv2.resize(frame, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)
            resized = np.full((manifest.height, manifest.width, 3), 114, dtype=np.uint8)
            x_offset = (manifest.width - resized_w) // 2
            y_offset = (manifest.height - resized_h) // 2
            resized[y_offset:y_offset + resized_h, x_offset:x_offset + resized_w] = scaled
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = np.asarray(rgb, dtype=np.float32) / np.float32(255.0)
        return np.transpose(tensor, (2, 0, 1))[None, ...]

    def detect(self, frame) -> list[Detection]:
        np, manifest = self.np, self.manifest
        tensor = self._preprocess(frame)
        try:
            if manifest.detections_output:
                raw = self.session.run(
                    [manifest.detections_output], {manifest.input_name: tensor}
                )[0]
            else:
                raw = self.session.run(
                    [manifest.boxes_output, manifest.scores_output, manifest.class_ids_output],
                    {manifest.input_name: tensor},
                )
        except Exception as exc:
            raise DetectorError("ONNX inference failed") from exc

        if manifest.detections_output:
            rows = np.asarray(raw).squeeze()
            if rows.size == 0:
                return []
            if rows.ndim == 1:
                rows = rows.reshape(1, -1)
            if rows.ndim != 2 or rows.shape[1] != 6:
                raise DetectorError("matrix6 detections output must have shape [N,6] or [1,N,6]")
            candidates = []
            for row in rows:
                if not np.isfinite(row).all():
                    continue
                x1, y1, x2, y2, score, class_id = (float(value) for value in row)
                candidates.append((x1, y1, x2, y2, score, class_id))
        else:
            boxes, scores, class_ids = (np.asarray(item).squeeze() for item in raw)
            if boxes.size == 0:
                return []
            if boxes.ndim == 1:
                boxes = boxes.reshape(1, -1)
            if boxes.ndim != 2 or boxes.shape[1] != 4:
                raise DetectorError("boxes output must have shape [N,4] or [1,N,4]")
            scores, class_ids = scores.reshape(-1), class_ids.reshape(-1)
            if len(boxes) != len(scores) or len(boxes) != len(class_ids):
                raise DetectorError("ONNX output arrays have inconsistent lengths")
            candidates = []
            for box, score, class_id in zip(boxes, scores, class_ids):
                if not np.isfinite(box).all() or not np.isfinite(score) or not np.isfinite(class_id):
                    continue
                x1, y1, x2, y2 = (float(value) for value in box)
                candidates.append((x1, y1, x2, y2, float(score), float(class_id)))

        detections = []
        for x1, y1, x2, y2, confidence, class_id in candidates:
            if not class_id.is_integer():
                continue
            mapped = manifest.classes.get(int(class_id))
            if mapped is None or not 0.0 <= confidence <= 1.0 or confidence < mapped.threshold:
                continue
            if manifest.box_format == "xyxy_pixels_nms_matrix6":
                valid_box = 0.0 <= x1 < x2 <= manifest.width and 0.0 <= y1 < y2 <= manifest.height
            else:
                valid_box = 0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0
            if not valid_box:
                continue
            detections.append(Detection(mapped.label, confidence, mapped.prey_detected))
        return detections
