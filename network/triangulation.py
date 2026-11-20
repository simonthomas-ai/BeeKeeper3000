"""Dependency-free bearing triangulation with angular uncertainty.

Bearings are azimuths clockwise from true north. The output is a search
hypothesis, never a confirmed nest location. Coordinates are projected into
a local tangent approximation around the observations' mean position; the
operational area must remain local (recommended <= 30 km across).

The estimator minimizes wrapped angular residuals with a robust starting fit,
then rejects a bounded number of statistically inconsistent bearings. Its
95% ellipse is a local linearized Gaussian approximation, not a guarantee
that the true target lies inside that ellipse. Field calibration and survey
validation remain mandatory before operational use.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import atan2, cos, degrees, hypot, isfinite, pi, radians, sin, sqrt
from typing import Iterable

EARTH_RADIUS_M = 6_371_000.0
CHI2_2D_95 = 5.991464547107979
HUBER_K = 2.5


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
    ellipse_major_95_m: float = 0.0
    ellipse_minor_95_m: float = 0.0
    ellipse_bearing_deg: float = 0.0
    rms_angular_error_deg: float = 0.0
    inlier_station_ids: tuple[str, ...] = ()
    rejected_station_ids: tuple[str, ...] = ()


def _number(value, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not isfinite(result):
        raise ValueError(f"{field} must be a finite number")
    return result


def _validate(items: list[Bearing], max_time_delta_sec: int) -> None:
    if len(items) < 3:
        raise ValueError("at least three independent bearings are required")
    if type(max_time_delta_sec) is not int or not 1 <= max_time_delta_sec <= 7 * 24 * 60 * 60:
        raise ValueError("max_time_delta_sec must be an integer from 1 second to 7 days")
    if any(not isinstance(item, Bearing) for item in items):
        raise ValueError("all observations must be Bearing objects")
    station_ids = []
    timestamps = []
    for b in items:
        if not isinstance(b.station_id, str) or not 1 <= len(b.station_id.strip()) <= 128:
            raise ValueError("station_id must be a non-empty string up to 128 characters")
        station_ids.append(b.station_id.strip())
        latitude = _number(b.latitude, "latitude")
        longitude = _number(b.longitude, "longitude")
        azimuth = _number(b.azimuth_deg, "azimuth_deg")
        sigma = _number(b.sigma_deg, "sigma_deg")
        if not -90 <= latitude <= 90:
            raise ValueError("latitude must be in [-90, 90]")
        if not -180 <= longitude <= 180:
            raise ValueError("longitude must be in [-180, 180]")
        if not 0 <= azimuth < 360:
            raise ValueError("azimuth must be in [0, 360)")
        if not 0.5 <= sigma <= 45:
            raise ValueError("sigma_deg must be in [0.5, 45]")
        if not isinstance(b.observed_at, str) or not b.observed_at:
            raise ValueError("each bearing requires a timezone-aware timestamp")
        try:
            stamp = datetime.fromisoformat(b.observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid observation timestamp") from exc
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("observation timestamp must include timezone")
        timestamps.append(stamp.timestamp())
    if len(set(station_ids)) != len(items):
        raise ValueError("station_id values must be unique")
    if max(timestamps) - min(timestamps) > max_time_delta_sec:
        raise ValueError("bearings fall outside the allowed time window")


def _wrap_angle(angle: float) -> float:
    return (angle + pi) % (2.0 * pi) - pi


def _initial_line_intersection(items: list[Bearing], points: list[tuple[float, float]]) -> tuple[float, float]:
    # A x = b, with each row the unit normal to a measured bearing line.
    aa = ab = bb = ax = by = 0.0
    for bearing, (px, py) in zip(items, points):
        theta = radians(float(bearing.azimuth_deg))
        dx, dy = sin(theta), cos(theta)
        nx, ny = dy, -dx
        weight = 1.0 / (radians(float(bearing.sigma_deg)) ** 2)
        c = nx * px + ny * py
        aa += weight * nx * nx
        ab += weight * nx * ny
        bb += weight * ny * ny
        ax += weight * nx * c
        by += weight * ny * c

    determinant = aa * bb - ab * ab
    geometry_ratio = determinant / (aa * bb) if aa * bb else 0.0
    if geometry_ratio < sin(radians(10.0)) ** 2:
        raise ValueError("bearings are nearly parallel; intersection is unstable")
    return ((ax * bb - by * ab) / determinant,
            (aa * by - ab * ax) / determinant)


def _angular_residual(bearing: Bearing, point: tuple[float, float], x: float, y: float):
    px, py = point
    dx = x - px
    dy = y - py
    distance_sq = dx * dx + dy * dy
    if distance_sq <= 1e-6:
        raise ValueError("estimated target is too close to a bearing station")
    theta = radians(float(bearing.azimuth_deg))
    along = dx * sin(theta) + dy * cos(theta)
    predicted = atan2(dx, dy)
    residual = _wrap_angle(predicted - theta)
    jx = dy / distance_sq
    jy = -dx / distance_sq
    return residual, jx, jy, along


def _fit_angular(items: list[Bearing], points: list[tuple[float, float]]) -> tuple[float, float]:
    x, y = _initial_line_intersection(items, points)
    for _ in range(40):
        hxx = hxy = hyy = gx = gy = 0.0
        for bearing, point in zip(items, points):
            residual, jx, jy, _ = _angular_residual(bearing, point, x, y)
            sigma = radians(float(bearing.sigma_deg))
            normalized = abs(residual) / sigma
            robust_weight = 1.0 if normalized <= HUBER_K else HUBER_K / normalized
            weight = robust_weight / (sigma * sigma)
            hxx += weight * jx * jx
            hxy += weight * jx * jy
            hyy += weight * jy * jy
            gx += weight * jx * residual
            gy += weight * jy * residual
        determinant = hxx * hyy - hxy * hxy
        if determinant <= 1e-18 or not isfinite(determinant):
            raise ValueError("bearing geometry cannot constrain a stable intersection")
        step_x = (-gx * hyy + hxy * gy) / determinant
        step_y = (-hxx * gy + hxy * gx) / determinant
        if not isfinite(step_x) or not isfinite(step_y):
            raise ValueError("triangulation iteration became non-finite")
        step_length = hypot(step_x, step_y)
        if step_length > 10_000:
            factor = 10_000 / step_length
            step_x *= factor
            step_y *= factor
        x += step_x
        y += step_y
        if hypot(step_x, step_y) < 0.001:
            break
    return x, y


def _residual_statistics(items: list[Bearing], points: list[tuple[float, float]], x: float, y: float):
    records = []
    for bearing, point in zip(items, points):
        residual, jx, jy, along = _angular_residual(bearing, point, x, y)
        sigma = radians(float(bearing.sigma_deg))
        records.append({
            "bearing": bearing,
            "residual": residual,
            "normalized": abs(residual) / sigma,
            "jx": jx,
            "jy": jy,
            "along": along,
            "cross_track": along * sin(residual),
            "sigma": sigma,
        })
    return records


def _uncertainty_ellipse(records) -> tuple[float, float, float]:
    # Fisher information in local east/north metres for angular observations.
    hxx = hxy = hyy = 0.0
    for row in records:
        weight = 1.0 / (row["sigma"] ** 2)
        hxx += weight * row["jx"] * row["jx"]
        hxy += weight * row["jx"] * row["jy"]
        hyy += weight * row["jy"] * row["jy"]
    determinant = hxx * hyy - hxy * hxy
    if determinant <= 1e-18 or not isfinite(determinant):
        raise ValueError("uncertainty ellipse is unbounded because geometry is unstable")

    cxx = hyy / determinant
    cxy = -hxy / determinant
    cyy = hxx / determinant
    trace = cxx + cyy
    discriminant = sqrt(max(0.0, (cxx - cyy) ** 2 + 4.0 * cxy * cxy))
    eigen_major = max(0.0, (trace + discriminant) / 2.0)
    eigen_minor = max(0.0, (trace - discriminant) / 2.0)
    scale = sqrt(CHI2_2D_95)
    major = scale * sqrt(eigen_major)
    minor = scale * sqrt(eigen_minor)

    if abs(cxy) > 1e-12:
        vx, vy = cxy, eigen_major - cxx
    elif cxx >= cyy:
        vx, vy = 1.0, 0.0
    else:
        vx, vy = 0.0, 1.0
    bearing = degrees(atan2(vx, vy)) % 180.0
    if not all(isfinite(v) for v in (major, minor, bearing)):
        raise ValueError("uncertainty ellipse is non-finite")
    return major, minor, bearing


def triangulate(
    bearings: Iterable[Bearing],
    *,
    max_rms_error_m: float = 250.0,
    max_area_m: float = 30_000.0,
    max_time_delta_sec: int = 1800,
    outlier_sigma: float = 5.0,
    max_outliers: int = 1,
) -> Estimate:
    """Estimate an intersection and local 95% uncertainty ellipse.

    Angular residuals are weighted by each station's sigma in radians. Up to
    max_outliers observations above outlier_sigma are rejected while keeping
    at least three stations. Inconsistent geometry fails closed.
    """
    items = list(bearings)
    _validate(items, max_time_delta_sec)
    max_rms_error_m = _number(max_rms_error_m, "max_rms_error_m")
    max_area_m = _number(max_area_m, "max_area_m")
    outlier_sigma = _number(outlier_sigma, "outlier_sigma")
    if max_rms_error_m <= 0 or max_area_m <= 0:
        raise ValueError("max_rms_error_m and max_area_m must be positive")
    if not 2.0 <= outlier_sigma <= 20.0:
        raise ValueError("outlier_sigma must be between 2 and 20")
    if type(max_outliers) is not int or not 0 <= max_outliers <= len(items) - 3:
        raise ValueError("max_outliers must leave at least three inlier bearings")

    lat0 = sum(float(b.latitude) for b in items) / len(items)
    lon0 = sum(float(b.longitude) for b in items) / len(items)
    lat_scale = radians(1.0) * EARTH_RADIUS_M
    lon_scale = lat_scale * cos(radians(lat0))
    if abs(lon_scale) < 1e-6:
        raise ValueError("local east-west projection is unstable near the poles")
    all_points = [
        ((float(b.longitude) - lon0) * lon_scale,
         (float(b.latitude) - lat0) * lat_scale)
        for b in items
    ]
    if max(max(p[0] for p in all_points) - min(p[0] for p in all_points),
           max(p[1] for p in all_points) - min(p[1] for p in all_points)) > max_area_m:
        raise ValueError("bearing stations exceed local projection area")

    active_indices = list(range(len(items)))
    rejected_indices = []
    while True:
        active = [items[i] for i in active_indices]
        points = [all_points[i] for i in active_indices]
        x, y = _fit_angular(active, points)
        records = _residual_statistics(active, points, x, y)
        worst = max(range(len(records)), key=lambda idx: records[idx]["normalized"])
        worst_sigma = records[worst]["normalized"]
        if worst_sigma <= outlier_sigma:
            break
        if len(rejected_indices) >= max_outliers or len(active_indices) <= 3:
            raise ValueError(
                "inconsistent bearings: station {} is {:.1f} sigma from the estimated direction".format(
                    active[worst].station_id, worst_sigma
                )
            )
        rejected_indices.append(active_indices.pop(worst))

    for row in records:
        if row["along"] <= 0:
            raise ValueError(
                "estimated target lies behind inlier station {}".format(
                    row["bearing"].station_id
                )
            )

    weighted_cross = sum(
        row["cross_track"] ** 2 / (row["sigma"] ** 2) for row in records
    )
    total_weight = sum(1.0 / (row["sigma"] ** 2) for row in records)
    rms = sqrt(weighted_cross / total_weight)
    if not isfinite(rms) or rms > max_rms_error_m:
        raise ValueError("bearing residual too large ({:.1f} m)".format(rms))

    ellipse_major, ellipse_minor, ellipse_bearing = _uncertainty_ellipse(records)
    rms_angle = sqrt(sum(row["residual"] ** 2 for row in records) / len(records))

    latitude = lat0 + (y / EARTH_RADIUS_M) * (180.0 / pi)
    longitude = lon0 + (x / (EARTH_RADIUS_M * cos(radians(lat0)))) * (180.0 / pi)
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("estimated position is outside valid geographic coordinates")

    return Estimate(
        latitude=latitude,
        longitude=longitude,
        rms_error_m=rms,
        bearing_count=len(records),
        max_range_m=max(row["along"] for row in records),
        ellipse_major_95_m=ellipse_major,
        ellipse_minor_95_m=ellipse_minor,
        ellipse_bearing_deg=ellipse_bearing,
        rms_angular_error_deg=degrees(rms_angle),
        inlier_station_ids=tuple(row["bearing"].station_id for row in records),
        rejected_station_ids=tuple(items[i].station_id for i in rejected_indices),
    )
