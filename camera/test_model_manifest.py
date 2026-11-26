import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from camera.model_manifest import load_manifest, ModelManifestError


class ManifestTests(unittest.TestCase):
    def make(self, tmp, **changes):
        model = Path(tmp) / "detector.onnx"
        model.write_bytes(b"synthetic model file for hash checks")
        provenance = Path(tmp) / "provenance.jsonl"
        provenance_row = {
            "image": "images/sample.jpg",
            "image_sha256": "a" * 64,
            "source_url": "https://example.org/dataset",
            "revision": "a" * 40,
            "license": "CC-BY-4.0",
            "license_review_status": "approved",
            "training_use_allowed": True,
            "redistribution_allowed": False,
            "reviewed_by": "reviewer:test-0001",
            "reviewed_at": "2026-11-20T12:00:00Z",
            "attribution": "Example creator (CC BY 4.0)",
        }
        provenance_bytes = (json.dumps(provenance_row, sort_keys=True) + "\n").encode("utf-8")
        provenance.write_bytes(provenance_bytes)
        data = {
            "manifest_version": 2, "model_file": "detector.onnx",
            "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
            "dataset_manifest_file": "provenance.jsonl",
            "dataset_manifest_sha256": hashlib.sha256(provenance_bytes).hexdigest(),
            "training_data_sources": [{
                "source_url": "https://example.org/dataset",
                "revision": "a" * 40,
                "license": "CC-BY-4.0",
                "license_review_status": "approved",
                "license_evidence_url": "https://creativecommons.org/licenses/by/4.0/",
                "training_use_allowed": True,
                "redistribution_allowed": False,
                "reviewed_by": "reviewer:test-0001",
                "reviewed_at": "2026-11-20T12:00:00Z",
            }],
            "model_version": "0.0-test", "model_source_url": "https://example.org/model",
            "model_license": "MIT", "license_review_status": "approved", "license_evidence_url": "https://example.org/LICENSE", "license_reviewed_by": "reviewer:test-0001", "license_reviewed_at": "2026-11-20T12:00:00Z", "inference_use_allowed": True, "redistribution_allowed": False, "inference_status": "experimental",
            "input": {"name": "images", "width": 640, "height": 640, "color": "RGB", "layout": "NCHW", "scale": "0..1"},
            "outputs": {"boxes": "boxes", "scores": "scores", "class_ids": "classes", "box_format": "xyxy_normalized_post_nms"},
            "classes": [{"id": 0, "label": "vespa_velutina_candidate", "threshold": 0.8, "prey_detected": False}],
        }
        data.update(changes)
        target = Path(tmp) / "manifest.json"
        target.write_text(json.dumps(data), encoding="utf-8")
        return target


    def default_provenance_row(self):
        return {
            "image": "images/sample.jpg",
            "image_sha256": "a" * 64,
            "source_url": "https://example.org/dataset",
            "revision": "a" * 40,
            "license": "CC-BY-4.0",
            "license_review_status": "approved",
            "training_use_allowed": True,
            "redistribution_allowed": False,
            "reviewed_by": "reviewer:image-0001",
            "reviewed_at": "2026-11-20T12:30:00Z",
            "attribution": "Example creator (CC BY 4.0)",
        }

    def rewrite_provenance(self, manifest_path, payload):
        provenance = manifest_path.parent / "provenance.jsonl"
        provenance.write_bytes(payload)
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["dataset_manifest_sha256"] = hashlib.sha256(payload).hexdigest()
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
        return manifest_path

    def test_valid_manifest_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = load_manifest(self.make(tmp))
            self.assertEqual(manifest.classes[0].label, "vespa_velutina_candidate")
            self.assertEqual(manifest.dataset_manifest_path.name, "provenance.jsonl")
            self.assertEqual(manifest.training_data_sources[0].license_id, "CC-BY-4.0")

    def test_rejects_unreviewed_license_and_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, license_review_status="not-reviewed")
            with self.assertRaises(ModelManifestError):
                load_manifest(path)
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, model_sha256="0" * 64)
            with self.assertRaises(ModelManifestError):
                load_manifest(path)

    def test_rejects_missing_license_evidence_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, license_evidence_url="")
            with self.assertRaises(ModelManifestError):
                load_manifest(path)
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, inference_use_allowed=False)
            with self.assertRaises(ModelManifestError):
                load_manifest(path)
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, license_reviewed_at="2026-11-20")
            with self.assertRaises(ModelManifestError):
                load_manifest(path)

    def test_accepts_ultralytics_post_nms_matrix_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["input"]["resize_mode"] = "letterbox"
            data["outputs"] = {
                "detections": "output0",
                "box_format": "xyxy_pixels_nms_matrix6"
            }
            path.write_text(json.dumps(data), encoding="utf-8")
            manifest = load_manifest(path)
            self.assertEqual(manifest.box_format, "xyxy_pixels_nms_matrix6")
            self.assertEqual(manifest.detections_output, "output0")
            self.assertEqual(manifest.resize_mode, "letterbox")

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            outside = parent / "outside.onnx"
            outside.write_bytes(b"outside")
            path = self.make(tmp, model_file="../outside.onnx")
            with self.assertRaises(ModelManifestError):
                load_manifest(path)



    def test_rejects_missing_or_unreviewed_training_dataset_rights(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, training_data_sources=[])
            with self.assertRaisesRegex(ModelManifestError, "training_data_sources"):
                load_manifest(path)
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, training_data_sources=[{
                "source_url": "https://example.org/dataset",
                "revision": "a" * 40,
                "license": "CC-BY-4.0",
                "license_review_status": "not-reviewed",
                "license_evidence_url": "https://creativecommons.org/licenses/by/4.0/",
                "training_use_allowed": True,
                "redistribution_allowed": False,
                "reviewed_by": "reviewer:test-0001",
                "reviewed_at": "2026-11-20T12:00:00Z",
            }])
            with self.assertRaisesRegex(ModelManifestError, "explicitly reviewed"):
                load_manifest(path)
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, training_data_sources=[{
                "source_url": "https://example.org/dataset",
                "revision": "a" * 40,
                "license": "CC-BY-4.0",
                "license_review_status": "approved",
                "license_evidence_url": "https://creativecommons.org/licenses/by/4.0/",
                "training_use_allowed": False,
                "redistribution_allowed": False,
                "reviewed_by": "reviewer:test-0001",
                "reviewed_at": "2026-11-20T12:00:00Z",
            }])
            with self.assertRaisesRegex(ModelManifestError, "does not permit training"):
                load_manifest(path)

    def test_rejects_dataset_provenance_manifest_missing_mismatch_and_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, dataset_manifest_file="missing.jsonl")
            with self.assertRaisesRegex(ModelManifestError, "missing"):
                load_manifest(path)
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, dataset_manifest_sha256="0" * 64)
            with self.assertRaisesRegex(ModelManifestError, "SHA-256 mismatch"):
                load_manifest(path)
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            outside = parent / "outside.jsonl"
            outside.write_text('{"image":"outside.jpg"}\\n', encoding="utf-8")
            path = self.make(tmp, dataset_manifest_file="../outside.jsonl")
            with self.assertRaisesRegex(ModelManifestError, "relative POSIX path"):
                load_manifest(path)

    def test_rejects_dataset_source_query_credentials_and_duplicate_revision(self):
        for source_url in ("https://example.org/dataset?token=secret", "https://user:pass@example.org/dataset"):
            with tempfile.TemporaryDirectory() as tmp:
                path = self.make(tmp, training_data_sources=[{
                    "source_url": source_url,
                    "revision": "a" * 40,
                    "license": "CC-BY-4.0",
                    "license_review_status": "approved",
                    "license_evidence_url": "https://creativecommons.org/licenses/by/4.0/",
                    "training_use_allowed": True,
                    "redistribution_allowed": False,
                    "reviewed_by": "reviewer:test-0001",
                    "reviewed_at": "2026-11-20T12:00:00Z",
                }])
                with self.assertRaisesRegex(ModelManifestError, "credential-free HTTPS"):
                    load_manifest(path)
        with tempfile.TemporaryDirectory() as tmp:
            source = {
                "source_url": "https://example.org/dataset",
                "revision": "a" * 40,
                "license": "CC-BY-4.0",
                "license_review_status": "approved",
                "license_evidence_url": "https://creativecommons.org/licenses/by/4.0/",
                "training_use_allowed": True,
                "redistribution_allowed": False,
                "reviewed_by": "reviewer:test-0001",
                "reviewed_at": "2026-11-20T12:00:00Z",
            }
            path = self.make(tmp, training_data_sources=[source, source])
            with self.assertRaisesRegex(ModelManifestError, "duplicate training dataset"):
                load_manifest(path)
        with tempfile.TemporaryDirectory() as tmp:
            source = {
                "source_url": "https://example.org/dataset",
                "revision": "main",
                "license": "CC-BY-4.0",
                "license_review_status": "approved",
                "license_evidence_url": "https://creativecommons.org/licenses/by/4.0/",
                "training_use_allowed": True,
                "redistribution_allowed": False,
                "reviewed_by": "reviewer:test-0001",
                "reviewed_at": "2026-11-20T12:00:00Z",
            }
            path = self.make(tmp, training_data_sources=[source])
            with self.assertRaisesRegex(ModelManifestError, "full Git commit SHA"):
                load_manifest(path)

    def test_rejects_dataset_provenance_symlink_and_oversized_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp)
            provenance = Path(tmp) / "provenance.jsonl"
            alias = Path(tmp) / "alias.jsonl"
            try:
                alias.symlink_to(provenance)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symbolic links are unavailable: {exc}")
            data = json.loads(path.read_text(encoding="utf-8"))
            data["dataset_manifest_file"] = "alias.jsonl"
            data["dataset_manifest_sha256"] = hashlib.sha256(provenance.read_bytes()).hexdigest()
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ModelManifestError, "symbolic links"):
                load_manifest(path)
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp)
            provenance = Path(tmp) / "provenance.jsonl"
            provenance.write_bytes(b"x" * 5)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["dataset_manifest_sha256"] = hashlib.sha256(provenance.read_bytes()).hexdigest()
            path.write_text(json.dumps(data), encoding="utf-8")
            with patch("camera.model_manifest.MAX_DATASET_PROVENANCE_BYTES", 4):
                with self.assertRaisesRegex(ModelManifestError, "maximum supported size"):
                    load_manifest(path)


    def test_rejects_malformed_empty_and_duplicate_key_dataset_provenance(self):
        cases = [
            (b"", "must contain 1 to"),
            (b"not-json\n", "line 1 is not valid unique-key JSON"),
            (b'{"image":"images/a.jpg","image":"images/b.jpg"}\n', "line 1 is not valid unique-key JSON"),
        ]
        for payload, message in cases:
            with tempfile.TemporaryDirectory() as tmp:
                path = self.make(tmp)
                self.rewrite_provenance(path, payload)
                with self.assertRaisesRegex(ModelManifestError, message):
                    load_manifest(path)

    def test_rejects_unlinked_or_unreviewed_per_image_provenance(self):
        cases = [
            ({"source_url": "https://other.example/dataset"}, "approved training_data_sources"),
            ({"training_use_allowed": False}, "does not explicitly permit training use"),
            ({"license_review_status": "not-reviewed"}, "review status does not match"),
            ({"image_sha256": "bad"}, "image_sha256 must be 64"),
            ({"image": "images/../private.jpg"}, "clean relative POSIX path"),
            ({"image": r"images\\private.jpg"}, "clean relative POSIX path"),
            ({"gps": "52.0,8.0"}, "unknown or missing fields"),
            ({"attribution": ""}, "requires CC-BY attribution"),
        ]
        for index, (change, message) in enumerate(cases):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as tmp:
                path = self.make(tmp)
                row = self.default_provenance_row()
                row.update(change)
                payload = (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")
                self.rewrite_provenance(path, payload)
                with self.assertRaisesRegex(ModelManifestError, message):
                    load_manifest(path)

    def test_rejects_duplicate_image_paths_and_duplicate_image_hashes(self):
        first = self.default_provenance_row()
        second = {**first, "image_sha256": "b" * 64}
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp)
            payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in (first, second)).encode("utf-8")
            self.rewrite_provenance(path, payload)
            with self.assertRaisesRegex(ModelManifestError, "duplicates an image path"):
                load_manifest(path)
        second = {**first, "image": "images/second.jpg"}
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp)
            payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in (first, second)).encode("utf-8")
            self.rewrite_provenance(path, payload)
            with self.assertRaisesRegex(ModelManifestError, "duplicates image bytes"):
                load_manifest(path)


    def test_accepts_local_field_capture_with_archive_digest_and_opaque_permission(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp)
            data = json.loads(path.read_text(encoding="utf-8"))
            source_url = "local-capture://batch-2026-11-26-a1"
            revision = "sha256:" + "c" * 64
            data["training_data_sources"] = [{
                "source_url": source_url,
                "revision": revision,
                "license": "LicenseRef-ExplicitPermission",
                "license_review_status": "approved",
                "training_use_allowed": True,
                "redistribution_allowed": False,
                "reviewed_by": "reviewer:test-0001",
                "reviewed_at": "2026-11-26T03:00:00Z",
            }]
            row = self.default_provenance_row()
            row.update({
                "source_url": source_url,
                "revision": revision,
                "license": "LicenseRef-ExplicitPermission",
                "license_review_status": "approved",
                "reviewed_by": "reviewer:test-0001",
                "reviewed_at": "2026-11-26T03:00:00Z",
                "permission_ref": "consent-record-opaque-001",
            })
            row.pop("attribution")
            payload = (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")
            (Path(tmp) / "provenance.jsonl").write_bytes(payload)
            data["dataset_manifest_sha256"] = hashlib.sha256(payload).hexdigest()
            path.write_text(json.dumps(data), encoding="utf-8")
            manifest = load_manifest(path)
            self.assertEqual(manifest.training_data_sources[0].source_url, source_url)
            self.assertIsNone(manifest.training_data_sources[0].license_evidence_url)

    def test_rejects_local_capture_source_for_public_license(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = {
                "source_url": "local-capture://batch-2026-11-26-a1",
                "revision": "sha256:" + "c" * 64,
                "license": "CC-BY-4.0",
                "license_review_status": "approved",
                "license_evidence_url": "https://creativecommons.org/licenses/by/4.0/",
                "training_use_allowed": True,
                "redistribution_allowed": False,
                "reviewed_by": "reviewer:test-0001",
                "reviewed_at": "2026-11-20T12:00:00Z",
            }
            path = self.make(tmp, training_data_sources=[source])
            with self.assertRaisesRegex(ModelManifestError, "local-capture source must use"):
                load_manifest(path)

    def test_requires_explicit_permission_reference_for_per_image_license_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["training_data_sources"] = [{
                "source_url": "https://example.org/dataset",
                "revision": "a" * 40,
                "license": "LicenseRef-ExplicitPermission",
                "license_review_status": "approved",
                "license_evidence_url": "https://example.org/permission-record",
                "training_use_allowed": True,
                "redistribution_allowed": False,
                "reviewed_by": "reviewer:test-0001",
                "reviewed_at": "2026-11-20T12:00:00Z",
            }]
            row = self.default_provenance_row()
            row["license"] = "LicenseRef-ExplicitPermission"
            row["license_review_status"] = "approved"
            row.pop("attribution")
            payload = (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")
            provenance = Path(tmp) / "provenance.jsonl"
            provenance.write_bytes(payload)
            data["dataset_manifest_sha256"] = hashlib.sha256(payload).hexdigest()
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ModelManifestError, "requires a bounded permission_ref"):
                load_manifest(path)

    def test_requires_full_immutable_dataset_revision_and_supported_license(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = {
                "source_url": "https://example.org/dataset",
                "revision": "dataset-v1",
                "license": "CC-BY-4.0",
                "license_review_status": "approved",
                "license_evidence_url": "https://creativecommons.org/licenses/by/4.0/",
                "training_use_allowed": True,
                "redistribution_allowed": False,
                "reviewed_by": "reviewer:test-0001",
                "reviewed_at": "2026-11-20T12:00:00Z",
            }
            path = self.make(tmp, training_data_sources=[source])
            with self.assertRaisesRegex(ModelManifestError, "full Git commit SHA"):
                load_manifest(path)
        with tempfile.TemporaryDirectory() as tmp:
            source = {
                "source_url": "https://example.org/dataset",
                "revision": "a" * 40,
                "license": "GPL-3.0",
                "license_review_status": "approved",
                "license_evidence_url": "https://example.org/license",
                "training_use_allowed": True,
                "redistribution_allowed": False,
                "reviewed_by": "reviewer:test-0001",
                "reviewed_at": "2026-11-20T12:00:00Z",
            }
            path = self.make(tmp, training_data_sources=[source])
            with self.assertRaisesRegex(ModelManifestError, "supported reviewed-license allowlist"):
                load_manifest(path)


    def test_rejects_unhashable_provenance_and_manifest_status_values(self):
        malformed_rows = [
            ({"source_url": []}, "source_url, revision and license must be strings"),
            ({"revision": []}, "source_url, revision and license must be strings"),
            ({"license": []}, "source_url, revision and license must be strings"),
        ]
        for index, (change, message) in enumerate(malformed_rows):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as tmp:
                path = self.make(tmp)
                row = self.default_provenance_row()
                row.update(change)
                payload = (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")
                self.rewrite_provenance(path, payload)
                with self.assertRaisesRegex(ModelManifestError, message):
                    load_manifest(path)

        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, license_review_status=[])
            with self.assertRaisesRegex(ModelManifestError, "model license must be explicitly reviewed"):
                load_manifest(path)
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, inference_status=[])
            with self.assertRaisesRegex(ModelManifestError, "inference_status must be experimental"):
                load_manifest(path)
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, input={"name":"images","width":640,"height":640,"color":"RGB","layout":"NCHW","scale":"0..1","resize_mode":[]})
            with self.assertRaisesRegex(ModelManifestError, "resize_mode must be stretch"):
                load_manifest(path)
        with tempfile.TemporaryDirectory() as tmp:
            source = {
                "source_url": "https://example.org/dataset",
                "revision": "a" * 40,
                "license": "CC-BY-4.0",
                "license_review_status": [],
                "license_evidence_url": "https://creativecommons.org/licenses/by/4.0/",
                "training_use_allowed": True,
                "redistribution_allowed": False,
                "reviewed_by": "reviewer:test-0001",
                "reviewed_at": "2026-11-20T12:00:00Z",
            }
            path = self.make(tmp, training_data_sources=[source])
            with self.assertRaisesRegex(ModelManifestError, "training dataset license must be explicitly reviewed"):
                load_manifest(path)

    def test_rejects_oversized_model_before_hash_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp)
            with patch("camera.model_manifest.MAX_MODEL_BYTES", 4):
                with self.assertRaisesRegex(ModelManifestError, "maximum supported size"):
                    load_manifest(path)

    def test_rejects_non_integer_manifest_version(self):
        for version in (True, 1.0, 1):
            with tempfile.TemporaryDirectory() as tmp:
                path = self.make(tmp, manifest_version=version)
                with self.subTest(version=version), self.assertRaises(ModelManifestError):
                    load_manifest(path)

    def test_rejects_duplicate_class_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["classes"].append({
                "id": 1,
                "label": data["classes"][0]["label"],
                "threshold": 0.7,
                "prey_detected": False,
            })
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ModelManifestError, "duplicate class"):
                load_manifest(path)

    def test_rejects_internal_symlink_model_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp)
            model = Path(tmp) / "detector.onnx"
            target = Path(tmp) / "real-model.onnx"
            target.write_bytes(model.read_bytes())
            model.unlink()
            alias = Path(tmp) / "alias.onnx"
            try:
                alias.symlink_to(target)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symbolic links are unavailable: {exc}")
            data = json.loads(path.read_text(encoding="utf-8"))
            data["model_file"] = "alias.onnx"
            data["model_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ModelManifestError, "symbolic links"):
                load_manifest(path)

    def test_rejects_oversized_manifest_with_bounded_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp)
            path.write_bytes(b" " * 5)
            with patch("camera.model_manifest.MAX_MANIFEST_BYTES", 4):
                with self.assertRaisesRegex(ModelManifestError, "maximum supported size"):
                    load_manifest(path)


    def test_requires_pseudonymous_reviewer_ids(self):
        invalid_ids = (
            "Simon Thomas",
            "simon@example.org",
            "https://example.org/reviewer",
            "reviewer:short",
        )
        for reviewer_id in invalid_ids:
            with self.subTest(field="model", reviewer_id=reviewer_id), tempfile.TemporaryDirectory() as tmp:
                path = self.make(tmp, license_reviewed_by=reviewer_id)
                with self.assertRaisesRegex(ModelManifestError, "reviewer:<opaque-id>"):
                    load_manifest(path)

            with self.subTest(field="dataset-source", reviewer_id=reviewer_id), tempfile.TemporaryDirectory() as tmp:
                source = {
                    "source_url": "https://example.org/dataset",
                    "revision": "a" * 40,
                    "license": "CC-BY-4.0",
                    "license_review_status": "approved",
                    "license_evidence_url": "https://creativecommons.org/licenses/by/4.0/",
                    "training_use_allowed": True,
                    "redistribution_allowed": False,
                    "reviewed_by": reviewer_id,
                    "reviewed_at": "2026-11-20T12:00:00Z",
                }
                path = self.make(tmp, training_data_sources=[source])
                with self.assertRaisesRegex(ModelManifestError, "reviewer:<opaque-id>"):
                    load_manifest(path)

            with self.subTest(field="image", reviewer_id=reviewer_id), tempfile.TemporaryDirectory() as tmp:
                path = self.make(tmp)
                row = self.default_provenance_row()
                row["reviewed_by"] = reviewer_id
                payload = (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")
                self.rewrite_provenance(path, payload)
                with self.assertRaisesRegex(ModelManifestError, "reviewer:<opaque-id>"):
                    load_manifest(path)

    def test_rejects_non_opaque_permission_reference(self):
        invalid_refs = (
            "person@example.org",
            "https://private.example/consent/123",
            "consent record with name",
            "../private-consent",
        )
        for permission_ref in invalid_refs:
            with self.subTest(permission_ref=permission_ref), tempfile.TemporaryDirectory() as tmp:
                path = self.make(tmp)
                data = json.loads(path.read_text(encoding="utf-8"))
                revision = "sha256:" + "c" * 64
                source_url = "local-capture://batch-opaque-0001"
                provenance_row = {
                    "image": "images/sample.jpg",
                    "image_sha256": "a" * 64,
                    "source_url": source_url,
                    "revision": revision,
                    "license": "LicenseRef-ExplicitPermission",
                    "license_review_status": "approved",
                    "training_use_allowed": True,
                    "redistribution_allowed": False,
                    "reviewed_by": "reviewer:image-0001",
                    "reviewed_at": "2026-11-20T12:30:00Z",
                    "permission_ref": permission_ref,
                }
                payload = (json.dumps(provenance_row, sort_keys=True) + "\n").encode("utf-8")
                (Path(tmp) / "provenance.jsonl").write_bytes(payload)
                data["dataset_manifest_sha256"] = hashlib.sha256(payload).hexdigest()
                data["training_data_sources"] = [{
                    "source_url": source_url,
                    "revision": revision,
                    "license": "LicenseRef-ExplicitPermission",
                    "license_review_status": "approved",
                    "license_evidence_url": None,
                    "training_use_allowed": True,
                    "redistribution_allowed": False,
                    "reviewed_by": "reviewer:rights-0001",
                    "reviewed_at": "2026-11-20T12:00:00Z",
                }]
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaisesRegex(ModelManifestError, "opaque permission_ref"):
                    load_manifest(path)

    def test_rejects_private_consent_evidence_url_for_explicit_permission(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = {
                "source_url": "local-capture://batch-opaque-0001",
                "revision": "sha256:" + "c" * 64,
                "license": "LicenseRef-ExplicitPermission",
                "license_review_status": "approved",
                "license_evidence_url": "https://private.example/consent/person-123",
                "training_use_allowed": True,
                "redistribution_allowed": False,
                "reviewed_by": "reviewer:rights-0001",
                "reviewed_at": "2026-11-20T12:00:00Z",
            }
            path = self.make(tmp, training_data_sources=[source])
            with self.assertRaisesRegex(ModelManifestError, "consent URLs or documents"):
                load_manifest(path)

    def test_public_domain_dataset_status_is_reserved_for_cc0(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = {
                "source_url": "https://example.org/dataset",
                "revision": "a" * 40,
                "license": "CC-BY-4.0",
                "license_review_status": "public-domain",
                "license_evidence_url": "https://creativecommons.org/licenses/by/4.0/",
                "training_use_allowed": True,
                "redistribution_allowed": False,
                "reviewed_by": "reviewer:rights-0001",
                "reviewed_at": "2026-11-20T12:00:00Z",
            }
            path = self.make(tmp, training_data_sources=[source])
            with self.assertRaisesRegex(ModelManifestError, "only valid for CC0-1.0"):
                load_manifest(path)

if __name__ == "__main__":
    unittest.main()
