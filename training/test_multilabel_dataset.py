import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from training.multilabel_dataset import (
    CLASS_NAMES,
    DatasetValidationError,
    create_split_plan,
    main,
    validate_dataset_archive,
    validate_dataset,
)
try:
    from training.train_multilabel import _build_parser, task_config, task_targets
except ImportError:
    _build_parser = None
    task_config = None
    task_targets = None


def rights(*, basis="CC0-1.0", **changes):
    result = {
        "source": "https://example.org/photos/item",
        "basis": basis,
        "status": "training_approved",
        "publication_allowed": True,
    }
    if basis in {"CC0-1.0", "CC-BY-4.0"}:
        result["evidence_url"] = (
            "https://creativecommons.org/publicdomain/zero/1.0/"
            if basis == "CC0-1.0"
            else "https://creativecommons.org/licenses/by/4.0/"
        )
    if basis == "CC-BY-4.0":
        result["attribution"] = "Example creator (CC BY 4.0)"
    if basis == "LicenseRef-ExplicitPermission":
        result["permission_ref"] = "permission-record-1"
    result.update(changes)
    return result


class DatasetFixture:
    def __init__(self, root):
        self.root = Path(root)
        (self.root / "images").mkdir()

    def add(
        self,
        name,
        content,
        *,
        labels=None,
        session=None,
        source=None,
        review_status="approved",
        photo_rights=None,
        captured_at="2026-11-20T12:00:00Z",
    ):
        image = f"images/{name}.jpg"
        (self.root / image).write_bytes(content)
        item_rights = photo_rights or rights(source=f"https://example.org/photos/{name}")
        if source is not None:
            item_rights = {**item_rights, "source": source}
        return {
            "image": image,
            "labels": labels if labels is not None else [CLASS_NAMES[0]],
            "captured_at": captured_at,
            "capture_session_id": session or f"session-{name}",
            "review_status": review_status,
            "rights": item_rights,
        }

    def write(self, rows):
        (self.root / "annotations.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )


class MultiLabelDatasetTests(unittest.TestCase):
    def test_training_task_configs_keep_seven_and_binary_contracts_separate(self):
        if task_config is None:
            self.skipTest("training task module unavailable")
        seven = task_config("seven_multilabel")
        binary = task_config("vespa_velutina_binary")
        self.assertEqual(len(seven["classes"]), 7)
        self.assertEqual(binary["classes"], ["vespa_velutina"])
        with self.assertRaisesRegex(ValueError, "unsupported"):
            task_config("unknown")

    def test_classes_alias_selects_one_binary_class(self):
        if _build_parser is None:
            self.skipTest("training task module unavailable")
        args = _build_parser().parse_args([
            "--dataset", "fixture.zip",
            "--output-dir", "fixture-output",
            "--classes", "vespa_velutina",
        ])
        self.assertEqual(args.classes, "vespa_velutina")

    def test_binary_task_targets_positive_and_negative_without_confusing_other_labels(self):
        if task_targets is None:
            self.skipTest("training task module unavailable")
        classes = ["vespa_velutina"]
        self.assertEqual(task_targets(["vespa_velutina", "apis_mellifera"], classes), [1.0])
        self.assertEqual(task_targets(["apis_mellifera", "bombus_spp"], classes), [0.0])
        self.assertEqual(task_targets([], classes), [0.0])

    def test_accepts_multilabel_and_reviewed_negative_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = DatasetFixture(tmp)
            positive = data.add("positive", b"private fixture one", labels=[CLASS_NAMES[0], CLASS_NAMES[3]])
            negative = data.add("negative", b"private fixture two", labels=[])
            data.write([positive, negative])
            rows = validate_dataset(tmp)
            self.assertEqual(rows[0]["labels"], [CLASS_NAMES[0], CLASS_NAMES[3]])
            self.assertEqual(rows[1]["labels"], [])

    def test_requires_exact_manifest_to_image_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = DatasetFixture(tmp)
            row = data.add("listed", b"fixture 1")
            data.add("unlisted", b"fixture 2")
            data.write([row])
            with self.assertRaisesRegex(DatasetValidationError, "inventory mismatch"):
                validate_dataset(tmp)

    def test_rejects_duplicate_image_bytes_and_duplicate_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = DatasetFixture(tmp)
            first = data.add("one", b"same image", labels=[CLASS_NAMES[0], CLASS_NAMES[0]])
            data.write([first])
            with self.assertRaisesRegex(DatasetValidationError, "unique known class"):
                validate_dataset(tmp)
        with tempfile.TemporaryDirectory() as tmp:
            data = DatasetFixture(tmp)
            first = data.add("one", b"same image")
            second = data.add("two", b"same image")
            data.write([first, second])
            with self.assertRaisesRegex(DatasetValidationError, "duplicates image bytes"):
                validate_dataset(tmp)

    def test_rejects_unknown_labels_path_traversal_and_timezone_naive_time(self):
        variants = [
            ("labels", {"labels": ["unknown"]}, "unique known class"),
            ("path", {"image": "images/../outside.jpg"}, "clean supported path"),
            ("time", {"captured_at": "2026-11-20T12:00:00"}, "include a timezone"),
        ]
        for name, update, message in variants:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                data = DatasetFixture(tmp)
                row = data.add(name, b"fixture " + name.encode())
                row.update(update)
                data.write([row])
                with self.assertRaisesRegex(DatasetValidationError, message):
                    validate_dataset(tmp)

    def test_rejects_unreviewed_or_unpublished_data_and_missing_rights(self):
        cases = [
            ({"review_status": "pending"}, "review_status must be approved"),
            ({"rights": rights(status="pending")}, "rights.status must be training_approved"),
            ({"rights": rights(basis=[])}, "rights.basis must be a non-empty bounded value"),
            ({"rights": rights(basis="Nutzerangabe")}, "basis must be CC0-1.0"),
            ({"rights": rights(source="http://example.org/photo")}, "credential-free HTTPS URL"),
            (
                {"rights": rights(publication_allowed=False)},
                "publication_allowed must be true",
            ),
            ({"rights": {"source": "https://example.org"}}, "rights.basis must be a non-empty bounded value"),
        ]
        for index, (change, message) in enumerate(cases):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as tmp:
                data = DatasetFixture(tmp)
                row = data.add(f"item-{index}", f"fixture {index}".encode())
                row.update(change)
                data.write([row])
                with self.assertRaisesRegex(DatasetValidationError, message):
                    validate_dataset(tmp)

    def test_requires_license_evidence_attribution_and_explicit_permission_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = DatasetFixture(tmp)
            row = data.add(
                "shared", b"shared image",
                photo_rights=rights(basis="CC-BY-4.0", source="https://example.org/photos/shared"),
            )
            data.write([row])
            rows = validate_dataset(tmp)
            self.assertEqual(rows[0]["source"], "https://example.org/photos/shared")

        missing_cc0_evidence = rights(basis="CC0-1.0")
        missing_cc0_evidence.pop("evidence_url")
        invalid_rights = [
            (missing_cc0_evidence, "evidence_url is required"),
            (rights(basis="CC-BY-4.0", attribution=""), "attribution is required"),
            (rights(basis="LicenseRef-ExplicitPermission", permission_ref=""), "permission_ref is required"),
        ]
        for index, (photo_rights, message) in enumerate(invalid_rights):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as tmp:
                data = DatasetFixture(tmp)
                row = data.add(f"invalid-{index}", f"fixture {index}".encode(), photo_rights=photo_rights)
                data.write([row])
                with self.assertRaisesRegex(DatasetValidationError, message):
                    validate_dataset(tmp)

        with tempfile.TemporaryDirectory() as tmp:
            data = DatasetFixture(tmp)
            row = data.add(
                "permission", b"permission image",
                photo_rights=rights(
                    basis="LicenseRef-ExplicitPermission",
                    source="Eigene Feldaufnahme",
                    permission_ref="owner-consent-record-2026-001",
                ),
            )
            data.write([row])
            rows = validate_dataset(tmp)
            self.assertIsNone(rows[0]["source"])

    def test_rejects_manifest_duplicate_keys_and_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = DatasetFixture(tmp)
            row = data.add("one", b"fixture")
            data.write([row])
            (data.root / "annotations.jsonl").write_text(
                '{"image":"images/one.jpg","image":"images/one.jpg"}\n', encoding="utf-8"
            )
            with self.assertRaisesRegex(DatasetValidationError, "unique-key JSON"):
                validate_dataset(tmp)
        with tempfile.TemporaryDirectory() as tmp:
            data = DatasetFixture(tmp)
            row = data.add("one", b"fixture")
            (data.root / row["image"]).unlink()
            data.write([row])
            with self.assertRaisesRegex(DatasetValidationError, "missing or escapes"):
                validate_dataset(tmp)

    def test_split_is_deterministic_and_keeps_source_and_session_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = DatasetFixture(tmp)
            rows = []
            rows.append(data.add("a", b"fixture a", session="shared-session"))
            rows.append(data.add("b", b"fixture b", session="shared-session", source="https://example.org/b"))
            rows.append(data.add("g", b"fixture g", session="session-g", source="https://example.org/shared"))
            rows.append(data.add("h", b"fixture h", session="session-h", source="https://example.org/shared"))
            for name in "cdef":
                rows.append(data.add(name, f"fixture {name}".encode()))
            data.write(rows)
            validated = validate_dataset(tmp)
            first = create_split_plan(validated, seed=7)
            second = create_split_plan(validated, seed=7)
            self.assertEqual(first, second)
            self.assertEqual(
                first["splits"]["images/a.jpg"], first["splits"]["images/b.jpg"]
            )
            self.assertEqual(
                first["splits"]["images/g.jpg"], first["splits"]["images/h.jpg"]
            )
            self.assertEqual(set(first["summary"]), {"train", "val", "test"})

    def test_refuses_split_with_fewer_than_three_independent_groups(self):
        rows = [
            {"image": f"images/{index}.jpg", "labels": [], "capture_session_id": "same-session",
             "source": f"https://example.org/{index}"}
            for index in range(3)
        ]
        with self.assertRaisesRegex(DatasetValidationError, "three independent"):
            create_split_plan(rows)

    def test_generic_field_source_does_not_join_all_images(self):
        rows = [
            {"image": f"images/{index}.jpg", "labels": [], "capture_session_id": f"s{index}",
             "source": None}
            for index in range(3)
        ]
        plan = create_split_plan(rows, seed=42)
        self.assertEqual(set(plan["summary"]), {"train", "val", "test"})

    def test_refuses_non_finite_split_ratios(self):
        rows = [
            {"image": f"images/{index}.jpg", "labels": [], "capture_session_id": f"s{index}",
             "source": f"https://example.org/{index}"}
            for index in range(3)
        ]
        with self.assertRaisesRegex(DatasetValidationError, "finite"):
            create_split_plan(rows, ratios={"train": float("nan"), "val": 0.15, "test": 0.15})

    def test_summary_cli_does_not_print_private_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = DatasetFixture(tmp)
            rows = [
                data.add(f"private-coordinate-{index}", f"fixture {index}".encode())
                for index in range(3)
            ]
            data.write(rows)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(["--dataset", tmp])
            self.assertEqual(result, 0)
            self.assertNotIn("private-coordinate", output.getvalue())

    def test_accepts_safe_zip_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "field.zip"
            rows = [
                {"image":"images/a.jpg","labels":[CLASS_NAMES[0]],"captured_at":"2026-11-20T12:00:00Z","capture_session_id":"session-a","review_status":"approved","rights":{"source":"Eigene Feldaufnahme","basis":"LicenseRef-ExplicitPermission","status":"training_approved","permission_ref":"owner-consent-a"}},
                {"image":"images/b.jpg","labels":[],"captured_at":"2026-11-20T13:00:00Z","capture_session_id":"session-b","review_status":"approved","rights":{"source":"Eigene Feldaufnahme","basis":"LicenseRef-ExplicitPermission","status":"training_approved","permission_ref":"owner-consent-b"}},
                {"image":"images/c.jpg","labels":[CLASS_NAMES[1]],"captured_at":"2026-11-20T14:00:00Z","capture_session_id":"session-c","review_status":"approved","rights":{"source":"Eigene Feldaufnahme","basis":"LicenseRef-ExplicitPermission","status":"training_approved","permission_ref":"owner-consent-c"}},
            ]
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("annotations.jsonl", "".join(json.dumps(row) + "\n" for row in rows))
                for name in ("a", "b", "c"):
                    output.writestr(f"images/{name}.jpg", f"fixture {name}".encode())
            validated = validate_dataset_archive(archive)
            self.assertEqual(len(validated), 3)

    def test_rejects_zip_traversal_duplicate_and_unlisted_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("annotations.jsonl", "{}\n")
                output.writestr("../outside.jpg", b"escape")
            with self.assertRaisesRegex(DatasetValidationError, "unsafe path|traversal"):
                validate_dataset_archive(archive)
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "duplicate.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("annotations.jsonl", "{}\n")
                output.writestr("images/a.jpg", b"one")
                output.writestr("images/a.jpg", b"two")
            with self.assertRaisesRegex(DatasetValidationError, "duplicate path"):
                validate_dataset_archive(archive)

    def test_rejects_noncontract_zip_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "unexpected.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("annotations.jsonl", "{}\n")
                output.writestr("other/", b"")
            with self.assertRaisesRegex(DatasetValidationError, "only images"):
                validate_dataset_archive(archive)


if __name__ == "__main__":
    unittest.main()
