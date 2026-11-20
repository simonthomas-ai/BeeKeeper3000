"""CPU ONNX detector for a documented, fixed three-output model contract.

The network must emit normalized xyxy boxes *after* its own NMS, scores and
integer class IDs. No image is retained or sent to another service.
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
        expected_outputs = {manifest.boxes_output, manifest.scores_output, manifest.class_ids_output}
        if manifest.input_name not in inputs or not expected_outputs.issubset(outputs):
            raise DetectorError("ONNX graph tensor names do not match the model manifest")
        self.manifest = manifest

    @classmethod
    def from_manifest(cls, path: str | Path, *, intra_op_threads: int = 2):
        return cls(load_manifest(path, verify_model=True), intra_op_threads=intra_op_threads)

    def detect(self, frame) -> list[Detection]:
        np, cv2, manifest = self.np, self.cv2, self.manifest
        if frame is None or not hasattr(frame, "shape") or len(frame.shape) != 3 or frame.shape[2] != 3:
            raise ValueError("frame must be a three-channel BGR image")
        resized = cv2.resize(frame, (manifest.width, manifest.height), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = np.asarray(rgb, dtype=np.float32) / np.float32(255.0)
        tensor = np.transpose(tensor, (2, 0, 1))[None, ...]
        try:
            raw = self.session.run(
                [manifest.boxes_output, manifest.scores_output, manifest.class_ids_output],
                {manifest.input_name: tensor},
            )
        except Exception as exc:
            raise DetectorError("ONNX inference failed") from exc
        boxes, scores, class_ids = (np.asarray(item).squeeze() for item in raw)
        if boxes.size == 0:
            return []
        if boxes.ndim == 1:
            boxes = boxes.reshape(1, -1)
        if boxes.ndim != 2 or boxes.shape[1] != 4:
            raise DetectorError("boxes output must have shape [N,4] or [1,N,4]")
        scores = scores.reshape(-1)
        class_ids = class_ids.reshape(-1)
        if len(boxes) != len(scores) or len(boxes) != len(class_ids):
            raise DetectorError("ONNX output arrays have inconsistent lengths")
        detections = []
        for box, score, class_id in zip(boxes, scores, class_ids):
            if not np.isfinite(box).all() or not np.isfinite(score) or not np.isfinite(class_id):
                continue
            cid_number = float(class_id)
            if not cid_number.is_integer():
                continue
            mapped = manifest.classes.get(int(cid_number))
            confidence = float(score)
            if mapped is None or not 0.0 <= confidence <= 1.0 or confidence < mapped.threshold:
                continue
            x1, y1, x2, y2 = (float(value) for value in box)
            if not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
                continue
            detections.append(Detection(mapped.label, confidence, mapped.prey_detected))
        return detections
