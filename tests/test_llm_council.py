import datetime as dt
import unittest
from pathlib import Path

from tools.llm_council import CouncilError, scrub_prompt, validate_external_provider, validate_local_url


class CouncilSafetyTests(unittest.TestCase):
    def test_zero_cost_external_requires_hard_cap(self):
        p = {
            "enabled": True, "free_access_verified": True,
            "provider_enforced_hard_cap_eur": None,
            "terms_reviewed_on": dt.date.today().isoformat(),
            "base_url": "https://example.org/v1", "provider_type": "openai_compatible", "model": "model"
        }
        self.assertIn("hard spending cap", validate_external_provider(p, dt.date.today()))

    def test_boolean_is_not_accepted_as_zero_budget(self):
        from tools.llm_council import run
        with self.assertRaises(CouncilError):
            run({"budget_eur": False}, "safe prompt", __import__("pathlib").Path("unused-test-output"))

    def test_boolean_is_not_accepted_as_provider_cap(self):
        p = {"enabled": True, "free_access_verified": True, "provider_enforced_hard_cap_eur": False, "terms_reviewed_on": dt.date.today().isoformat(), "base_url": "https://example.org/v1", "provider_type": "openai_compatible", "model": "model"}
        self.assertIn("hard spending cap", validate_external_provider(p, dt.date.today()))

    def test_external_provider_requires_recent_terms_review(self):
        p = {
            "enabled": True, "free_access_verified": True,
            "provider_enforced_hard_cap_eur": 0,
            "terms_reviewed_on": "2020-01-01",
            "base_url": "https://example.org/v1", "provider_type": "openai_compatible", "model": "model"
        }
        self.assertIn("older than 30 days", validate_external_provider(p, dt.date.today()))

    def test_external_provider_requires_https(self):
        p = {
            "enabled": True, "free_access_verified": True,
            "provider_enforced_hard_cap_eur": 0,
            "terms_reviewed_on": dt.date.today().isoformat(),
            "base_url": "http://example.org/v1", "provider_type": "openai_compatible", "model": "model"
        }
        self.assertIn("HTTPS", validate_external_provider(p, dt.date.today()))

    def test_local_provider_must_be_loopback(self):
        with self.assertRaises(CouncilError):
            validate_local_url("http://example.org:11434/v1")
        validate_local_url("http://127.0.0.1:11434/v1")

    def test_prompt_secrets_are_blocked(self):
        with self.assertRaises(CouncilError):
            scrub_prompt("api_key=supersecretvalue")

    def test_prompt_size_is_bounded(self):
        with self.assertRaises(CouncilError):
            scrub_prompt("x" * 100_001)




class CouncilWorkflowIsolationTests(unittest.TestCase):
    def test_self_hosted_council_only_runs_from_main(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github" / "workflows" / "llm-council.yml").read_text(encoding="utf-8")
        self.assertIn(
            "if: github.repository == 'simonthomas-ai/BeeKeeper3000' && github.ref == 'refs/heads/main'",
            workflow,
        )
        self.assertIn("runs-on: [self-hosted, windows, x64, llm-council]", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertNotIn("pull_request:", workflow)


if __name__ == "__main__":
    unittest.main()
