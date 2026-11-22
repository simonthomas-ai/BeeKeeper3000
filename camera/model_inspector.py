"""Inspect a local ONNX graph without approving or activating the model."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _shape_value(value):
    if value is None or type(value) is int or isinstance(value, str):
        return value
    return str(value)


def _node_info(node) -> dict:
    return {
        "name": node.name,
        "type": node.type,
        "shape": [_shape_value(dimension) for dimension in node.shape],
    }


def inspect_model(path: str | Path) -> dict:
    model_path = Path(path).expanduser().resolve(strict=True)
    if not model_path.is_file() or model_path.suffix.lower() != ".onnx":
        raise ValueError("model path must be a regular .onnx file")

    digest = hashlib.sha256()
    with model_path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)

    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise RuntimeError("Install ONNX Runtime from camera/requirements.txt") from exc

    if "CPUExecutionProvider" not in ort.get_available_providers():
        raise RuntimeError("ONNX Runtime does not provide CPUExecutionProvider")
    session = ort.InferenceSession(
        str(model_path),
        providers=["CPUExecutionProvider"],
    )
    providers = session.get_providers()
    if "CPUExecutionProvider" not in providers:
        raise RuntimeError("ONNX graph did not load with CPUExecutionProvider")

    return {
        "inspection_version": 1,
        "file_name": model_path.name,
        "size_bytes": model_path.stat().st_size,
        "sha256": digest.hexdigest(),
        "runtime": {
            "name": "onnxruntime",
            "version": ort.__version__,
            "providers": providers,
        },
        "inputs": [_node_info(node) for node in session.get_inputs()],
        "outputs": [_node_info(node) for node in session.get_outputs()],
        "activation_manifest_generated": False,
        "note": (
            "Graph loading only; no inference, class mapping, license review, "
            "or model approval was performed."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect a local ONNX graph; this does not approve or activate it."
    )
    parser.add_argument("model", help="Path to a local ONNX file")
    args = parser.parse_args(argv)
    try:
        report = inspect_model(args.model)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ONNX inspection failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
