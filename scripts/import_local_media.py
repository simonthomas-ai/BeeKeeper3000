#!/usr/bin/env python3
"""Import one explicitly selected local image/video into the metadata-only outbox."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from adapters.lifecycle import (
    AdapterConfigurationError,
    AdapterLifecycleError,
    AdapterSpec,
    AdapterSupervisor,
)
from adapters.local_media import LocalMediaAdapter
from camera.onnx_detector import OnnxDetector
from camera.outbox import OutboxFull, SQLiteOutbox


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Locally infer one explicitly selected media file and queue only "
            "unverified detection metadata. No media upload or network client is used."
        )
    )
    parser.add_argument("--manifest", type=Path, required=True,
                        help="local model manifest with verified SHA-256 and reviewed licence")
    parser.add_argument("--source", type=Path, required=True,
                        help="one image or video file beneath --allowed-root")
    parser.add_argument("--allowed-root", type=Path, required=True,
                        help="approved local directory; symlinks and path traversal are rejected")
    parser.add_argument("--station-id", required=True)
    parser.add_argument("--outbox", type=Path, required=True,
                        help="private local metadata-only SQLite outbox")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--cooldown", type=float, default=30.0)
    parser.add_argument("--max-video-frames", type=int, default=10_000)
    parser.add_argument("--max-video-duration", type=int, default=3_600)
    parser.add_argument("--confirm-local-file-access", action="store_true",
                        help="explicitly attest that this local file may be read for inference")
    parser.add_argument("--shadow", action="store_true",
                        help="allow experimental inference but discard all detections without creating or changing the outbox")
    return parser


async def import_media(args: argparse.Namespace) -> int:
    if not args.confirm_local_file_access:
        raise AdapterConfigurationError("explicit_local_file_access_confirmation_required")

    shadow_mode = getattr(args, "shadow", False)
    if type(shadow_mode) is not bool:
        raise AdapterConfigurationError("shadow_mode_must_be_boolean")

    extension = args.source.suffix.lower()
    capability = "local_image" if extension in {".jpg", ".jpeg", ".png", ".webp"} else "local_video"
    detector = OnnxDetector.from_manifest(args.manifest, intra_op_threads=args.threads)
    manifest = getattr(detector, "manifest", None)
    inference_status = getattr(manifest, "inference_status", None)
    if manifest is None:
        raise AdapterConfigurationError("detector_must_have_reviewed_model_manifest")
    if inference_status != "experimental":
        raise AdapterConfigurationError(
            "production_inference_disabled_until_trusted_evaluator_attestation_verification"
        )
    if not shadow_mode:
        raise AdapterConfigurationError("experimental_model_requires_explicit_shadow_mode")

    outbox = None if shadow_mode else SQLiteOutbox(str(args.outbox))
    adapter = LocalMediaAdapter(
        source_path=args.source,
        allowed_root=args.allowed_root,
        detector=detector,
        station_id=args.station_id,
        permission_granted=True,
        max_video_frames=args.max_video_frames,
        max_video_duration_seconds=args.max_video_duration,
    )
    spec = AdapterSpec(
        adapter_id="media.local_file",
        version="1.0.0",
        source_type="local_media",
        required_capabilities=(capability, "local_file_read"),
        required_permissions=("local_file_read",),
    )
    supervisor = AdapterSupervisor(spec, adapter)
    queued = 0
    discarded = 0

    def store_metadata(event):
        nonlocal queued, discarded
        if shadow_mode:
            discarded += 1
            return
        try:
            inserted = outbox.enqueue_if_due(
                dict(event),
                cooldown_seconds=args.cooldown,
            )
        except OutboxFull:
            raise AdapterConfigurationError("local_metadata_outbox_full") from None
        if inserted:
            queued += 1

    await supervisor.run_once(store_metadata, asyncio.Event())
    if shadow_mode:
        print(
            "Local shadow import complete: "
            f"{discarded} unverified detection event(s) discarded; "
            "no outbox was created or modified. Raw media remained local."
        )
        return 0

    pending = outbox.count()
    print(
        "Local import complete: "
        f"{queued} unverified metadata event(s) queued; "
        f"{pending} event(s) currently pending in the outbox. "
        "Raw media remained local and was not stored or transmitted."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(import_media(args))
    except AdapterLifecycleError as exc:
        print(f"Local media import blocked: {exc.code}", file=sys.stderr)
        return 2
    except (ValueError, OSError, RuntimeError):
        # Avoid exposing local file paths, driver messages or model internals.
        print("Local media import failed: configuration or local processing error", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
