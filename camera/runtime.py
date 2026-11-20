"""Reconnect-safe local capture, metadata outbox and loopback API delivery."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from .contracts import make_source_event
from .onnx_detector import OnnxDetector
from .outbox import SQLiteOutbox, OutboxFull
from .source_client import SourceApiClient, SourceClientError


class CameraRuntimeError(RuntimeError):
    pass


def _capture_source(value: str):
    try:
        import cv2
    except ImportError as exc:
        raise CameraRuntimeError("Install optional OpenCV from camera/requirements.txt") from exc
    if not isinstance(value, str) or not value.strip():
        raise ValueError("BEEKEEPER_CAMERA_SOURCE is required")
    value = value.strip()
    if not value:
        raise ValueError("BEEKEEPER_CAMERA_SOURCE is required")
    source = int(value) if value.isdecimal() else value
    if isinstance(source, str) and not source.startswith(("rtsp://", "rtsps://", "http://", "https://")):
        source = str(Path(source).expanduser())

    # Use native camera backends for local devices. Forcing FFmpeg on Linux can
    # break V4L2 webcams and Raspberry Pi camera bridges; keep FFmpeg for files
    # and network streams where it is the appropriate decoder.
    local_device = isinstance(source, int) or (
        isinstance(source, str) and source.startswith("/dev/video")
    )
    if local_device and sys.platform == "win32":
        backend = cv2.CAP_DSHOW
    elif local_device and sys.platform.startswith("linux"):
        backend = getattr(cv2, "CAP_V4L2", cv2.CAP_ANY)
    elif local_device and sys.platform == "darwin":
        backend = getattr(cv2, "CAP_AVFOUNDATION", cv2.CAP_ANY)
    elif local_device:
        backend = cv2.CAP_ANY
    else:
        backend = cv2.CAP_FFMPEG
    capture = cv2.VideoCapture(source, backend)
    if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return capture


class LocalCameraRuntime:
    def __init__(self, *, detector, outbox, client, station_id: str, source: str,
                 max_fps: float = 5.0, cooldown_seconds: float = 30.0,
                 reconnect_max_seconds: float = 30.0):
        if not 0.1 <= float(max_fps) <= 15.0:
            raise ValueError("max_fps must be between 0.1 and 15")
        if not 0 <= float(cooldown_seconds) <= 86400:
            raise ValueError("cooldown_seconds must be between 0 and 86400")
        if not 1 <= float(reconnect_max_seconds) <= 120:
            raise ValueError("reconnect_max_seconds must be between 1 and 120")
        self.detector, self.outbox, self.client = detector, outbox, client
        self.station_id, self.source = station_id, source
        self.frame_interval = 1.0 / float(max_fps)
        self.cooldown_seconds = float(cooldown_seconds)
        self.reconnect_max_seconds = float(reconnect_max_seconds)
        self.last_emitted: dict[tuple[str, bool], float] = {}

    def process_frame(self, frame, *, now_monotonic: float | None = None) -> int:
        now = time.monotonic() if now_monotonic is None else now_monotonic
        queued = 0
        for detection in self.detector.detect(frame):
            key = (detection.species, detection.prey_detected)
            previous = self.last_emitted.get(key)
            if previous is not None and now - previous < self.cooldown_seconds:
                continue
            event = make_source_event(station_id=self.station_id, detection=detection)
            self.outbox.enqueue(event)
            self.last_emitted[key] = now
            queued += 1
        return queued

    def drain_outbox(self, limit: int = 50) -> int:
        sent = 0
        for event in self.outbox.pending(limit):
            self.client.send_event(event)
            self.outbox.acknowledge(event["id"])
            sent += 1
        return sent

    def run_forever(self) -> None:
        backoff = 1.0
        print("BeeKeeper camera inference active; CPU-only, local frames, metadata-only forwarding.", flush=True)
        while True:
            capture = None
            try:
                capture = _capture_source(self.source)
                if not capture.isOpened():
                    raise CameraRuntimeError("camera source could not be opened")
                print("Camera source connected.", flush=True)
                backoff = 1.0
                consecutive_failures = 0
                while True:
                    started = time.monotonic()
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        consecutive_failures += 1
                        if consecutive_failures >= 3:
                            raise CameraRuntimeError("camera stream stopped returning frames")
                    else:
                        consecutive_failures = 0
                        self.process_frame(frame)
                    # Delivery errors leave every unacknowledged event in SQLite.
                    try:
                        self.drain_outbox(limit=25)
                    except SourceClientError:
                        pass
                    elapsed = time.monotonic() - started
                    if elapsed < self.frame_interval:
                        time.sleep(self.frame_interval - elapsed)
            except KeyboardInterrupt:
                print("Camera runtime stopped by operator.", flush=True)
                return
            except OutboxFull:
                raise CameraRuntimeError("local outbox reached capacity; stopped to avoid silent event loss")
            except CameraRuntimeError as exc:
                print(f"Camera runtime: {exc}", file=sys.stderr, flush=True)
            finally:
                if capture is not None:
                    capture.release()
            time.sleep(backoff)
            backoff = min(self.reconnect_max_seconds, backoff * 2.0)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Run local BeeKeeper camera inference")
    parser.add_argument("--manifest", default=os.environ.get("BEEKEEPER_MODEL_MANIFEST", ""))
    parser.add_argument("--source", default=os.environ.get("BEEKEEPER_CAMERA_SOURCE", ""))
    parser.add_argument("--station-id", default=os.environ.get("HORNET3000_STATION_ID", ""))
    parser.add_argument("--api-url", default=os.environ.get("HORNET3000_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--outbox", default=os.environ.get("BEEKEEPER_CAMERA_OUTBOX", str(Path.home() / ".local" / "share" / "beekeeper3000" / "camera-outbox.sqlite3")))
    parser.add_argument("--max-fps", type=float, default=float(os.environ.get("BEEKEEPER_CAMERA_MAX_FPS", "5")))
    parser.add_argument("--cooldown", type=float, default=float(os.environ.get("BEEKEEPER_CAMERA_COOLDOWN_SECONDS", "30")))
    parser.add_argument("--threads", type=int, default=int(os.environ.get("BEEKEEPER_ONNX_THREADS", "2")))
    args = parser.parse_args()
    api_key = os.environ.get("HORNET3000_API_KEY", "")
    if not args.manifest or not args.source or not args.station_id or not api_key:
        parser.error("set BEEKEEPER_MODEL_MANIFEST, BEEKEEPER_CAMERA_SOURCE, HORNET3000_STATION_ID and HORNET3000_API_KEY")
    try:
        detector = OnnxDetector.from_manifest(args.manifest, intra_op_threads=args.threads)
        outbox = SQLiteOutbox(args.outbox)
        client = SourceApiClient(args.api_url, api_key)
        runtime = LocalCameraRuntime(
            detector=detector, outbox=outbox, client=client, station_id=args.station_id,
            source=args.source, max_fps=args.max_fps, cooldown_seconds=args.cooldown,
        )
        runtime.run_forever()
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"BeeKeeper camera startup failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
