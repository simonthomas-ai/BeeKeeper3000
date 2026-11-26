"""Keep the training runtime pins and supply-chain audit in sync."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TRAINER = ROOT / "training" / "train_multilabel.py"
REQUIREMENTS = ROOT / "training" / "requirements-training.txt"
SUPPLY_CHAIN = ROOT / ".github" / "workflows" / "supply-chain.yml"
QUALITY_GATES = ROOT / ".github" / "workflows" / "quality-gates.yml"

REQUIRED = {
    "Pillow": "13.0.0",
    "onnx": "1.23.2",
    "torch": "2.15.0",
}


class TrainingDependencyContractTests(unittest.TestCase):
    def test_direct_pins_match_the_trainer_runtime_contract(self):
        requirements = REQUIREMENTS.read_text(encoding="utf-8")
        trainer = TRAINER.read_text(encoding="utf-8")
        for package, version in REQUIRED.items():
            with self.subTest(package=package):
                self.assertIn(f"{package}=={version}", requirements)
                self.assertIn(f'"{version}"', trainer)

    def test_supply_chain_audits_and_emits_training_dependency_evidence(self):
        workflow = SUPPLY_CHAIN.read_text(encoding="utf-8")
        self.assertIn(
            "pip-audit --requirement training/requirements-training.txt --strict",
            workflow,
        )
        self.assertIn(
            "cyclonedx-py requirements training/requirements-training.txt",
            workflow,
        )
        self.assertIn("training-runtime-audit.json", workflow)
        self.assertIn("training-declared-requirements.cdx.json", workflow)

    def test_required_quality_gates_run_this_contract_test(self):
        workflow = QUALITY_GATES.read_text(encoding="utf-8")
        self.assertIn(
            "python -m unittest scripts.test_training_dependency_contract -v",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
