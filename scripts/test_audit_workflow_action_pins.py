"""Regression tests for immutable Actions pins, image digests and checkout credentials."""
import unittest
from pathlib import Path

from scripts.audit_workflow_action_pins import (
    find_checkout_steps_without_persist_credentials,
    find_permission_policy_violations,
    find_unpinned_actions,
    find_unpinned_images,
)


class ActionPinTests(unittest.TestCase):
    def test_accepts_full_commit_sha_with_version_comment(self):
        text = "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1"
        self.assertEqual(find_unpinned_actions(text), [])

    def test_rejects_major_tag(self):
        text = "      - uses: actions/checkout@v7"
        self.assertEqual(len(find_unpinned_actions(text)), 1)

    def test_rejects_short_commit_reference(self):
        text = "      - uses: owner/action@abcdef123456"
        self.assertEqual(len(find_unpinned_actions(text)), 1)

    def test_accepts_local_action_path(self):
        text = "      - uses: ./.github/actions/my-action"
        self.assertEqual(find_unpinned_actions(text), [])

    def test_requires_docker_action_digest(self):
        mutable = "      - uses: docker://ghcr.io/example/action:latest"
        immutable = "      - uses: docker://ghcr.io/example/action@sha256:" + "a" * 64
        self.assertEqual(len(find_unpinned_actions(mutable)), 1)
        self.assertEqual(find_unpinned_actions(immutable), [])

    def test_ignores_action_comments_and_run_lines(self):
        text = "# uses: actions/checkout@v4\n      - run: echo done"
        self.assertEqual(find_unpinned_actions(text), [])

    def test_accepts_container_image_with_oci_digest(self):
        text = "      image: mcr.microsoft.com/playwright:v1.65.1-noble@sha256:" + "b" * 64
        self.assertEqual(find_unpinned_images(text), [])

    def test_rejects_container_image_tag_without_digest(self):
        text = "      image: mcr.microsoft.com/playwright:v1.65.1-noble"
        self.assertEqual(len(find_unpinned_images(text)), 1)

    def test_accepts_quoted_container_image_digest(self):
        text = "      image: 'ghcr.io/example/test:2.0@sha256:" + "c" * 64 + "'"
        self.assertEqual(find_unpinned_images(text), [])

    def test_ignores_image_comments_and_run_lines(self):
        text = "# image: ubuntu:latest\n      - run: echo done"
        self.assertEqual(find_unpinned_images(text), [])


class CheckoutCredentialTests(unittest.TestCase):
    def test_accepts_named_checkout_with_persist_credentials_false(self):
        text = (
            "    steps:\n"
            "      - name: Checkout\n"
            "        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n"
            "        with:\n"
            "          persist-credentials: false\n"
            "          repository: owner/repo\n"
        )
        self.assertEqual(find_checkout_steps_without_persist_credentials(text), [])

    def test_rejects_checkout_without_explicit_false(self):
        text = (
            "    steps:\n"
            "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n"
        )
        problems = find_checkout_steps_without_persist_credentials(text, "fixture.yml")
        self.assertEqual(len(problems), 1)
        self.assertIn("persist-credentials: false", problems[0])

    def test_rejects_checkout_when_persist_credentials_is_true(self):
        text = (
            "    steps:\n"
            "      - name: Checkout\n"
            "        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n"
            "        with:\n"
            "          persist-credentials: true\n"
        )
        self.assertEqual(len(find_checkout_steps_without_persist_credentials(text)), 1)

    def test_ignores_non_checkout_steps(self):
        text = (
            "    steps:\n"
            "      - name: Setup\n"
            "        uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0\n"
        )
        self.assertEqual(find_checkout_steps_without_persist_credentials(text), [])


class WaspinatorMetadataAuditTests(unittest.TestCase):
    def test_metadata_audit_pins_exact_source_snapshot(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "waspinator-metadata-audit.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("7251be99a69dfc38f82abb062e22a0062ff5c58c", workflow)
        self.assertIn(
            "models/yolo26n-waspinator-chamber_ncnn_model/model.ncnn.bin",
            workflow,
        )
        self.assertIn("EXPECTED_SIZE: '9602112'", workflow)
        self.assertIn(
            "EXPECTED_GIT_BLOB: 19b5fb51fd63a09e4a74b2f4469bf399e21792bf",
            workflow,
        )
        self.assertIn('entry.get("size") != expected_size', workflow)
        self.assertIn('entry.get("sha") != expected_git_blob', workflow)

    def test_metadata_audit_never_retrieves_or_publishes_model_bytes(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "waspinator-metadata-audit.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("No model weight bytes are downloaded or read.", workflow)
        self.assertNotIn("raw.githubusercontent.com", workflow)
        self.assertNotIn("hashlib", workflow)
        self.assertIn("No SHA-256 is computed.", workflow)
        self.assertIn("Git blob ID is not a SHA-256 digest", workflow)
        self.assertNotIn("actions/upload-artifact", workflow)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", workflow)
        self.assertIn('"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"]', workflow)
        self.assertNotIn("secrets.", workflow)

    def test_upstream_tree_audit_is_metadata_only_and_does_not_publish_artifacts(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "waspinator-upstream-audit.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("https://api.github.com/repos/", workflow)
        self.assertIn("/git/trees/", workflow)
        self.assertIn("No model weights were downloaded or executed.", workflow)
        self.assertNotIn("raw.githubusercontent.com", workflow)
        self.assertNotIn("download_url", workflow)
        self.assertNotIn("actions/download-artifact", workflow)
        self.assertNotIn("actions/upload-artifact", workflow)
        self.assertIn("GITHUB_STEP_SUMMARY", workflow)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", workflow)
        self.assertIn('"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"]', workflow)

    def test_old_weight_downloader_is_removed(self):
        old = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "waspinator-weight-sha256.yml"
        )
        self.assertFalse(old.exists())


class WorkflowPermissionTests(unittest.TestCase):
    def test_accepts_workflow_level_read_only_permissions(self):
        text = """name: test
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps: []
"""
        self.assertEqual(find_permission_policy_violations(text), [])

    def test_accepts_job_level_permissions_when_workflow_level_is_absent(self):
        text = """name: test
jobs:
  build:
    permissions:
      contents: read
    runs-on: ubuntu-latest
    steps: []
"""
        self.assertEqual(find_permission_policy_violations(text), [])

    def test_rejects_workflow_without_explicit_permissions(self):
        text = """name: test
jobs:
  build:
    runs-on: ubuntu-latest
    steps: []
"""
        self.assertTrue(find_permission_policy_violations(text))

    def test_rejects_write_all_permissions(self):
        text = """name: test
permissions: write-all
jobs:
  build:
    runs-on: ubuntu-latest
    steps: []
"""
        self.assertTrue(find_permission_policy_violations(text))

    def test_rejects_job_write_all_override_even_with_read_only_workflow_default(self):
        text = """name: test
permissions:
  contents: read
jobs:
  build:
    permissions: write-all
    runs-on: ubuntu-latest
    steps: []
"""
        self.assertTrue(find_permission_policy_violations(text))

    def test_every_repository_workflow_declares_explicit_permissions(self):
        root = Path(__file__).resolve().parents[1]
        for path in sorted((root / ".github" / "workflows").glob("*.y*ml")):
            with self.subTest(workflow=path.name):
                self.assertEqual(
                    find_permission_policy_violations(path.read_text(encoding="utf-8"), str(path)),
                    [],
                )


if __name__ == "__main__":
    unittest.main()
