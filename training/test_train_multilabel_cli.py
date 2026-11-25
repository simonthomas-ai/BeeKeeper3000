"""Package-mode CLI smoke tests; they never load a dataset or model weights."""
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TrainingModuleCliTests(unittest.TestCase):
    def _help(self, module, expected):
        result = subprocess.run(
            [sys.executable, "-m", module, "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(expected, result.stdout)

    def test_dataset_validator_runs_as_package_module(self):
        self._help("training.multilabel_dataset", "--dataset")

    def test_trainer_runs_as_package_module_without_loading_runtime(self):
        self._help("training.train_multilabel", "--output-dir")


if __name__ == "__main__":
    unittest.main()
