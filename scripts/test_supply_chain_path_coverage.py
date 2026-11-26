"""Ensure supply-chain audits run when training/provenance scope changes."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "supply-chain.yml"
REGISTER = ROOT / "SUPPLY_CHAIN.md"


class SupplyChainPathCoverageTests(unittest.TestCase):
    def test_push_and_pull_request_cover_training_code_lockfiles_and_register(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        push = text.split("  push:\n", 1)[1].split("  pull_request:\n", 1)[0]
        pull_request = text.split("  pull_request:\n", 1)[1].split("  workflow_dispatch:\n", 1)[0]
        required = (
            "training/**/*.py",
            "training/requirements*.txt",
            "training/**/*.lock",
            "SUPPLY_CHAIN.md",
        )
        for name, section in (("push", push), ("pull_request", pull_request)):
            for pattern in required:
                with self.subTest(event=name, pattern=pattern):
                    self.assertIn(f'- "{pattern}"', section)

    def test_register_documents_every_audited_python_runtime_surface(self):
        text = REGISTER.read_text(encoding="utf-8")
        for path in (
            "network/meshcore/requirements.lock",
            "adapters/nmea-requirements.lock",
            "camera/requirements.txt",
            "training/requirements-training.txt",
        ):
            with self.subTest(path=path):
                self.assertIn(path, text)
        self.assertIn("not a complete resolved environment inventory", text)
        self.assertIn("no provenance attestation", text.lower())


if __name__ == "__main__":
    unittest.main()
