import math
import unittest

from network.triangulation import Bearing, triangulate


def bearing_to(lat1, lon1, lat2, lon2):
    # Local east/north approximation is sufficient for these synthetic tests.
    east = (lon2 - lon1) * 111_000 * math.cos(math.radians((lat1 + lat2) / 2))
    north = (lat2 - lat1) * 111_000
    return math.degrees(math.atan2(east, north)) % 360


class TriangulationTests(unittest.TestCase):
    def setUp(self):
        self.target = (51.0000, 7.0000)
        stations = [(51.0000, 6.9950), (50.9960, 7.0040), (51.0050, 7.0060)]
        self.bearings = [
            Bearing(f"station-{i}", lat, lon,
                    bearing_to(lat, lon, *self.target), 2.0,
                    "2026-11-20T10:00:00Z")
            for i, (lat, lon) in enumerate(stations)
        ]

    def test_known_target(self):
        result = triangulate(self.bearings)
        self.assertAlmostEqual(result.latitude, self.target[0], places=4)
        self.assertAlmostEqual(result.longitude, self.target[1], places=4)
        self.assertEqual(result.bearing_count, 3)
        self.assertEqual(result.status, "search_hypothesis")

    def test_requires_three_stations(self):
        with self.assertRaises(ValueError):
            triangulate(self.bearings[:2])

    def test_rejects_parallel_bearings(self):
        parallel = [
            Bearing("a", 51.0, 7.0, 90.0, 2.0),
            Bearing("b", 51.001, 7.001, 90.0, 2.0),
            Bearing("c", 51.002, 7.002, 90.0, 2.0),
        ]
        with self.assertRaises(ValueError):
            triangulate(parallel)

    def test_rejects_duplicate_station(self):
        dup = [self.bearings[0], self.bearings[0], self.bearings[2]]
        with self.assertRaises(ValueError):
            triangulate(dup)

    def test_rejects_bad_uncertainty(self):
        bad = [self.bearings[0], self.bearings[1],
               Bearing("c", 51.0, 7.01, 20.0, 0.1)]
        with self.assertRaises(ValueError):
            triangulate(bad)


    def test_estimate_reports_95_percent_uncertainty_ellipse(self):
        result = triangulate(self.bearings)
        self.assertGreater(result.ellipse_major_95_m, 0)
        self.assertGreater(result.ellipse_minor_95_m, 0)
        self.assertGreaterEqual(result.ellipse_major_95_m, result.ellipse_minor_95_m)
        self.assertTrue(0 <= result.ellipse_bearing_deg < 180)
        self.assertGreaterEqual(result.rms_angular_error_deg, 0)
        self.assertEqual(set(result.inlier_station_ids), {b.station_id for b in self.bearings})
        self.assertEqual(result.rejected_station_ids, ())

    def test_rejects_boolean_nan_and_infinite_measurements(self):
        invalid = [
            Bearing("station-a", True, 7.0, 10.0, 2.0, "2026-11-20T10:00:00Z"),
            Bearing("station-b", 51.0, float("nan"), 10.0, 2.0, "2026-11-20T10:00:00Z"),
            Bearing("station-c", 51.0, 7.0, float("inf"), 2.0, "2026-11-20T10:00:00Z"),
        ]
        with self.assertRaises(ValueError):
            triangulate(invalid)

    def test_rejects_invalid_option_types_and_values(self):
        with self.assertRaises(ValueError):
            triangulate(self.bearings, max_rms_error_m=float("nan"))
        with self.assertRaises(ValueError):
            triangulate(self.bearings, max_outliers=True)
        with self.assertRaises(ValueError):
            triangulate(self.bearings, max_time_delta_sec=True)

    def test_rejects_timestamps_outside_window(self):
        values = list(self.bearings)
        values[0] = Bearing(
            values[0].station_id, values[0].latitude, values[0].longitude,
            values[0].azimuth_deg, values[0].sigma_deg,
            "2026-11-20T09:00:00Z",
        )
        with self.assertRaises(ValueError):
            triangulate(values, max_time_delta_sec=300)

    def test_single_gross_outlier_is_identified_without_failing_closed(self):
        target = (51.0, 7.0)
        stations = [
            (51.0000, 6.9900),
            (50.9920, 6.9980),
            (51.0040, 7.0100),
            (51.0100, 6.9950),
            (50.9900, 7.0120),
        ]
        observations = []
        for index, (lat, lon) in enumerate(stations):
            angle = bearing_to(lat, lon, *target)
            if index == 4:
                angle = (angle + 30.0) % 360.0
            observations.append(Bearing(
                "station-{}".format(index), lat, lon, angle, 1.5,
                "2026-11-20T10:00:00Z",
            ))

        result = triangulate(observations, max_outliers=1, outlier_sigma=4.0)
        self.assertEqual(result.bearing_count, 4)
        self.assertIn("station-4", result.rejected_station_ids)
        self.assertLess(abs(result.latitude - target[0]), 0.0005)
        self.assertLess(abs(result.longitude - target[1]), 0.0005)
        self.assertEqual(result.status, "search_hypothesis")

    def test_three_station_solution_fails_closed_for_gross_outlier(self):
        values = list(self.bearings)
        bad = values[2]
        values[2] = Bearing(
            bad.station_id, bad.latitude, bad.longitude,
            (bad.azimuth_deg + 30.0) % 360.0, bad.sigma_deg, bad.observed_at,
        )
        with self.assertRaises(ValueError):
            triangulate(values, max_outliers=0)

    def test_rejects_stations_outside_local_projection_area(self):
        far = list(self.bearings)
        far[2] = Bearing(
            "station-far", 51.5, 7.0, 180.0, 2.0, "2026-11-20T10:00:00Z"
        )
        with self.assertRaises(ValueError):
            triangulate(far, max_area_m=30_000.0)



if __name__ == "__main__":
    unittest.main()
