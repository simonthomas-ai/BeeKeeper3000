""""Regression tests for the fail-closed branch-protection helper."""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "Set-VespaGuardBranchProtection.ps1"
SOURCE = SCRIPT.read_text(encoding="utf-8")


def required_checks(repository: str) -> set[str]:
    pattern = (
        rf'Repository = "\\$Owner/{re.escape(repository)}"\\s+'
        r"RequiredChecks = @\\((.*?)\\n\\s+\\)\\s+\\}"
    )
    match = re.search(pattern, SOURCE, re.DOTALL)
    if not match:
        raise AssertionError(f"Missing branch-protection policy for {repository}")
    return set(re.findall(r'^\\s*"([^"]+)"', match.group(1), re.MULTILINE))


class BranchProtectionPolicyTests(unittest.TestCase):
    def test_monitor_requires_every_unconditional_pr_gate(self):
        self.assertEqual(
            required_checks("Beekeeper-Monitor"),
            {
                "gesamttest",
                "Field-Dataset-Export gegen BeeKeeper-Validator",
                "BeeKeeper3000 $([char]0x2013) Bridge-Integration",
                "Analyze source (python)",
                "Analyze source (javascript-typescript)",
            },
        )

    def test_beekeeper_requires_always_on_quality_and_codeql_gates(self):
        self.assertEqual(
            required_checks("BeeKeeper3000"),
            {
                "Python core and safety tests",
                "Camera runtime safety tests",
                "Windows camera runtime compatibility tests",
                "Monitor bridge tests",
                "Analyze source (python)",
                "Analyze source (javascript-typescript)",
            },
        )

    def test_read_only_preflight_checks_current_main_status_before_any_write(self):
        self.assertIn('commits/$headSha/check-runs?per_page=100', SOURCE)
        self.assertIn("Assert-RequiredChecksAvailable -Repository $repository -RequiredChecks $contexts", SOURCE)
        self.assertIn('if ($latest.status -ne "completed" -or $latest.conclusion -ne "success")', SOURCE)

    def test_apply_is_opt_in_and_dry_run_returns_before_put(self):
        dry_run = SOURCE.index("if (-not $Apply)")
        put = SOURCE.index('"--method", "PUT"')
        self.assertLess(dry_run, put)
        self.assertIn("DRY RUN ONLY. No repository settings were changed.", SOURCE)

    def test_unreadable_existing_protection_fails_closed(self):
        self.assertIn("Cannot safely read current branch protection", SOURCE)
        self.assertIn("Existing branch protection is already configured", SOURCE)
        self.assertIn("refuses to overwrite or weaken an existing policy", SOURCE)


if __name__ == "__main__":
    unittest.main()
