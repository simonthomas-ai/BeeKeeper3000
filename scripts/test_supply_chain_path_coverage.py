"""Ensure supply-chain audits run when training/provenance code changes."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "supply-chain.yml"


class SupplyChainPathCoverageTests(unittest.TestCase):
    def test_push_and_pull_request_cover_training_code_and_lockfiles(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        push = text.split("  push:\n", 1)[1].split("  pull_request:\n", 1)[0]
        pull_request = text.split("  pull_request:\n", 1)[1].split("  workflow_dispatch:\n", 1)[0]
        required = (
            "training/**/*.py",
            "training/requirements*.txt",
            "training/**/*.lock",
        )
        for name, section in (("push", push), ("pull_request", pull_request)):
            for pattern in required:
                with self.subTest(event=name, pattern=pattern):
                    self.assertIn(f'- "{pattern}"', section)


if __name__ == "__main__":
    unittest.main()
