import math
import unittest
from dataclasses import replace

from network.geojson import estimate_to_geojson
from network.triangulation import Bearing, Estimate, triangulate


def bearing_to(lat1, lon1, lat2, lon2):
    east = (lon2 - lon1) * 111_000 * math.cos(math.radians((lat1 + lat2) / 2))
    north = (lat2 - lat1) * 111_000
    return math.degrees(math.atan2(east, north)) % 360


class GeoJsonExportTests(unittest.TestCase):
    def setUp(self):
        target = (51.0, 7.0)
        stations = [(51.000, 6.995), (50.996, 7.004), (51.005, 7.006)]
        bearings = [
            Bearing(
                f"station-{index}", lat, lon,
                bearing_to(lat, lon, *target), 2.0,
                "2026-11-22T10:00:00Z",
            )
            for index, (lat, lon) in enumerate(stations)
        ]
        self.estimate = triangulate(bearings)

    def test_exports_point_and_closed_95_percent_polygon(self):
        result = estimate_to_geojson(self.estimate)
        self.assertEqual(result["type"], "FeatureCollection")
        self.assertEqual(len(result["features"]), 2)

        point, ellipse = result["features"]
        self.assertEqual(point["geometry"]["type"], "Point")
        self.assertEqual(point["geometry"]["coordinates"], [7.0, 51.0])
        self.assertEqual(ellipse["geometry"]["type"], "Polygon")
        ring = ellipse["geometry"]["coordinates"][0]
        self.assertEqual(len(ring), 73)
        self.assertEqual(ring[0], ring[-1])
        self.assertEqual(ellipse["properties"]["confidence_level"], 0.95)
        self.assertEqual(ellipse["properties"]["status"], "search_hypothesis")
        self.assertTrue(ellipse["properties"]["approximation_only"])
        self.assertIn("Search hypothesis only", ellipse["properties"]["operational_notice"])

    def test_export_uses_geojson_longitude_latitude_order_and_wraps_dateline(self):
        estimate = replace(self.estimate, longitude=179.9999, ellipse_major_95_m=500,
                           ellipse_minor_95_m=100, ellipse_bearing_deg=90.0)
        result = estimate_to_geojson(estimate, vertices=24)
        point = result["features"][0]["geometry"]["coordinates"]
        self.assertAlmostEqual(point[0], 179.9999, places=7)
        self.assertAlmostEqual(point[1], 51.0, places=7)
        ring = result["features"][1]["geometry"]["coordinates"][0]
        self.assertTrue(any(lon < -179.9 for lon, lat in ring))
        self.assertTrue(all(-180 <= lon <= 180 and -90 <= lat <= 90 for lon, lat in ring))

    def test_rejects_confirmed_or_changed_status(self):
        with self.assertRaisesRegex(ValueError, "only provisional"):
            estimate_to_geojson(replace(self.estimate, status="expert_confirmed"))

    def test_rejects_invalid_ellipse_and_vertex_count(self):
        with self.assertRaisesRegex(ValueError, "axes"):
            estimate_to_geojson(replace(self.estimate, ellipse_major_95_m=0))
        with self.assertRaises(ValueError):
            estimate_to_geojson(self.estimate, vertices=8)

    def test_rejects_invalid_station_metadata(self):
        with self.assertRaises(ValueError):
            estimate_to_geojson(replace(self.estimate, bearing_count=2))


if __name__ == "__main__":
    unittest.main()
