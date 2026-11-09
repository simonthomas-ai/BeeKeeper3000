"""YOLOv8/YOLOv10-ONNX-Detektor ohne OpenCV (nur onnxruntime + numpy + Pillow).

OpenCV wird bewusst nicht benutzt: cv2 stürzt auf manchen Rechnern/Python-Versionen mit
"illegal instruction" ab. Bildverarbeitung läuft über Pillow, Videoeingang über ffmpeg.
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass
class Detection:
    cls_id: int
    name: str
    conf: float
    box: tuple[float, float, float, float]  # x1, y1, x2, y2 im Originalbild

    @property
    def area(self) -> float:
        return max(0.0, self.box[2] - self.box[0]) * max(0.0, self.box[3] - self.box[1])

    def to_dict(self) -> dict:
        return {
            "cls": self.name,
            "conf": round(float(self.conf), 3),
            "box": [round(float(v), 1) for v in self.box],
        }


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def nms(boxes: np.ndarray, scores: np.ndarray, iou_thr: float) -> list[int]:
    """Klassische Non-Maximum-Suppression (boxes: N×4 xyxy)."""
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        iou_ = inter / (areas[i] + areas[rest] - inter + 1e-9)
        order = rest[iou_ <= iou_thr]
    return keep


class YoloOnnx:
    def __init__(self, model_path: str | Path, providers: list[str] | None = None,
                 iou_thr: float = 0.5, names_override: dict[int, str] | None = None):
        import onnxruntime as ort

        self.path = Path(model_path)
        if not self.path.is_file():
            raise FileNotFoundError(f"Modell nicht gefunden: {self.path}")
        so = ort.SessionOptions()
        so.intra_op_num_threads = max(1, (os.cpu_count() or 2))
        so.log_severity_level = 3
        avail = ort.get_available_providers()
        wanted = providers or ["CPUExecutionProvider"]
        wanted = [p for p in wanted if p in avail] or ["CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(self.path), sess_options=so, providers=wanted)
        self.provider = self.session.get_providers()[0]
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        shape = inp.shape
        self.in_h = int(shape[2]) if isinstance(shape[2], int) else 640
        self.in_w = int(shape[3]) if isinstance(shape[3], int) else 640
        self.iou_thr = iou_thr
        self.names = names_override or self._read_names()

    def _read_names(self) -> dict[int, str]:
        md = self.session.get_modelmeta().custom_metadata_map or {}
        raw = md.get("names")
        if raw:
            try:
                d = ast.literal_eval(raw)
                return {int(k): str(v) for k, v in d.items()}
            except Exception:
                pass
        return {}

    def name_of(self, cls_id: int) -> str:
        return self.names.get(cls_id, f"class{cls_id}")

    # -- Vorverarbeitung ------------------------------------------------------------
    def _letterbox(self, img: Image.Image) -> tuple[np.ndarray, float, float, float]:
        w, h = img.size
        r = min(self.in_w / w, self.in_h / h)
        nw, nh = max(1, int(round(w * r))), max(1, int(round(h * r)))
        resized = img.convert("RGB").resize((nw, nh), Image.BILINEAR)
        canvas = Image.new("RGB", (self.in_w, self.in_h), (114, 114, 114))
        px, py = (self.in_w - nw) // 2, (self.in_h - nh) // 2
        canvas.paste(resized, (px, py))
        arr = np.asarray(canvas, dtype=np.float32) / 255.0
        arr = np.transpose(arr, (2, 0, 1))[None]
        return np.ascontiguousarray(arr), r, float(px), float(py)

    # -- Inferenz -------------------------------------------------------------------
    def detect(self, img: Image.Image, conf_min: float = 0.25) -> list[Detection]:
        blob, r, px, py = self._letterbox(img)
        out = np.asarray(self.session.run(None, {self.input_name: blob})[0])
        W, H = img.size
        dets: list[Detection] = []

        if out.ndim == 3 and out.shape[2] == 6 and out.shape[1] > 6:
            # NMS-frei exportiert (YOLOv10): [1, N, 6] = x1 y1 x2 y2 conf cls
            rows = out[0]
            rows = rows[rows[:, 4] >= conf_min]
            for x1, y1, x2, y2, c, k in rows:
                b = self._unmap((x1, y1, x2, y2), r, px, py, W, H)
                dets.append(Detection(int(k), self.name_of(int(k)), float(c), b))
            return sorted(dets, key=lambda d: -d.conf)

        pred = out[0]
        if pred.shape[0] < pred.shape[1]:  # [4+nc, N] -> [N, 4+nc]
            pred = pred.T
        boxes_xywh = pred[:, :4]
        scores = pred[:, 4:]
        conf = scores.max(axis=1)
        cls = scores.argmax(axis=1)
        m = conf >= conf_min
        if not m.any():
            return []
        boxes_xywh, conf, cls = boxes_xywh[m], conf[m], cls[m]
        xyxy = np.empty_like(boxes_xywh)
        xyxy[:, 0] = boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2
        xyxy[:, 1] = boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2
        xyxy[:, 2] = boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2
        xyxy[:, 3] = boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2
        # klassenweise NMS über Offset-Trick
        offset = cls[:, None].astype(np.float32) * 4096.0
        keep = nms(xyxy + offset, conf, self.iou_thr)
        for i in keep:
            b = self._unmap(tuple(xyxy[i]), r, px, py, W, H)
            dets.append(Detection(int(cls[i]), self.name_of(int(cls[i])), float(conf[i]), b))
        return sorted(dets, key=lambda d: -d.conf)

    @staticmethod
    def _unmap(b, r, px, py, W, H):
        x1 = min(max((b[0] - px) / r, 0), W)
        y1 = min(max((b[1] - py) / r, 0), H)
        x2 = min(max((b[2] - px) / r, 0), W)
        y2 = min(max((b[3] - py) / r, 0), H)
        return (float(x1), float(y1), float(x2), float(y2))
