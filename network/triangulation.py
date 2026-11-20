"""Dependency-free weighted triangulation of geographic bearings.

Bearings are azimuths clockwise from true north. The output is a search
hypothesis, never a confirmed nest location. Coordinates are projected into
a local tangent approximation around the observations' mean latitude/longitude;
keep the operational area local (recommended <= 30 km across).
"""
from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin, sqrt
from typing import Iterable

EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class Bearing:
    station_id: str
    latitude: float
    longitude: float
    azimuth_deg: float
    sigma_deg: float = 5.0
    observed_at: str = ""


@dataclass(frozen=True)
class Estimate:
    latitude: float
    longitude: float
    rms_error_m: float
    bearing_count: int
    max_range_m: float
    status: str = "search_hypothesis"


def _validate(items: list[Bearing]) -> None:
    if len(items) < 3:
        raise ValueError("at least three independent bearings are required")
    if len({b.station_id for b in items}) != len(items):
        raise ValueError("station_id values must be unique")
    for b in items:
        if not b.station_id or not (-90 <= b.latitude <= 90):
            raise ValueError("invalid station identity or latitude")
        if not (-180 <= b.longitude <= 180):
            raise ValueError("invalid longitude")
        if not (0 <= b.azimuth_deg < 360):
            raise ValueError("azimuth must be in [0, 360)")
        if not (0.5 <= b.sigma_deg <= 45):
            raise ValueError("sigma_deg must be in [0.5, 45]")


def triangulate(
    bearings: Iterable[Bearing],
    *,
    max_rms_error_m: float = 250.0,
    max_area_m: float = 30_000.0,
) -> Estimate:
    """Return weighted intersection; reject poor geometry and invalid rays."""
    items = list(bearings)
    _validate(items)

    lat0 = sum(b.latitude for b in items) / len(items)
    lon0 = sum(b.longitude for b in items) / len(items)
    lat_scale = radians(1.0) * EARTH_RADIUS_M
    lon_scale = lat_scale * cos(radians(lat0))
    points = [
        ((b.longitude - lon0) * lon_scale, (b.latitude - lat0) * lat_scale)
        for b in items
    ]
    if max(max(p[0] for p in points) - min(p[0] for p in points),
           max(p[1] for p in points) - min(p[1] for p in points)) > max_area_m:
        raise ValueError("bearing stations exceed local projection area")

    # A x = b, where each row is the unit normal to the bearing line.
    aa = ab = bb = ax = by = 0.0
    normals = []
    for bearing, (px, py) in zip(items, points):
        theta = radians(bearing.azimuth_deg)
        dx, dy = sin(theta), cos(theta)  # east, north
        nx, ny = dy, -dx                 # perpendicular normal
        weight = 1.0 / (radians(bearing.sigma_deg) ** 2)
        c = nx * px + ny * py
        aa += weight * nx * nx
        ab += weight * nx * ny
        bb += weight * ny * ny
        ax += weight * nx * c
        by += weight * ny * c
        normals.append((px, py, dx, dy, nx, ny))

    determinant = aa * bb - ab * ab
    if determinant <= 1e-8:
        raise ValueError("bearings are nearly parallel; intersection is unstable")
    x = (ax * bb - by * ab) / determinant
    y = (aa * by - ab * ax) / determinant

    residuals = []
    ranges = []
    for px, py, dx, dy, nx, ny in normals:
        along = (x - px) * dx + (y - py) * dy
        if along <= 0:
            raise ValueError("estimated target lies behind at least one bearing")
        ranges.append(along)
        residuals.append(nx * (x - px) + ny * (y - py))

    # Weighted residual scale, in metres.
    weighted_sum = 0.0
    total_weight = 0.0
    for b, residual in zip(items, residuals):
        w = 1.0 / (radians(b.sigma_deg) ** 2)
        weighted_sum += w * residual * residual
        total_weight += w
    rms = sqrt(weighted_sum / total_weight)
    if rms > max_rms_error_m:
        raise ValueError(f"bearing residual too large ({rms:.1f} m)")

    latitude = lat0 + (y / EARTH_RADIUS_M) * (180.0 / 3.141592653589793)
    longitude = lon0 + (x / (EARTH_RADIUS_M * cos(radians(lat0)))) * (180.0 / 3.141592653589793)
    return Estimate(latitude, longitude, rms, len(items), max(ranges))
