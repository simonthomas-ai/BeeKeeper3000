#!/usr/bin/env python3
"""Train a deterministic experimental seven-class multi-label image classifier."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

try:
    from .multilabel_dataset import (
        CLASS_NAMES,
        DatasetValidationError,
        create_split_plan,
        prepared_dataset,
        validate_dataset,
    )
except ImportError:
    from multilabel_dataset import (
        CLASS_NAMES,
        DatasetValidationError,
        create_split_plan,
        prepared_dataset,
        validate_dataset,
    )

IMAGE_SIZE = 224
TASKS = ("seven_multilabel", "vespa_velutina_binary")


def task_config(task: str) -> dict:
    if task == "seven_multilabel":
        return {
            "name": task,
            "classes": list(CLASS_NAMES),
            "requires": "one positive example for every seven class in train split",
        }
    if task == "vespa_velutina_binary":
        return {
            "name": task,
            "classes": ["vespa_velutina"],
            "requires": "positive vespa_velutina and negative without vespa_velutina in train split",
        }
    raise ValueError("unsupported training task")


def task_targets(labels: list[str], task_classes: list[str]) -> list[float]:
    """Map shared export labels to a task-specific zero/one target."""
    if any(not isinstance(label, str) for label in labels):
        raise ValueError("labels must be strings")
    return [1.0 if label in labels else 0.0 for label in task_classes]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train from reviewed local annotations; never downloads data or checkpoints."
    )
    parser.add_argument("--dataset", required=True, help="Local directory or ZIP with images/ and annotations.jsonl")
    parser.add_argument("--output-dir", required=True, help="New local model output directory")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("cpu",), default="cpu")
    parser.add_argument(
        "--task",
        choices=TASKS,
        default="seven_multilabel",
        help="Seven-class multilabel or explicit vespa_velutina binary task",
    )
    parser.add_argument(
        "--classes",
        choices=("vespa_velutina",),
        help="Optional short alias for an explicit vespa_velutina binary task",
    )
    return parser


def _load_runtime():
    try:
        import PIL
        import onnx
        import torch
        from PIL import Image, ImageFile
    except ImportError as exc:
        raise RuntimeError(
            "Install the reviewed optional dependencies from training/requirements-training.txt"
        ) from exc
    if (
        torch.__version__.split("+", 1)[0] != "2.9.1"
        or PIL.__version__ != "12.0.0"
        or onnx.__version__ != "1.20.1"
    ):
        raise RuntimeError("Training requires torch==2.9.1, Pillow==12.0.0 and onnx==1.20.1")
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    return torch, Image, onnx


def _make_model(torch, class_count: int):
    from torch import nn

    class SmallMultiLabelCNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.features = nn.Sequential(
                nn.Conv2d(3, 16, kernel_size=3, padding=1),
                nn.ReLU(inplace=False),
                nn.MaxPool2d(2),
                nn.Conv2d(16, 32, kernel_size=3, padding=1),
                nn.ReLU(inplace=False),
                nn.MaxPool2d(2),
                nn.Conv2d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(inplace=False),
                nn.AdaptiveAvgPool2d((1, 1)),
            )
            self.classifier = nn.Linear(64, class_count)

        def forward(self, images):
            return self.classifier(self.features(images).flatten(1))

    return SmallMultiLabelCNN()


def _load_image(image_path: Path, Image, torch):
    try:
        with Image.open(image_path) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"} or getattr(image, "n_frames", 1) != 1:
                raise ValueError(f"unsupported or animated image: {image_path}")
            if image.width < 16 or image.height < 16 or image.width * image.height > 80_000_000:
                raise ValueError(f"unsafe image dimensions: {image_path}")
            image = image.convert("RGB").resize((IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.BILINEAR)
            values = list(image.getdata())
        tensor = torch.tensor(values, dtype=torch.float32).reshape(IMAGE_SIZE, IMAGE_SIZE, 3)
        return tensor.permute(2, 0, 1).contiguous().div_(255.0)
    except (OSError, ValueError) as exc:
        raise DatasetValidationError(f"cannot decode reviewed image {image_path.name}") from exc


def _dataset_for_split(
    root: Path,
    rows: list[dict],
    split_plan: dict,
    split: str,
    Image,
    torch,
    task_classes: list[str],
):
    from torch.utils.data import Dataset

    row_by_image = {row["image"]: row for row in rows}
    selected = sorted(
        image for image, assigned_split in split_plan["splits"].items()
        if assigned_split == split
    )

    class LocalImageDataset(Dataset):
        def __len__(self):
            return len(selected)

        def __getitem__(self, index):
            image_name = selected[index]
            row = row_by_image[image_name]
            image_tensor = _load_image(root / image_name, Image, torch)
            target = torch.zeros(len(task_classes), dtype=torch.float32)
            for index, value in enumerate(task_targets(row["labels"], task_classes)):
                target[index] = value
            return image_tensor, target

    return LocalImageDataset()


def _evaluate(model, loader, torch, device, task_classes: list[str]):
    import torch.nn.functional as functional

    model.eval()
    total_loss = 0.0
    total_images = 0
    true_positive = torch.zeros(len(task_classes), dtype=torch.int64)
    false_positive = torch.zeros_like(true_positive)
    false_negative = torch.zeros_like(true_positive)
    with torch.no_grad():
        for images, targets in loader:
            images, targets = images.to(device), targets.to(device)
            logits = model(images)
            total_loss += functional.binary_cross_entropy_with_logits(
                logits, targets, reduction="sum"
            ).item()
            predicted = torch.sigmoid(logits) >= 0.5
            expected = targets >= 0.5
            true_positive += (predicted & expected).sum(dim=0).cpu()
            false_positive += (predicted & ~expected).sum(dim=0).cpu()
            false_negative += (~predicted & expected).sum(dim=0).cpu()
            total_images += len(images)
    metrics = {}
    for index, label in enumerate(task_classes):
        tp, fp, fn = int(true_positive[index]), int(false_positive[index]), int(false_negative[index])
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall
            else None
        )
        metrics[label] = {"tp": tp, "fp": fp, "fn": fn,
                          "precision_at_0_5": precision, "recall_at_0_5": recall,
                          "f1_at_0_5": f1}
    return {
        "images": total_images,
        "mean_binary_cross_entropy": total_loss / total_images if total_images else None,
        "fixed_threshold": 0.5,
        "per_class": metrics,
        "scope": "internal_validation_split_only_not_field_accuracy",
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _train_prepared(args, dataset_root: Path) -> dict:
    if not 1 <= args.epochs <= 500:
        raise ValueError("epochs must be in 1..500")
    if not 1 <= args.batch_size <= 256:
        raise ValueError("batch-size must be in 1..256")
    if not 0.000001 <= args.learning_rate <= 1:
        raise ValueError("learning-rate must be in 0.000001..1")
    if type(args.seed) is not int or not 0 <= args.seed <= 2_147_483_647:
        raise ValueError("seed must be in 0..2147483647")

    selected_task = "vespa_velutina_binary" if args.classes == "vespa_velutina" else args.task
    if args.classes == "vespa_velutina" and args.task not in ("seven_multilabel", "vespa_velutina_binary"):
        raise ValueError("unsupported training task")
    task = task_config(selected_task)
    task_classes = task["classes"]
    rows = validate_dataset(dataset_root)
    split_plan = create_split_plan(rows, seed=args.seed)
    train_images = [
        row for row in rows
        if split_plan["splits"][row["image"]] == "train"
    ]
    if selected_task == "seven_multilabel":
        train_label_counts = {
            label: sum(label in row["labels"] for row in train_images)
            for label in CLASS_NAMES
        }
        missing_train_labels = [label for label, count in train_label_counts.items() if not count]
        if missing_train_labels:
            raise DatasetValidationError(
                "training split lacks positive examples for: " + ", ".join(missing_train_labels)
            )
    else:
        positive_count = sum("vespa_velutina" in row["labels"] for row in train_images)
        negative_count = sum("vespa_velutina" not in row["labels"] for row in train_images)
        if positive_count == 0 or negative_count == 0:
            raise DatasetValidationError(
                "vespa_velutina binary training split requires positive and negative examples"
            )
    if any(not split_plan["summary"][split]["images"] for split in ("train", "val", "test")):
        raise DatasetValidationError("train, val and test splits must all contain images")

    torch, Image, onnx = _load_runtime()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    device = torch.device("cpu")

    from torch.utils.data import DataLoader
    train_dataset = _dataset_for_split(
        dataset_root, rows, split_plan, "train", Image, torch, task_classes
    )
    val_dataset = _dataset_for_split(
        dataset_root, rows, split_plan, "val", Image, torch, task_classes
    )
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,
        generator=torch.Generator().manual_seed(args.seed),
    )
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)

    model = _make_model(torch, len(task_classes)).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    loss_fn = torch.nn.BCEWithLogitsLoss()
    history = []
    for epoch in range(args.epochs):
        model.train()
        epoch_loss = 0.0
        epoch_images = 0
        for images, targets in train_loader:
            images, targets = images.to(device), targets.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(images), targets)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item() * len(images)
            epoch_images += len(images)
        history.append({
            "epoch": epoch + 1,
            "train_mean_binary_cross_entropy": epoch_loss / epoch_images,
        })

    validation = _evaluate(model, val_loader, torch, device, task_classes)
    weights_path = output_dir / "classifier.pt"
    torch.save(model.state_dict(), weights_path)
    onnx_path = output_dir / "classifier.onnx"
    model.eval()
    torch.onnx.export(
        model,
        torch.zeros(1, 3, IMAGE_SIZE, IMAGE_SIZE, dtype=torch.float32),
        str(onnx_path),
        input_names=["images"],
        output_names=["logits"],
        opset_version=17,
        dynamo=False,
    )
    exported_model = onnx.load(str(onnx_path))
    onnx.checker.check_model(exported_model)
    graph_inputs = list(exported_model.graph.input)
    graph_outputs = list(exported_model.graph.output)
    if (
        len(graph_inputs) != 1
        or graph_inputs[0].name != "images"
        or [dimension.dim_value for dimension in graph_inputs[0].type.tensor_type.shape.dim]
        != [1, 3, IMAGE_SIZE, IMAGE_SIZE]
        or len(graph_outputs) != 1
        or graph_outputs[0].name != "logits"
        or [dimension.dim_value for dimension in graph_outputs[0].type.tensor_type.shape.dim]
        != [1, len(task_classes)]
    ):
        raise RuntimeError("exported ONNX input/output contract is unexpected")
    onnx_digest = _sha256_file(onnx_path)
    split_plan_bytes = json.dumps(split_plan, sort_keys=True, separators=(",", ":")).encode()
    report = {
        "format_version": 1,
        "status": "experimental_unvalidated",
        "task": task["name"],
        "classes": task_classes,
        "input": {
            "name": "images",
            "shape": [1, 3, IMAGE_SIZE, IMAGE_SIZE],
            "color": "RGB",
            "layout": "NCHW",
            "scale": "0..1",
        },
        "output": {
            "name": "logits",
            "shape": [1, len(task_classes)],
            "activation_for_inference": "sigmoid",
        },
        "artifacts": {
            "checkpoint": weights_path.name,
            "checkpoint_sha256": _sha256_file(weights_path),
            "onnx": onnx_path.name,
            "onnx_sha256": onnx_digest,
        },
        "dataset": {
            "root": "local_dataset",
            "annotations_jsonl_sha256": _sha256_file(
                dataset_root / "annotations.jsonl"
            ),
            "images": len(rows),
            "split_plan_sha256": hashlib.sha256(split_plan_bytes).hexdigest(),
            "split_summary": split_plan["summary"],
        },
        "training": {
            "torch": torch.__version__,
            "onnx": "1.20.1",
            "device": "cpu",
            "seed": args.seed,
            "deterministic_algorithms": True,
            "threads": 1,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "learning_rate": args.learning_rate,
            "optimizer": "Adam",
            "loss": "BCEWithLogitsLoss",
            "pretrained_weights": False,
            "history": history,
        },
        "validation": validation,
        "test_split_used_for_training_or_threshold_selection": False,
        "license_review": "dataset images and training dependency rights must be reviewed before running",
        "field_accuracy_claimed": False,
    }
    (output_dir / "training-evidence.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def train(args) -> dict:
    with prepared_dataset(args.dataset) as dataset_root:
        return _train_prepared(args, dataset_root)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = train(args)
    except (DatasetValidationError, OSError, RuntimeError, ValueError) as exc:
        print(f"Training stopped: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
