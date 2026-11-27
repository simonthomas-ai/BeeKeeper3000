"""Regression tests for the public supply-chain artifact exposure policy."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "supply-chain.yml"


def upload_step_blocks():
    source = WORKFLOW.read_text(encoding="utf-8")
    starts = list(re.finditer(r"(?m)^      - name: Upload [^\n]+\n", source))
    blocks = []
    for match in starts:
        next_step = re.search(r"(?m)^      - name: ", source[match.end():])
        end = match.end() + next_step.start() if next_step else len(source)
        blocks.append(source[match.start():end])
    return blocks


class SupplyChainArtifactPolicyTests(unittest.TestCase):
    def test_all_uploads_are_short_lived(self):
        blocks = upload_step_blocks()
        self.assertEqual(len(blocks), 6)
        for block in blocks:
            with self.subTest(step=block.splitlines()[0]):
                self.assertRegex(block, r"(?m)^\s+retention-days: 7\s*$")
                self.assertNotRegex(block, r"(?m)^\s+retention-days: (?:[8-9]|[1-9][0-9]+)\s*$")

    def test_public_artifacts_are_main_or_manual_only(self):
        for block in upload_step_blocks():
            with self.subTest(step=block.splitlines()[0]):
                self.assertIn("github.ref == 'refs/heads/main'", block)
                self.assertIn("github.event_name == 'workflow_dispatch'", block)
                self.assertNotIn("github.event_name != 'pull_request'", block)
                if "vulnerability report" in block:
                    self.assertIn("always()", block)

    def test_artifact_paths_are_report_only(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        for block in upload_step_blocks():
            with self.subTest(step=block.splitlines()[0]):
                self.assertIn("reports/", block)
                for forbidden in (
                    "datasets/", "models/", ".onnx", ".pt", ".jpg", ".jpeg",
                    ".png", ".mp4", ".mov", ".wav", "camera.env", "station.env",
                ):
                    self.assertNotIn(forbidden, block.lower())
        self.assertIn("permissions:\n  contents: read", source)


if __name__ == "__main__":
    unittest.main()
