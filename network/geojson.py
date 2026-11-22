"""GeoJSON export for triangulation search hypotheses.

The polygon is the solver's local linearized 95% uncertainty ellipse. It is
not a legal boundary, a nest confirmation or a guarantee of target containment.
"""
from __future__ import annotations

from math import cos, isfinite, pi, radians, sin
from typing import Any

from .triangulation import EARTH_RADIUS_M, Estimate


def estimate_to_geojson(estimate: Estimate, *, vertices: int = 72) -> dict[str, Any]:
    """Return a GeoJSON FeatureCollection containing a hypothesis point and 95% ellipse."""
    if not isinstance(estimate, Estimate):
        raise TypeError("estimate must be a network.triangulation.Estimate")
    if type(vertices) is not int or not 24 <= vertices <= 360:
        raise ValueError("vertices must be an integer from 24 to 360")

    numeric = {
        "latitude": estimate.latitude,
        "longitude": estimate.longitude,
        "rms_error_m": estimate.rms_error_m,
        "max_range_m": estimate.max_range_m,
        "ellipse_major_95_m": estimate.ellipse_major_95_m,
        "ellipse_minor_95_m": estimate.ellipse_minor_95_m,
        "ellipse_bearing_deg": estimate.ellipse_bearing_deg,
        "rms_angular_error_deg": estimate.rms_angular_error_deg,
    }
    for name, value in numeric.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
            raise ValueError(f"{name} must be a finite number")

    latitude = float(estimate.latitude)
    longitude = float(estimate.longitude)
    major = float(estimate.ellipse_major_95_m)
    minor = float(estimate.ellipse_minor_95_m)
    bearing = float(estimate.ellipse_bearing_deg)
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("estimate coordinates are outside valid geographic ranges")
    if major <= 0 or minor <= 0 or major < minor:
        raise ValueError("95% uncertainty ellipse axes must be positive with major >= minor")
    if not 0 <= bearing < 180:
        raise ValueError("ellipse bearing must be in [0, 180)")
    if type(estimate.bearing_count) is not int or estimate.bearing_count < 3:
        raise ValueError("bearing_count must be an integer of at least three")
    if estimate.status != "search_hypothesis":
        raise ValueError("only provisional search_hypothesis estimates may be exported")
    if abs(cos(radians(latitude))) < 1e-6:
        raise ValueError("GeoJSON local projection is unstable near the poles")

    angle = radians(bearing)
    sin_bearing = sin(angle)
    cos_bearing = cos(angle)
    lon_scale = EARTH_RADIUS_M * cos(radians(latitude))
    ring: list[list[float]] = []

    for index in range(vertices):
        parameter = 2.0 * pi * index / vertices
        along_major = major * cos(parameter)
        along_minor = minor * sin(parameter)
        east = along_major * sin_bearing + along_minor * cos_bearing
        north = along_major * cos_bearing - along_minor * sin_bearing
        point_latitude = latitude + (north / EARTH_RADIUS_M) * (180.0 / pi)
        point_longitude = longitude + (east / lon_scale) * (180.0 / pi)
        if not -90 <= point_latitude <= 90 or not isfinite(point_longitude):
            raise ValueError("uncertainty ellipse extends outside valid geographic coordinates")
        # Normalize longitude across the antimeridian without changing the
        # local tangent-plane shape.
        point_longitude = (point_longitude + 180.0) % 360.0 - 180.0
        ring.append([round(point_longitude, 8), round(point_latitude, 8)])

    ring.append(list(ring[0]))
    common = {
        "status": "search_hypothesis",
        "bearing_count": estimate.bearing_count,
        "inlier_station_ids": list(estimate.inlier_station_ids),
        "rejected_station_ids": list(estimate.rejected_station_ids),
        "rms_error_m": round(float(estimate.rms_error_m), 3),
        "rms_angular_error_deg": round(float(estimate.rms_angular_error_deg), 5),
        "max_range_m": round(float(estimate.max_range_m), 3),
        "uncertainty_method": "local_linearized_gaussian_95_percent_ellipse",
        "operational_notice": (
            "Search hypothesis only. Not a confirmed nest location or boundary. "
            "Field calibration and independent survey validation remain required."
        ),
    }
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(longitude, 8), round(latitude, 8)],
                },
                "properties": {**common, "feature_kind": "estimated_intersection"},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {
                    **common,
                    "feature_kind": "uncertainty_ellipse",
                    "confidence_level": 0.95,
                    "semi_major_axis_m": round(major, 3),
                    "semi_minor_axis_m": round(minor, 3),
                    "major_axis_bearing_deg": round(bearing, 5),
                    "approximation_only": True,
                },
            },
        ],
    }
