"""Explicit local-only image/video adapter with bounded decoding.

The adapter reads one operator-selected file beneath an approved root. Images
are read once into a bounded byte snapshot and dimension-checked before decode.
Videos use a local file path with bounded FFmpeg open/read timeouts and strict
frame/duration ceilings. Only detection metadata is emitted; pixels never leave
the adapter or enter the event contract.
"""
from __future__ import annotations

import os
import stat
import struct
import time
import math
from collections import deque
from pathlib import Path
from typing import Any, Mapping

from camera.contracts import Detection, make_source_event
from adapters.lifecycle import AdapterConfigurationError, AdapterTransientError


_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".mkv", ".avi", ".webm"}
_SOF_MARKERS = {
    0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
    0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
}


def image_dimensions(payload: bytes) -> tuple[int, int]:
    """Read JPEG/PNG/WebP dimensions without decoding the image."""
    if not isinstance(payload, bytes) or len(payload) < 16:
        raise ValueError("image_header_invalid")

    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(payload) < 24 or payload[12:16] != b"IHDR":
            raise ValueError("png_header_invalid")
        width, height = struct.unpack(">II", payload[16:24])
        return width, height

    if payload.startswith(b"\xff\xd8"):
        index = 2
        while index + 4 <= len(payload):
            if payload[index] != 0xFF:
                index += 1
                continue
            while index < len(payload) and payload[index] == 0xFF:
                index += 1
            if index >= len(payload):
                break
            marker = payload[index]
            index += 1
            if marker in {0xD8, 0xD9, 0x01} or 0xD0 <= marker <= 0xD7:
                continue
            if index + 2 > len(payload):
                break
            segment_length = int.from_bytes(payload[index:index + 2], "big")
            if segment_length < 2 or index + segment_length > len(payload):
                raise ValueError("jpeg_segment_invalid")
            if marker in _SOF_MARKERS:
                if segment_length < 8:
                    raise ValueError("jpeg_sof_invalid")
                height = int.from_bytes(payload[index + 3:index + 5], "big")
                width = int.from_bytes(payload[index + 5:index + 7], "big")
                return width, height
            if marker == 0xDA:
                break
            index += segment_length
        raise ValueError("jpeg_dimensions_missing")

    if payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        index = 12
        while index + 8 <= len(payload):
            kind = payload[index:index + 4]
            size = int.from_bytes(payload[index + 4:index + 8], "little")
            data = index + 8
            if data + size > len(payload):
                raise ValueError("webp_chunk_invalid")
            if kind == b"VP8X" and size >= 10:
                width = 1 + int.from_bytes(payload[data + 4:data + 7], "little")
                height = 1 + int.from_bytes(payload[data + 7:data + 10], "little")
                return width, height
            if kind == b"VP8 " and size >= 10:
                if payload[data + 3:data + 6] != b"\x9d\x01\x2a":
                    raise ValueError("webp_vp8_header_invalid")
                width = int.from_bytes(payload[data + 6:data + 8], "little") & 0x3FFF
                height = int.from_bytes(payload[data + 8:data + 10], "little") & 0x3FFF
                return width, height
            if kind == b"VP8L" and size >= 5 and payload[data] == 0x2F:
                b1, b2, b3, b4 = payload[data + 1:data + 5]
                width = 1 + (b1 | ((b2 & 0x3F) << 8))
                height = 1 + ((b2 >> 6) | (b3 << 2) | ((b4 & 0x0F) << 10))
                return width, height
            index = data + size + (size & 1)
        raise ValueError("webp_dimensions_missing")

    raise ValueError("unsupported_image_format")


class LocalMediaAdapter:
    """Adapter for one local image or video file; no network source is accepted."""

    def __init__(
        self,
        *,
        source_path: str | Path,
        allowed_root: str | Path,
        detector: Any,
        station_id: str,
        permission_granted: bool,
        max_image_bytes: int = 32 * 1024 * 1024,
        max_video_bytes: int = 256 * 1024 * 1024,
        max_image_pixels: int = 50_000_000,
        max_image_dimension: int = 12_000,
        max_video_frames: int = 10_000,
        max_video_duration_seconds: int = 3_600,
        max_frames_per_read: int = 24,
        cooldown_seconds: float = 30.0,
    ):
        if type(permission_granted) is not bool:
            raise ValueError("permission_granted must be an explicit boolean")
        if not permission_granted:
            raise AdapterConfigurationError("local_media_permission_not_granted")
        if not isinstance(station_id, str) or not 1 <= len(station_id.strip()) <= 80:
            raise ValueError("station_id must be a non-empty identifier up to 80 characters")
        if type(max_image_bytes) is not int or not 1_024 <= max_image_bytes <= 128 * 1024 * 1024:
            raise ValueError("max_image_bytes must be between 1 KiB and 128 MiB")
        if type(max_video_bytes) is not int or not 1_024 <= max_video_bytes <= 1024 * 1024 * 1024:
            raise ValueError("max_video_bytes must be between 1 KiB and 1 GiB")
        if type(max_image_pixels) is not int or not 1_000 <= max_image_pixels <= 100_000_000:
            raise ValueError("max_image_pixels must be between 1,000 and 100 million")
        if type(max_image_dimension) is not int or not 64 <= max_image_dimension <= 32_000:
            raise ValueError("max_image_dimension is outside the supported range")
        if type(max_video_frames) is not int or not 1 <= max_video_frames <= 100_000:
            raise ValueError("max_video_frames must be between 1 and 100,000")
        if type(max_video_duration_seconds) is not int or not 1 <= max_video_duration_seconds <= 86_400:
            raise ValueError("max_video_duration_seconds must be between 1 second and 24 hours")
        if type(max_frames_per_read) is not int or not 1 <= max_frames_per_read <= 120:
            raise ValueError("max_frames_per_read must be between 1 and 120")
        if not 0 <= float(cooldown_seconds) <= 86_400:
            raise ValueError("cooldown_seconds must be between 0 and 24 hours")

        root_input = Path(allowed_root).expanduser().absolute()
        try:
            root_parts = list(reversed([root_input] + list(root_input.parents)))
            current_root = Path(root_input.anchor)
            for part in root_parts[1:]:
                current_root = current_root / part.name
                if current_root.is_symlink():
                    raise AdapterConfigurationError("allowed_media_root_symlink_not_allowed")
            if not root_input.exists() or not root_input.is_dir():
                raise AdapterConfigurationError("allowed_media_root_invalid")
            self.allowed_root = root_input.resolve(strict=True)
        except OSError:
            raise AdapterConfigurationError("allowed_media_root_invalid") from None
        source = Path(source_path).expanduser()
        self.source_path = source if source.is_absolute() else self.allowed_root / source
        self.detector = detector
        self.station_id = station_id.strip()
        self.max_image_bytes = max_image_bytes
        self.max_video_bytes = max_video_bytes
        self.max_image_pixels = max_image_pixels
        self.max_image_dimension = max_image_dimension
        self.max_video_frames = max_video_frames
        self.max_video_duration_seconds = max_video_duration_seconds
        self.max_frames_per_read = max_frames_per_read
        self.cooldown_seconds = float(cooldown_seconds)

        self._path: Path | None = None
        self._extension = ""
        self._image_snapshot: bytes | None = None
        self._capture = None
        self._cv2 = None
        self._np = None
        self._pending: deque[dict[str, Any]] = deque()
        self._image_processed = False
        self._eof = False
        self._frames_seen = 0
        self._started = False
        self._last_event_by_species: dict[str, float] = {}
        self._last_read_monotonic = time.monotonic()

    def _resolve_local_path(self) -> Path:
        candidate = self.source_path
        try:
            root = self.allowed_root.resolve(strict=True)
            # Reject symlinks in every component below the configured root.
            relative = candidate.relative_to(root)
            current = root
            for part in relative.parts:
                current = current / part
                if current.is_symlink():
                    raise AdapterConfigurationError("local_media_symlink_not_allowed")
            resolved = current.resolve(strict=True)
            resolved.relative_to(root)
            if not resolved.is_file() or not stat.S_ISREG(resolved.stat().st_mode):
                raise AdapterConfigurationError("local_media_not_regular_file")
            return resolved
        except AdapterConfigurationError:
            raise
        except (OSError, ValueError):
            raise AdapterConfigurationError("local_media_path_outside_allowed_root") from None

    @staticmethod
    def _read_bounded_file(path: Path, maximum: int) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError:
            raise AdapterConfigurationError("local_media_open_failed") from None
        try:
            with os.fdopen(descriptor, "rb") as stream:
                metadata = os.fstat(stream.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
                    raise AdapterConfigurationError("local_media_size_or_type_rejected")
                payload = stream.read(maximum + 1)
        except OSError:
            raise AdapterConfigurationError("local_media_read_failed") from None
        if len(payload) > maximum:
            raise AdapterConfigurationError("local_media_size_limit_exceeded")
        return payload

    async def discover(self) -> bool:
        self._path = self._resolve_local_path()
        self._extension = self._path.suffix.lower()
        if self._extension in _IMAGE_EXTENSIONS:
            payload = self._read_bounded_file(self._path, self.max_image_bytes)
            width, height = image_dimensions(payload)
            self._validate_image_dimensions(width, height)
            self._image_snapshot = payload
            return True
        if self._extension in _VIDEO_EXTENSIONS:
            size = self._path.stat().st_size
            if not 0 < size <= self.max_video_bytes:
                raise AdapterConfigurationError("local_video_size_limit_exceeded")
            return True
        raise AdapterConfigurationError("local_media_extension_not_allowed")

    def _validate_image_dimensions(self, width: int, height: int) -> None:
        if (
            type(width) is not int or type(height) is not int or
            width < 1 or height < 1 or
            width > self.max_image_dimension or height > self.max_image_dimension or
            width * height > self.max_image_pixels
        ):
            raise AdapterConfigurationError("local_image_dimension_limit_exceeded")

    async def capabilities(self) -> Mapping[str, bool]:
        return {
            "local_image": self._extension in _IMAGE_EXTENSIONS,
            "local_video": self._extension in _VIDEO_EXTENSIONS,
            "local_file_read": self._path is not None,
        }

    async def permissions(self) -> Mapping[str, bool]:
        # The operator explicitly supplied the allowed root and selected file.
        return {"local_file_read": True}

    async def start(self) -> None:
        if self._path is None:
            raise AdapterConfigurationError("local_media_not_discovered")
        try:
            import cv2
            import numpy as np
        except ImportError:
            raise AdapterConfigurationError("opencv_optional_dependency_missing") from None
        self._cv2, self._np = cv2, np

        if self._extension in _IMAGE_EXTENSIONS:
            encoded = np.frombuffer(self._image_snapshot or b"", dtype=np.uint8)
            frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
            if frame is None or not hasattr(frame, "shape") or len(frame.shape) != 3:
                raise AdapterConfigurationError("local_image_decode_failed")
            height, width = frame.shape[:2]
            self._validate_image_dimensions(int(width), int(height))
            self._queue_detections(frame)
            del frame
            self._image_processed = True
        else:
            open_timeout = getattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC", None)
            read_timeout = getattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC", None)
            ffmpeg = getattr(cv2, "CAP_FFMPEG", None)
            if open_timeout is None or read_timeout is None or ffmpeg is None:
                raise AdapterConfigurationError("opencv_bounded_video_backend_unavailable")
            try:
                    self._capture = cv2.VideoCapture(
                    str(self._path), ffmpeg,
                    [open_timeout, 5_000, read_timeout, 5_000],
                )
            except Exception:
                self._release_capture()
                raise AdapterTransientError("local_video_open_failed") from None
            if self._capture is None or not self._capture.isOpened():
                self._release_capture()
                raise AdapterTransientError("local_video_open_failed")
            width = int(self._capture.get(getattr(cv2, "CAP_PROP_FRAME_WIDTH", 3)))
            height = int(self._capture.get(getattr(cv2, "CAP_PROP_FRAME_HEIGHT", 4)))
            if width > 0 and height > 0:
                self._validate_image_dimensions(width, height)
            frame_count = float(self._capture.get(getattr(cv2, "CAP_PROP_FRAME_COUNT", 7)))
            fps = float(self._capture.get(getattr(cv2, "CAP_PROP_FPS", 5)))
            if not math.isfinite(frame_count) or not math.isfinite(fps):
                self._release_capture()
                raise AdapterConfigurationError("local_video_metadata_invalid")
            if frame_count > self.max_video_frames:
                self._release_capture()
                raise AdapterConfigurationError("local_video_frame_limit_exceeded")
            if fps > 0 and frame_count > 0 and frame_count / fps > self.max_video_duration_seconds:
                self._release_capture()
                raise AdapterConfigurationError("local_video_duration_limit_exceeded")
        self._started = True

    def _queue_detections(self, frame: Any) -> None:
        now = time.monotonic()
        try:
            detections = self.detector.detect(frame)
        except Exception:
            raise AdapterTransientError("local_media_inference_failed") from None
        if not isinstance(detections, list):
            raise AdapterConfigurationError("detector_contract_invalid")
        for detection in detections:
            if not isinstance(detection, Detection):
                raise AdapterConfigurationError("detector_contract_invalid")
            detection.validate()
            previous = self._last_event_by_species.get(detection.species)
            if previous is not None and now - previous < self.cooldown_seconds:
                continue
            self._last_event_by_species[detection.species] = now
            self._pending.append(make_source_event(station_id=self.station_id, detection=detection))

    async def read_event(self, timeout_seconds: float) -> Mapping[str, Any] | None:
        if not self._started:
            raise AdapterConfigurationError("local_media_not_started")
        if self._pending:
            return self._pending.popleft()
        if self._image_processed or self._eof or self._capture is None:
            return None

        started = time.monotonic()
        processed = 0
        while processed < self.max_frames_per_read:
            if time.monotonic() - started >= min(float(timeout_seconds), 5.0):
                return None
            if self._frames_seen >= self.max_video_frames:
                self._eof = True
                self._release_capture()
                return None
            ok, frame = self._capture.read()
            if not ok or frame is None:
                self._eof = True
                self._release_capture()
                return None
            self._frames_seen += 1
            processed += 1
            media_position_ms = float(self._capture.get(getattr(self._cv2, "CAP_PROP_POS_MSEC", 0)))
            if math.isfinite(media_position_ms) and media_position_ms > self.max_video_duration_seconds * 1000:
                self._eof = True
                self._release_capture()
                return None
            height, width = frame.shape[:2]
            self._validate_image_dimensions(int(width), int(height))
            self._queue_detections(frame)
            del frame
            if self._pending:
                return self._pending.popleft()
        return None

    @property
    def completed(self) -> bool:
        """True only when the selected one-shot image/video input is exhausted."""
        return self._started and not self._pending and (
            (self._extension in _IMAGE_EXTENSIONS and self._image_processed) or
            (self._extension in _VIDEO_EXTENSIONS and self._eof)
        )

    async def health(self) -> Mapping[str, Any]:
        return {
            "healthy": self._started and (
                self._extension in _IMAGE_EXTENSIONS or self._eof or
                (self._capture is not None and self._capture.isOpened())
            ),
        }

    def _release_capture(self) -> None:
        if self._capture is not None:
            try:
                self._capture.release()
            finally:
                self._capture = None

    async def stop(self) -> None:
        self._release_capture()
        self._pending.clear()
        self._image_snapshot = None
        self._started = False
        self._eof = True
