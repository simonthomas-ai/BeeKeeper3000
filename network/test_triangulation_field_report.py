import csv
import math
import tempfile
import unittest
from pathlib import Path

from network.triangulation_field_report import (
    REQUIRED_COLUMNS,
    FieldReportError,
    _ellipse_contains,
    _initial_bearing_deg,
    _wilson_interval,
    build_report,
    report_csv,
)
from network.triangulation import Bearing, triangulate


def destination(lat, lon, distance_m, bearing_deg):
    angle = math.radians(bearing_deg)
    north = distance_m * math.cos(angle)
    east = distance_m * math.sin(angle)
    target_lat = lat + math.degrees(north / 6_371_000.0)
    target_lon = lon + math.degrees(east / (6_371_000.0 * math.cos(math.radians(lat))))
    return target_lat, target_lon


def trial_rows(trial_id, target=(51.0, 7.0), angular_noise=0.0, time="2026-11-20T10:00:00Z"):
    stations = [
        (51.0000, 6.9950),
        (50.9960, 7.0040),
        (51.0050, 7.0060),
        (51.0040, 6.9910),
    ]
    rows = []
    for index, (lat, lon) in enumerate(stations):
        true_bearing = _initial_bearing_deg(lat, lon, *target)
        rows.append({
            "trial_id": trial_id,
            "station_id": f"station-{index}",
            "station_latitude": str(lat),
            "station_longitude": str(lon),
            "azimuth_deg": str((true_bearing + angular_noise) % 360.0),
            "sigma_deg": "2.0",
            "observed_at": time,
            "target_latitude": str(target[0]),
            "target_longitude": str(target[1]),
        })
    return rows


def write_csv(path, rows, header=REQUIRED_COLUMNS):
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


class FieldReportTests(unittest.TestCase):
    def test_known_target_trial_is_evaluated_without_coordinates_in_report(self):
        rows = trial_rows("trial-01")
        trials = {
            "trial-01": [
                Bearing(
                    station_id=row["station_id"],
                    latitude=float(row["station_latitude"]),
                    longitude=float(row["station_longitude"]),
                    azimuth_deg=float(row["azimuth_deg"]),
                    sigma_deg=float(row["sigma_deg"]),
                    observed_at=row["observed_at"],
                )
                for row in rows
            ]
        }
        report = build_report(trials, {"trial-01": (51.0, 7.0)}, minimum_trials=1)
        self.assertEqual(report["status"], "enough_samples_for_expert_review_only")
        self.assertEqual(report["decision"], "not_approved_for_operational_use")
        self.assertEqual(report["successful_estimates"], 1)
        self.assertLess(report["trials"][0]["ground_truth_error_m"], 1.0)
        self.assertTrue(report["trials"][0]["ellipse_95_contains_target"])
        self.assertFalse(report["privacy"]["coordinates_in_report"])
        self.assertNotIn("latitude", str(report).lower())
        self.assertIn("station-0", report["station_angular_calibration"])

    def test_fewer_than_minimum_trials_is_insufficient(self):
        trial = trial_rows("trial-01")
        bearings = [
            Bearing(r["station_id"], float(r["station_latitude"]), float(r["station_longitude"]),
                    float(r["azimuth_deg"]), float(r["sigma_deg"]), r["observed_at"])
            for r in trial
        ]
        report = build_report({"trial-01": bearings}, {"trial-01": (51.0, 7.0)}, minimum_trials=30)
        self.assertEqual(report["status"], "insufficient_trials")
        self.assertEqual(report["decision"], "not_approved_for_operational_use")

    def test_solver_failure_is_counted(self):
        bad = [
            Bearing("station-a", 51.0, 7.0, 90.0, 2.0, "2026-11-20T10:00:00Z"),
            Bearing("station-b", 51.001, 7.001, 90.0, 2.0, "2026-11-20T10:00:00Z"),
            Bearing("station-c", 51.002, 7.002, 90.0, 2.0, "2026-11-20T10:00:00Z"),
        ]
        report = build_report({"bad-trial": bad}, {"bad-trial": (51.0, 7.01)}, minimum_trials=1)
        self.assertEqual(report["solver_failures"], 1)
        self.assertEqual(report["status"], "calibration_review_required")

    def test_circular_bias_handles_north_wraparound(self):
        rows = trial_rows("trial-01", target=(51.0, 7.0), angular_noise=1.5)
        trials = {
            "trial-01": [
                Bearing(r["station_id"], float(r["station_latitude"]), float(r["station_longitude"]),
                        float(r["azimuth_deg"]), float(r["sigma_deg"]), r["observed_at"])
                for r in rows
            ]
        }
        report = build_report(trials, {"trial-01": (51.0, 7.0)}, minimum_trials=1)
        for stats in report["station_angular_calibration"].values():
            self.assertAlmostEqual(stats["circular_bias_deg"], 1.5, places=2)

    def test_csv_requires_exact_header_and_no_missing_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            write_csv(path, trial_rows("trial-01"), header=("trial_id", "station_id"))
            with self.assertRaises(FieldReportError):
                report_csv(path)

    def test_csv_rejects_target_mismatch_inside_trial(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mismatch.csv"
            rows = trial_rows("trial-01")
            rows[1]["target_latitude"] = "51.1"
            write_csv(path, rows)
            with self.assertRaises(FieldReportError):
                report_csv(path)

    def test_csv_report_does_not_emit_station_or_target_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "known-targets.csv"
            write_csv(path, trial_rows("trial-01"))
            report = report_csv(path, minimum_trials=1)
            text = str(report)
            self.assertNotIn("51.0", text)
            self.assertNotIn("6.995", text)

    def test_wilson_interval_edges(self):
        self.assertIsNone(_wilson_interval(0, 0))
        low, high = _wilson_interval(30, 30)
        self.assertLess(low, 1.0)
        self.assertEqual(high, 1.0)


if __name__ == "__main__":
    unittest.main()
