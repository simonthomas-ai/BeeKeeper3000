import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from camera.model_manifest import load_manifest
from training.build_provenance import (
    ProvenanceBuildError,
    build_provenance,
    write_outputs,
)


REVIEWER = "reviewer:image-reviewer-01"
SOURCE_REVIEWER = "reviewer:source-reviewer-01"
STAMP = "2026-11-20T12:30:00Z"


def annotation(image, *, source, basis, permission_ref=None, attribution=None, session="session-0001"):
    rights = {
        "source": source,
        "basis": basis,
        "status": "training_approved",
    }
    if basis == "CC0-1.0":
        rights["evidence_url"] = "https://creativecommons.org/publicdomain/zero/1.0/"
    elif basis == "CC-BY-4.0":
        rights["evidence_url"] = "https://creativecommons.org/licenses/by/4.0/"
        rights["attribution"] = attribution or "Synthetic creator (CC BY 4.0)"
    else:
        rights["permission_ref"] = permission_ref or "permission-opaque-0001"
    return {
        "image": image,
        "labels": ["vespa_velutina"],
        "captured_at": "2026-11-20T12:00:00Z",
        "capture_session_id": session,
        "labeler_id": "reviewer:labeler-0001",
        "review_status": "approved",
        "reviewed_by": REVIEWER,
        "reviewed_at": STAMP,
        "rights": rights,
    }


def source_review(source_url, license_id, *, revision=None, status="approved", reviewer=SOURCE_REVIEWER):
    row = {
        "source_url": source_url,
        "license": license_id,
        "license_review_status": status,
        "license_evidence_url": (
            None if license_id == "LicenseRef-ExplicitPermission"
            else "https://creativecommons.org/publicdomain/zero/1.0/"
            if license_id == "CC0-1.0"
            else "https://creativecommons.org/licenses/by/4.0/"
        ),
        "training_use_allowed": True,
        "redistribution_allowed": False,
        "reviewed_by": reviewer,
        "reviewed_at": "2026-11-21T09:00:00+01:00",
        "review_kind": "source_rights",
    }
    if revision is not None:
        row["revision"] = revision
    return row


class ProvenanceConverterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.archive = self.root / "field.zip"
        self.review = self.root / "source-review.json"

    def tearDown(self):
        self.temporary.cleanup()

    def write_archive(self, rows):
        with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("images/one.jpg", b"synthetic image bytes one")
            if len(rows) > 1:
                archive.writestr("images/two.jpg", b"synthetic image bytes two")
            archive.writestr(
                "annotations.jsonl",
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            )

    def write_review(self, sources):
        self.review.write_text(
            json.dumps({"format_version": 1, "sources": sources}, sort_keys=True),
            encoding="utf-8",
        )

    def local_fixture(self):
        rows = [
            annotation(
                "images/one.jpg",
                source="Eigene Feldaufnahme",
                basis="LicenseRef-ExplicitPermission",
                permission_ref="permission-opaque-0001",
            )
        ]
        self.write_archive(rows)
        self.write_review([
            source_review(
                "local-capture://session-0001",
                "LicenseRef-ExplicitPermission",
            )
        ])
        return rows

    def public_fixture(self, license_id="CC-BY-4.0"):
        source = "https://example.org/photos/item-001"
        rows = [
            annotation(
                "images/one.jpg",
                source=source,
                basis=license_id,
                attribution="Example photographer (CC BY 4.0)",
            )
        ]
        self.write_archive(rows)
        self.write_review([
            source_review(
                source,
                license_id,
                revision="a" * 40,
                status="public-domain" if license_id == "CC0-1.0" else "approved",
            )
        ])
        return rows

    def make_model_manifest(self, output_dir, result):
        provenance = output_dir / "provenance.jsonl"
        sources_path = output_dir / "training_data_sources.json"
        provenance.write_bytes(result["provenance_bytes"])
        sources_path.write_bytes(result["sources_bytes"])
        sources = json.loads(sources_path.read_text(encoding="utf-8"))["training_data_sources"]
        model = output_dir / "detector.onnx"
        model.write_bytes(b"synthetic model bytes; never executed")
        manifest = {
            "manifest_version": 2,
            "model_file": "detector.onnx",
            "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
            "dataset_manifest_file": "provenance.jsonl",
            "dataset_manifest_sha256": hashlib.sha256(provenance.read_bytes()).hexdigest(),
            "training_data_sources": sources,
            "model_version": "synthetic-test-only",
            "model_source_url": "https://example.org/synthetic-model",
            "model_license": "MIT",
            "license_review_status": "approved",
            "license_evidence_url": "https://example.org/model-license",
            "license_reviewed_by": "reviewer:model-reviewer-01",
            "license_reviewed_at": "2026-11-21T10:00:00Z",
            "inference_use_allowed": True,
            "redistribution_allowed": False,
            "inference_status": "experimental",
            "input": {
                "name": "images",
                "width": 640,
                "height": 640,
                "color": "RGB",
                "layout": "NCHW",
                "scale": "0..1",
            },
            "outputs": {
                "boxes": "boxes",
                "scores": "scores",
                "class_ids": "classes",
                "box_format": "xyxy_normalized_post_nms",
            },
            "classes": [
                {"id": 0, "label": "synthetic_candidate", "threshold": 0.5, "prey_detected": False}
            ],
        }
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path

    def test_local_capture_uses_exact_archive_digest_and_opaque_permission(self):
        self.local_fixture()
        result = build_provenance(self.archive, self.review)
        row = json.loads(result["provenance_bytes"].decode("utf-8"))
        self.assertEqual(row["source_url"], "local-capture://session-0001")
        self.assertEqual(row["revision"], "sha256:" + hashlib.sha256(self.archive.read_bytes()).hexdigest())
        self.assertEqual(row["permission_ref"], "permission-opaque-0001")
        self.assertNotIn("captured_at", row)
        self.assertNotIn("capture_session_id", row)
        self.assertNotIn("labeler_id", row)
        self.assertNotIn("rights", row)
        self.assertNotIn("gps", row)

    def test_cc_by_and_cc0_use_separate_source_review_and_immutable_revision(self):
        source_by = "https://example.org/photos/by"
        source_zero = "https://example.org/photos/zero"
        rows = [
            annotation(
                "images/one.jpg",
                source=source_by,
                basis="CC-BY-4.0",
                attribution="Photographer A (CC BY 4.0)",
                session="session-0001",
            ),
            annotation(
                "images/two.jpg",
                source=source_zero,
                basis="CC0-1.0",
                session="session-0002",
            ),
        ]
        self.write_archive(rows)
        self.write_review([
            source_review(source_by, "CC-BY-4.0", revision="a" * 40),
            source_review(source_zero, "CC0-1.0", revision="b" * 40, status="public-domain"),
        ])
        result = build_provenance(self.archive, self.review)
        output_rows = [json.loads(line) for line in result["provenance_bytes"].decode().splitlines()]
        self.assertEqual(len(output_rows), 2)
        self.assertEqual(output_rows[0]["attribution"], "Photographer A (CC BY 4.0)")
        self.assertEqual(output_rows[1]["license_review_status"], "public-domain")
        self.assertEqual(result["source_count"], 2)

    def test_converter_output_is_accepted_by_model_manifest_v2_validator(self):
        self.local_fixture()
        result = build_provenance(self.archive, self.review)
        output_dir = self.root / "converted"
        output_dir.mkdir()
        manifest_path = self.make_model_manifest(output_dir, result)
        manifest = load_manifest(manifest_path, verify_model=True)
        self.assertEqual(manifest.dataset_manifest_path.name, "provenance.jsonl")
        self.assertEqual(manifest.training_data_sources[0].license_id, "LicenseRef-ExplicitPermission")
        self.assertEqual(manifest.training_data_sources[0].revision, "sha256:" + result["archive_sha256"])

    def test_output_is_deterministic_for_the_same_archive_and_review(self):
        self.local_fixture()
        first = build_provenance(self.archive, self.review)
        second = build_provenance(self.archive, self.review)
        self.assertEqual(first["archive_sha256"], second["archive_sha256"])
        self.assertEqual(first["provenance_bytes"], second["provenance_bytes"])
        self.assertEqual(first["sources_bytes"], second["sources_bytes"])

    def test_user_training_attestation_alone_does_not_approve_source_rights(self):
        self.local_fixture()
        self.review.unlink()
        with self.assertRaisesRegex(ProvenanceBuildError, "source-rights review"):
            build_provenance(self.archive, self.review)

    def test_source_rights_reviewer_must_differ_from_image_reviewer(self):
        self.local_fixture()
        self.write_review([
            source_review(
                "local-capture://session-0001",
                "LicenseRef-ExplicitPermission",
                reviewer=REVIEWER,
            )
        ])
        with self.assertRaisesRegex(ProvenanceBuildError, "distinct"):
            build_provenance(self.archive, self.review)

    def test_rejects_missing_training_permission_and_unreviewed_source(self):
        self.public_fixture()
        entries = [source_review(
            "https://example.org/photos/item-001",
            "CC-BY-4.0",
            revision="a" * 40,
        )]
        entries[0]["training_use_allowed"] = False
        self.write_review(entries)
        with self.assertRaisesRegex(ProvenanceBuildError, "permit training"):
            build_provenance(self.archive, self.review)

        entries[0]["training_use_allowed"] = True
        entries[0]["license_review_status"] = "not-reviewed"
        self.write_review(entries)
        with self.assertRaisesRegex(ProvenanceBuildError, "not explicitly reviewed"):
            build_provenance(self.archive, self.review)

    def test_rejects_public_source_without_immutable_revision(self):
        self.public_fixture()
        self.write_review([
            source_review(
                "https://example.org/photos/item-001",
                "CC-BY-4.0",
                revision="main",
            )
        ])
        with self.assertRaisesRegex(ProvenanceBuildError, "full commit SHA"):
            build_provenance(self.archive, self.review)

    def test_rejects_public_explicit_permission_and_local_public_license(self):
        rows = [
            annotation(
                "images/one.jpg",
                source="https://example.org/photos/item-001",
                basis="LicenseRef-ExplicitPermission",
            )
        ]
        self.write_archive(rows)
        self.write_review([
            source_review(
                "https://example.org/photos/item-001",
                "CC-BY-4.0",
                revision="a" * 40,
            )
        ])
        with self.assertRaisesRegex(ProvenanceBuildError, "reserved for opaque local"):
            build_provenance(self.archive, self.review)

        rows = [
            annotation(
                "images/one.jpg",
                source="Eigene Feldaufnahme",
                basis="CC0-1.0",
            )
        ]
        self.write_archive(rows)
        self.write_review([
            source_review("local-capture://session-0001", "LicenseRef-ExplicitPermission")
        ])
        with self.assertRaisesRegex(ProvenanceBuildError, "local field captures require"):
            build_provenance(self.archive, self.review)

    def test_rejects_unknown_source_review_fields_and_duplicate_json_keys(self):
        self.local_fixture()
        entries = [source_review(
            "local-capture://session-0001",
            "LicenseRef-ExplicitPermission",
        )]
        entries[0]["personal_name"] = "not allowed"
        self.write_review(entries)
        with self.assertRaisesRegex(ProvenanceBuildError, "unknown fields"):
            build_provenance(self.archive, self.review)

        self.review.write_text(
            '{"format_version":1,"format_version":1,"sources":[]}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ProvenanceBuildError, "unique-key"):
            build_provenance(self.archive, self.review)

    def test_rejects_invalid_local_identifier_and_local_revision_override(self):
        rows = [
            annotation(
                "images/one.jpg",
                source="Eigene Feldaufnahme",
                basis="LicenseRef-ExplicitPermission",
                session="short",
            )
        ]
        self.write_archive(rows)
        self.write_review([
            source_review("local-capture://session-0001", "LicenseRef-ExplicitPermission")
        ])
        with self.assertRaisesRegex(ProvenanceBuildError, "safe opaque identifier"):
            build_provenance(self.archive, self.review)

        self.local_fixture()
        entries = [source_review(
            "local-capture://session-0001",
            "LicenseRef-ExplicitPermission",
        )]
        entries[0]["revision"] = "a" * 40
        self.write_review(entries)
        with self.assertRaisesRegex(ProvenanceBuildError, "unknown fields"):
            build_provenance(self.archive, self.review)

    def test_rejects_unreferenced_source_review_entries(self):
        self.local_fixture()
        entries = [
            source_review("local-capture://session-0001", "LicenseRef-ExplicitPermission"),
            source_review(
                "https://example.org/unused",
                "CC0-1.0",
                revision="a" * 40,
                status="public-domain",
            ),
        ]
        self.write_review(entries)
        with self.assertRaisesRegex(ProvenanceBuildError, "unused or unreferenced"):
            build_provenance(self.archive, self.review)

    def test_rejects_archive_path_traversal(self):
        self.write_review([
            source_review("local-capture://session-0001", "LicenseRef-ExplicitPermission")
        ])
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("images/../escape.jpg", b"synthetic")
            archive.writestr("annotations.jsonl", "{}\n")
        with self.assertRaises(Exception):
            build_provenance(self.archive, self.review)

    def test_write_outputs_never_overwrites_an_existing_directory(self):
        self.local_fixture()
        result = build_provenance(self.archive, self.review)
        output_dir = self.root / "converted"
        write_outputs(result, output_dir)
        self.assertTrue((output_dir / "provenance.jsonl").is_file())
        with self.assertRaises(FileExistsError):
            write_outputs(result, output_dir)


if __name__ == "__main__":
    unittest.main()
