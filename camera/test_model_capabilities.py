"""Regression checks for the inventory, not model validation."""
import json
import re
import unittest
from pathlib import Path


class ModelCapabilitiesTest(unittest.TestCase):
    def test_inventory_cannot_enable_inference(self):
        data = json.loads(Path(__file__).with_name("model-capabilities.json").read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        ids = [entry["id"] for entry in data["capabilities"]]
        self.assertCountEqual(ids, ["hornet_species", "bee_species", "varroa", "queen",
                                    "swarm_visual", "swarm_audio", "hive_audio", "flight_activity"])
        for entry in data["capabilities"]:
            self.assertIs(entry["enabled"], False)
            self.assertIsNone(entry["model"])
            self.assertEqual(entry["status"], "not_validated")
        candidates = data["candidates"]
        self.assertEqual(len({c["id"] for c in candidates}), len(candidates))
        for candidate in candidates:
            self.assertIn(candidate["capability"], ids)
            self.assertIs(candidate["enabled"], False)
            self.assertEqual(candidate["status"], "rights_and_runtime_pending")
            self.assertTrue(re.fullmatch(r"[0-9a-f]{40}", candidate["revision"]))
            self.assertTrue(candidate["source"].startswith("https://github.com/"))


if __name__ == "__main__":
    unittest.main()
