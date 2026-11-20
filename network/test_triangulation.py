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


if __name__ == "__main__":
    unittest.main()
