import unittest
from datetime import datetime, timezone
from camera.contracts import Detection, make_source_event


class DetectionContractTests(unittest.TestCase):
    def test_metadata_only_source_event(self):
        event = make_source_event(station_id="station-01", detection=Detection("vespa_velutina_candidate", 0.93), observed_at=datetime(2026, 11, 20, tzinfo=timezone.utc))
        self.assertEqual(set(event), {"id", "observed_at", "station_id", "species", "confidence", "prey_detected", "origin"})
        self.assertTrue(event["id"].startswith("camera-"))
        self.assertTrue(event["observed_at"].endswith("Z"))
        self.assertEqual(event["origin"], "camera")
        self.assertEqual(event["species"], "vespa_velutina_candidate")

    def test_rejects_invalid_confidence_and_station_id(self):
        with self.assertRaises(ValueError):
            make_source_event(station_id="bad id", detection=Detection("hornet", 0.5))
        with self.assertRaises(ValueError):
            make_source_event(station_id="station-01", detection=Detection("hornet", float("nan")))


if __name__ == "__main__":
    unittest.main()
