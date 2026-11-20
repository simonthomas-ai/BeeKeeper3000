"""Robust weighted triangulation of geographic bearings.

The estimator uses a local tangent approximation, pairwise consensus to reject
gross bearing outliers, iteratively reweighted least squares and a 95% location
uncertainty ellipse. Output is a search hypothesis, never a confirmed nest.
Keep the station group local (recommended <= 30 km across).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from math import atan2, cos, degrees, isfinite, pi, radians, sin, sqrt
from typing import Iterable

EARTH_RADIUS_M = 6_371_000.0
CHI2_2D_95 = 5.991464547
CONSENSUS_SIGMA = 4.5
HUBER_K = 1.5
MIN_GEOMETRY_ANGLE_DEG = 10.0


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
    uncertainty_major_95_m: float = 0.0
    uncertainty_minor_95_m: float = 0.0
    uncertainty_bearing_deg: float = 0.0
    inlier_station_ids: tuple[str, ...] = ()
    outlier_station_ids: tuple[str, ...] = ()
    ellipse_95_coordinates: tuple[tuple[float, float], ...] = ()

    def to_geojson(self) -> dict:
        """Return a GeoJSON FeatureCollection for the point and 95% ellipse."""
        point_properties = {
            "status": self.status,
            "rms_error_m": self.rms_error_m,
            "bearing_count": self.bearing_count,
            "max_range_m": self.max_range_m,
            "uncertainty_major_95_m": self.uncertainty_major_95_m,
            "uncertainty_minor_95_m": self.uncertainty_minor_95_m,
            "uncertainty_bearing_deg": self.uncertainty_bearing_deg,
            "inlier_station_ids": list(self.inlier_station_ids),
            "outlier_station_ids": list(self.outlier_station_ids),
        }
        features = [{
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [self.longitude, self.latitude],
            },
            "properties": point_properties,
        }]
        if self.ellipse_95_coordinates:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[list(point) for point in self.ellipse_95_coordinates]],
                },
                "properties": {
                    "confidence_level": 0.95,
                    "status": self.status,
                    "description": "95% statistical search-hypothesis uncertainty ellipse",
                },
            })
        return {"type": "FeatureCollection", "features": features}


def _validate(items: list[Bearing], max_time_delta_sec: int) -> None:
    if len(items) < 3:
        raise ValueError("at least three independent bearings are required")
    if not isinstance(max_time_delta_sec, int) or isinstance(max_time_delta_sec, bool) or max_time_delta_sec < 0:
        raise ValueError("max_time_delta_sec must be a non-negative integer")
    if len({b.station_id for b in items}) != len(items):
        raise ValueError("station_id values must be unique")

    timestamps = []
    for b in items:
        if not isinstance(b.station_id, str) or not b.station_id.strip() or len(b.station_id) > 128:
            raise ValueError("invalid station identity")
        for value, low, high, name in (
            (b.latitude, -90.0, 90.0, "latitude"),
            (b.longitude, -180.0, 180.0, "longitude"),
            (b.azimuth_deg, 0.0, 360.0, "azimuth"),
            (b.sigma_deg, 0.5, 45.0, "sigma_deg"),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                raise ValueError(f"invalid {name}")
            if not low <= value <= high:
                raise ValueError(f"invalid {name}")
        if b.azimuth_deg >= 360.0:
            raise ValueError("azimuth must be in [0, 360)")
        if not b.observed_at:
            raise ValueError("each bearing requires a timezone-aware timestamp")
        try:
            stamp = datetime.fromisoformat(b.observed_at.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid observation timestamp") from exc
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("observation timestamp must include timezone")
        timestamps.append(stamp.timestamp())
    if max(timestamps) - min(timestamps) > max_time_delta_sec:
        raise ValueError("bearings fall outside the allowed time window")


def _normal_terms(bearing: Bearing, point: tuple[float, float]):
    px, py = point
    theta = radians(bearing.azimuth_deg)
    dx, dy = sin(theta), cos(theta)
    nx, ny = dy, -dx
    return px, py, dx, dy, nx, ny


def _along_residual(x: float, y: float, terms: tuple[float, ...]) -> tuple[float, float]:
    px, py, dx, dy, nx, ny = terms
    along = (x - px) * dx + (y - py) * dy
    residual = nx * (x - px) + ny * (y - py)
    return along, residual


def _line_intersection(
    first: tuple[float, ...], second: tuple[float, ...]
) -> tuple[float, float] | None:
    px1, py1, _, _, nx1, ny1 = first
    px2, py2, _, _, nx2, ny2 = second
    determinant = nx1 * ny2 - ny1 * nx2
    if abs(determinant) < sin(radians(MIN_GEOMETRY_ANGLE_DEG)):
        return None
    c1 = nx1 * px1 + ny1 * py1
    c2 = nx2 * px2 + ny2 * py2
    return (
        (c1 * ny2 - ny1 * c2) / determinant,
        (nx1 * c2 - c1 * nx2) / determinant,
    )


def _consensus(
    bearings: list[Bearing],
    terms: list[tuple[float, ...]],
    *,
    threshold_sigma: float,
) -> tuple[list[int], tuple[float, float]]:
    """Choose the best pairwise intersection supported by >=3 forward rays."""
    best_inliers: list[int] = []
    best_point: tuple[float, float] | None = None
    best_score: tuple[int, float, float] | None = None

    for i, j in combinations(range(len(bearings)), 2):
        candidate = _line_intersection(terms[i], terms[j])
        if candidate is None:
            continue
        x, y = candidate
        pair_along_i, _ = _along_residual(x, y, terms[i])
        pair_along_j, _ = _along_residual(x, y, terms[j])
        if pair_along_i <= 0 or pair_along_j <= 0:
            continue

        inliers = []
        normalized_sum = 0.0
        range_sum = 0.0
        for index, (bearing, line) in enumerate(zip(bearings, terms)):
            along, residual = _along_residual(x, y, line)
            if along <= 0:
                continue
            cross_sigma_m = max(1.0, along * radians(bearing.sigma_deg))
            normalized = abs(residual) / cross_sigma_m
            if normalized <= threshold_sigma:
                inliers.append(index)
                normalized_sum += normalized * normalized
                range_sum += along

        if len(inliers) < 3:
            continue
        score = (len(inliers), -normalized_sum, -range_sum)
        if best_score is None or score > best_score:
            best_score = score
            best_inliers = inliers
            best_point = candidate

    if len(best_inliers) < 3 or best_point is None:
        raise ValueError(
            "fewer than three forward bearings agree within the consensus uncertainty"
        )
    return best_inliers, best_point


def _weighted_solution(
    bearings: list[Bearing],
    terms: list[tuple[float, ...]],
    initial: tuple[float, float],
) -> tuple[float, float, tuple[float, float, float, float], list[float], list[float]]:
    """Iteratively solve a range-scaled Huber weighted least-squares system."""
    x, y = initial

    def matrix_at(px: float, py: float):
        aa = ab = bb = ax = by = 0.0
        residuals = []
        ranges = []
        for bearing, line in zip(bearings, terms):
            along, residual = _along_residual(px, py, line)
            if along <= 0:
                raise ValueError("estimated target lies behind at least one bearing")
            cross_sigma_m = max(1.0, along * radians(bearing.sigma_deg))
            normalized = abs(residual) / cross_sigma_m
            huber = 1.0 if normalized <= HUBER_K else HUBER_K / normalized
            weight = huber / (cross_sigma_m * cross_sigma_m)
            _, _, _, _, nx, ny = line
            c = nx * line[0] + ny * line[1]
            aa += weight * nx * nx
            ab += weight * nx * ny
            bb += weight * ny * ny
            ax += weight * nx * c
            by += weight * ny * c
            residuals.append(residual)
            ranges.append(along)
        determinant = aa * bb - ab * ab
        geometry_ratio = determinant / (aa * bb) if aa > 0 and bb > 0 else 0.0
        if geometry_ratio < sin(radians(MIN_GEOMETRY_ANGLE_DEG)) ** 2:
            raise ValueError("bearings are nearly parallel; intersection is unstable")
        return aa, ab, bb, determinant, ax, by, residuals, ranges

    for _ in range(12):
        aa, ab, bb, determinant, ax, by, _, _ = matrix_at(x, y)
        new_x = (ax * bb - by * ab) / determinant
        new_y = (aa * by - ab * ax) / determinant
        shift = sqrt((new_x - x) ** 2 + (new_y - y) ** 2)
        x, y = new_x, new_y
        if shift < 0.001:
            break

    aa, ab, bb, determinant, _, _, residuals, ranges = matrix_at(x, y)
    covariance = (bb / determinant, -ab / determinant, aa / determinant, determinant)
    return x, y, covariance, residuals, ranges


def _uncertainty_ellipse(
    x: float,
    y: float,
    covariance: tuple[float, float, float, float],
    lat0: float,
    lon0: float,
) -> tuple[float, float, float, tuple[tuple[float, float], ...]]:
    var_x, cov_xy, var_y, _ = covariance
    trace = var_x + var_y
    discriminant = sqrt(max(0.0, (var_x - var_y) ** 2 + 4.0 * cov_xy ** 2))
    lambda_major = max(0.0, (trace + discriminant) / 2.0)
    lambda_minor = max(0.0, (trace - discriminant) / 2.0)
    orientation = 0.5 * atan2(2.0 * cov_xy, var_x - var_y)
    major_scale = sqrt(lambda_major * CHI2_2D_95)
    minor_scale = sqrt(lambda_minor * CHI2_2D_95)
    major_east, major_north = cos(orientation), sin(orientation)
    minor_east, minor_north = -sin(orientation), cos(orientation)
    bearing = degrees(atan2(major_east, major_north)) % 360.0

    lat_scale = radians(1.0) * EARTH_RADIUS_M
    lon_scale = lat_scale * cos(radians(lat0))
    coordinates = []
    for step in range(37):
        angle = 2.0 * pi * step / 36.0
        east = x + major_scale * cos(angle) * major_east + minor_scale * sin(angle) * minor_east
        north = y + major_scale * cos(angle) * major_north + minor_scale * sin(angle) * minor_north
        latitude = lat0 + north / EARTH_RADIUS_M * (180.0 / pi)
        longitude = lon0 + east / lon_scale * (180.0 / pi)
        coordinates.append((longitude, latitude))
    return major_scale, minor_scale, bearing, tuple(coordinates)


def triangulate(
    bearings: Iterable[Bearing],
    *,
    max_rms_error_m: float = 250.0,
    max_area_m: float = 30_000.0,
    max_time_delta_sec: int = 1800,
    consensus_sigma: float = CONSENSUS_SIGMA,
) -> Estimate:
    """Return a robust weighted intersection and a 95% search uncertainty ellipse.

    A pairwise consensus stage rejects gross outliers when at least three
    independent forward bearings agree. Iteratively reweighted least squares
    then accounts for angular uncertainty increasing with station-to-target
    range. With exactly three bearings, one inconsistent ray causes a safe
    rejection instead of an unsupported two-ray estimate.
    """
    items = list(bearings)
    _validate(items, max_time_delta_sec)
    for value, name in ((max_rms_error_m, "max_rms_error_m"), (max_area_m, "max_area_m"),
                        (consensus_sigma, "consensus_sigma")):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a positive finite number")
    if consensus_sigma < 2.0 or consensus_sigma > 10.0:
        raise ValueError("consensus_sigma must be between 2 and 10")

    lat0 = sum(b.latitude for b in items) / len(items)
    lon0 = sum(b.longitude for b in items) / len(items)
    lat_scale = radians(1.0) * EARTH_RADIUS_M
    lon_scale = lat_scale * cos(radians(lat0))
    if abs(lon_scale) < 1e-6:
        raise ValueError("local longitude projection is unstable near the poles")

    points = [
        ((b.longitude - lon0) * lon_scale, (b.latitude - lat0) * lat_scale)
        for b in items
    ]
    width = max(p[0] for p in points) - min(p[0] for p in points)
    height = max(p[1] for p in points) - min(p[1] for p in points)
    if max(width, height) > max_area_m:
        raise ValueError("bearing stations exceed local projection area")

    all_terms = [_normal_terms(b, p) for b, p in zip(items, points)]
    inliers, initial = _consensus(items, all_terms, threshold_sigma=consensus_sigma)

    # Re-solve and remove any candidate that falls outside the standardized
    # uncertainty after robust weighting. Never publish with fewer than 3.
    while True:
        selected = [items[index] for index in inliers]
        terms = [all_terms[index] for index in inliers]
        x, y, covariance, residuals, ranges = _weighted_solution(selected, terms, initial)
        final_outliers = []
        for local_index, (bearing, residual, distance) in enumerate(zip(selected, residuals, ranges)):
            normalized = abs(residual) / max(1.0, distance * radians(bearing.sigma_deg))
            if normalized > consensus_sigma:
                final_outliers.append(inliers[local_index])
        if not final_outliers:
            break
        inliers = [index for index in inliers if index not in final_outliers]
        if len(inliers) < 3:
            raise ValueError("fewer than three bearings remain after outlier rejection")
        initial = (x, y)

    rms = sqrt(sum(residual * residual for residual in residuals) / len(residuals))
    if rms > max_rms_error_m:
        raise ValueError(f"bearing residual too large ({rms:.1f} m)")

    latitude = lat0 + (y / EARTH_RADIUS_M) * (180.0 / pi)
    longitude = lon0 + (x / lon_scale) * (180.0 / pi)
    major, minor, orientation, ellipse = _uncertainty_ellipse(
        x, y, covariance, lat0, lon0
    )
    inlier_ids = tuple(items[index].station_id for index in inliers)
    outlier_ids = tuple(b.station_id for index, b in enumerate(items) if index not in inliers)
    return Estimate(
        latitude=latitude,
        longitude=longitude,
        rms_error_m=rms,
        bearing_count=len(inliers),
        max_range_m=max(ranges),
        status="search_hypothesis",
        uncertainty_major_95_m=major,
        uncertainty_minor_95_m=minor,
        uncertainty_bearing_deg=orientation,
        inlier_station_ids=inlier_ids,
        outlier_station_ids=outlier_ids,
        ellipse_95_coordinates=ellipse,
    )
