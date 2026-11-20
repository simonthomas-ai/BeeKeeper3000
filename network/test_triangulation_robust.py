import json
import math
import unittest

from network.triangulation import Bearing, triangulate


def bearing_to(lat1, lon1, lat2, lon2):
    east = (lon2 - lon1) * 111_000 * math.cos(math.radians((lat1 + lat2) / 2))
    north = (lat2 - lat1) * 111_000
    return math.degrees(math.atan2(east, north)) % 360


class RobustTriangulationTests(unittest.TestCase):
    def setUp(self):
        self.target = (51.0000, 7.0000)
        self.stations = [
            ("west", 51.0000, 6.9950),
            ("south", 50.9960, 7.0040),
            ("north-east", 51.0050, 7.0060),
            ("south-east", 50.9980, 7.0060),
        ]
        self.bearings = [
            Bearing(
                station_id=name,
                latitude=lat,
                longitude=lon,
                azimuth_deg=bearing_to(lat, lon, *self.target),
                sigma_deg=2.0,
                observed_at="2026-11-20T10:00:00Z",
            )
            for name, lat, lon in self.stations
        ]

    def test_four_station_solution_rejects_one_gross_outlier(self):
        noisy = list(self.bearings)
        outlier = noisy[3]
        noisy[3] = Bearing(
            outlier.station_id, outlier.latitude, outlier.longitude,
            (outlier.azimuth_deg + 25.0) % 360.0, outlier.sigma_deg,
            outlier.observed_at,
        )
        estimate = triangulate(noisy)
        self.assertAlmostEqual(estimate.latitude, self.target[0], places=4)
        self.assertAlmostEqual(estimate.longitude, self.target[1], places=4)
        self.assertEqual(estimate.bearing_count, 3)
        self.assertEqual(estimate.inlier_station_ids, ("west", "south", "north-east"))
        self.assertEqual(estimate.outlier_station_ids, ("south-east",))
        self.assertEqual(estimate.status, "search_hypothesis")

    def test_three_bearings_with_one_gross_outlier_fail_closed(self):
        noisy = list(self.bearings[:3])
        outlier = noisy[2]
        noisy[2] = Bearing(
            outlier.station_id, outlier.latitude, outlier.longitude,
            (outlier.azimuth_deg + 30.0) % 360.0, outlier.sigma_deg,
            outlier.observed_at,
        )
        with self.assertRaises(ValueError):
            triangulate(noisy)

    def test_95_percent_uncertainty_ellipse_and_geojson(self):
        estimate = triangulate(self.bearings)
        self.assertGreater(estimate.uncertainty_major_95_m, 0)
        self.assertGreater(estimate.uncertainty_minor_95_m, 0)
        self.assertGreaterEqual(estimate.uncertainty_major_95_m, estimate.uncertainty_minor_95_m)
        self.assertEqual(len(estimate.ellipse_95_coordinates), 37)
        self.assertEqual(estimate.ellipse_95_coordinates[0], estimate.ellipse_95_coordinates[-1])
        geojson = estimate.to_geojson()
        json.dumps(geojson, allow_nan=False)
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertEqual(geojson["features"][0]["geometry"]["type"], "Point")
        self.assertEqual(geojson["features"][1]["geometry"]["type"], "Polygon")
        self.assertEqual(geojson["features"][1]["properties"]["confidence_level"], 0.95)

    def test_uncertainty_expands_with_larger_angular_error(self):
        exact = triangulate(self.bearings)
        uncertain = [
            Bearing(
                b.station_id, b.latitude, b.longitude, b.azimuth_deg,
                10.0, b.observed_at,
            )
            for b in self.bearings
        ]
        wide = triangulate(uncertain)
        self.assertGreater(wide.uncertainty_major_95_m, exact.uncertainty_major_95_m)
        self.assertGreater(wide.uncertainty_minor_95_m, exact.uncertainty_minor_95_m)

    def test_rejects_non_finite_coordinates_and_bool_values(self):
        with self.assertRaises(ValueError):
            triangulate(self.bearings[:2] + [
                Bearing("bad", float("nan"), 7.0, 90.0, 2.0, "2026-11-20T10:00:00Z")
            ])
        with self.assertRaises(ValueError):
            triangulate(self.bearings[:2] + [
                Bearing("bad", True, 7.0, 90.0, 2.0, "2026-11-20T10:00:00Z")
            ])

    def test_rejects_time_mismatch_and_nonlocal_station_group(self):
        stale = list(self.bearings[:3])
        last = stale[2]
        stale[2] = Bearing(
            last.station_id, last.latitude, last.longitude, last.azimuth_deg,
            last.sigma_deg, "2026-11-20T13:00:00Z",
        )
        with self.assertRaises(ValueError):
            triangulate(stale, max_time_delta_sec=1800)

        distant = [
            self.bearings[0],
            self.bearings[1],
            Bearing("far", 51.5, 7.0, 270.0, 2.0, "2026-11-20T10:00:00Z"),
        ]
        with self.assertRaises(ValueError):
            triangulate(distant)

    def test_rejects_unstable_geometry_and_invalid_consensus(self):
        parallel = [
            Bearing("p1", 51.0, 7.0, 90, 2, "2026-11-20T10:00:00Z"),
            Bearing("p2", 51.001, 7.001, 90, 2, "2026-11-20T10:00:00Z"),
            Bearing("p3", 51.002, 7.002, 90, 2, "2026-11-20T10:00:00Z"),
        ]
        with self.assertRaises(ValueError):
            triangulate(parallel)
        with self.assertRaises(ValueError):
            triangulate(self.bearings, consensus_sigma=50)


if __name__ == "__main__":
    unittest.main()
