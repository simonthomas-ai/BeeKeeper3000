"""Evidence report for known-target bearing triangulation field trials.

The input CSV contains confidential station and surveyed-target coordinates.
The JSON report intentionally emits derived errors only, not coordinates.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .triangulation import Bearing, Estimate, triangulate

EARTH_RADIUS_M = 6_371_000.0
REQUIRED_COLUMNS = (
    "trial_id",
    "station_id",
    "station_latitude",
    "station_longitude",
    "azimuth_deg",
    "sigma_deg",
    "observed_at",
    "target_latitude",
    "target_longitude",
)
MAX_INPUT_ROWS = 100_000
MAX_STATIONS_PER_TRIAL = 64


class FieldReportError(ValueError):
    """Invalid or unsafe field-trial evidence input."""


def _finite_float(value: str, field: str, line: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FieldReportError(f"line {line}: {field} must be a finite number") from exc
    if not math.isfinite(number):
        raise FieldReportError(f"line {line}: {field} must be a finite number")
    return number


def _coordinate(value: str, field: str, low: float, high: float, line: int) -> float:
    result = _finite_float(value, field, line)
    if not low <= result <= high:
        raise FieldReportError(f"line {line}: {field} is outside valid geographic bounds")
    return result


def _initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle initial azimuth, clockwise from true north."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lon = math.radians(lon2 - lon1)
    y = math.sin(delta_lon) * math.cos(phi2)
    x = (
        math.cos(phi1) * math.sin(phi2)
        - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lon)
    )
    if abs(x) < 1e-15 and abs(y) < 1e-15:
        raise FieldReportError("station and surveyed target coordinates must differ")
    return math.degrees(math.atan2(y, x)) % 360.0


def _wrapped_delta_deg(measured: float, expected: float) -> float:
    return (measured - expected + 180.0) % 360.0 - 180.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(max(0.0, a))))


def _ellipse_contains(estimate: Estimate, target_lat: float, target_lon: float) -> bool:
    """Test ground truth against the returned 95% ellipse in local EN metres."""
    mean_lat = math.radians((estimate.latitude + target_lat) / 2.0)
    east = math.radians(target_lon - estimate.longitude) * EARTH_RADIUS_M * math.cos(mean_lat)
    north = math.radians(target_lat - estimate.latitude) * EARTH_RADIUS_M
    beta = math.radians(estimate.ellipse_bearing_deg)
    major = east * math.sin(beta) + north * math.cos(beta)
    minor = east * math.cos(beta) - north * math.sin(beta)
    if estimate.ellipse_major_95_m <= 0 or estimate.ellipse_minor_95_m <= 0:
        return False
    mahalanobis = (
        (major / estimate.ellipse_major_95_m) ** 2
        + (minor / estimate.ellipse_minor_95_m) ** 2
    )
    return mahalanobis <= 1.0


def _wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> list[float] | None:
    if trials <= 0:
        return None
    p = successes / trials
    denominator = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / denominator
    margin = z * math.sqrt((p * (1.0 - p) / trials) + z * z / (4.0 * trials * trials)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _circular_stats(errors: list[float], sigmas: list[float]) -> dict:
    radians = [math.radians(value) for value in errors]
    mean_sin = sum(math.sin(value) for value in radians) / len(radians)
    mean_cos = sum(math.cos(value) for value in radians) / len(radians)
    resultant = min(1.0, math.hypot(mean_sin, mean_cos))
    bias = math.degrees(math.atan2(mean_sin, mean_cos))
    circular_std = math.degrees(math.sqrt(max(0.0, -2.0 * math.log(max(resultant, 1e-15)))))
    absolute = sorted(abs(value) for value in errors)
    p95_index = max(0, math.ceil(0.95 * len(absolute)) - 1)
    normalized_rms = math.sqrt(
        sum((error / sigma) ** 2 for error, sigma in zip(errors, sigmas)) / len(errors)
    )
    return {
        "observations": len(errors),
        "circular_bias_deg": round(bias, 4),
        "circular_std_deg": round(circular_std, 4),
        "p95_absolute_error_deg": round(absolute[p95_index], 4),
        "mean_declared_sigma_deg": round(statistics.fmean(sigmas), 4),
        "normalized_rms_sigma": round(normalized_rms, 4),
    }


def _read_trials(path: str | Path) -> tuple[dict[str, list[Bearing]], dict[str, tuple[float, float]]]:
    source = Path(path).expanduser().resolve(strict=True)
    trials: dict[str, list[Bearing]] = defaultdict(list)
    targets: dict[str, tuple[float, float]] = {}
    station_locations: dict[str, tuple[float, float]] = {}
    seen_rows = 0

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames is None or tuple(reader.fieldnames) != REQUIRED_COLUMNS:
            raise FieldReportError(
                "CSV header must exactly match: " + ",".join(REQUIRED_COLUMNS)
            )
        for row in reader:
            line = reader.line_num
            if row is None or any(row.get(name) is None for name in REQUIRED_COLUMNS):
                raise FieldReportError(f"line {line}: malformed CSV row")
            if all(not (row[name] or "").strip() for name in REQUIRED_COLUMNS):
                continue
            seen_rows += 1
            if seen_rows > MAX_INPUT_ROWS:
                raise FieldReportError(f"input exceeds the {MAX_INPUT_ROWS} row safety limit")

            trial_id = (row["trial_id"] or "").strip()
            station_id = (row["station_id"] or "").strip()
            if not 1 <= len(trial_id) <= 80 or not 1 <= len(station_id) <= 80:
                raise FieldReportError(f"line {line}: trial_id and station_id must be 1..80 characters")

            station_lat = _coordinate(row["station_latitude"], "station_latitude", -90, 90, line)
            station_lon = _coordinate(row["station_longitude"], "station_longitude", -180, 180, line)
            azimuth = _finite_float(row["azimuth_deg"], "azimuth_deg", line)
            sigma = _finite_float(row["sigma_deg"], "sigma_deg", line)
            if not 0 <= azimuth < 360:
                raise FieldReportError(f"line {line}: azimuth_deg must be in [0, 360)")
            if not 0.5 <= sigma <= 45:
                raise FieldReportError(f"line {line}: sigma_deg must be in [0.5, 45]")

            target_lat = _coordinate(row["target_latitude"], "target_latitude", -90, 90, line)
            target_lon = _coordinate(row["target_longitude"], "target_longitude", -180, 180, line)
            expected = targets.get(trial_id)
            if expected is not None and (
                abs(expected[0] - target_lat) > 1e-7
                or abs(expected[1] - target_lon) > 1e-7
            ):
                raise FieldReportError(f"line {line}: surveyed target differs within trial {trial_id}")
            targets[trial_id] = (target_lat, target_lon)

            station_location = station_locations.get(station_id)
            if station_location is not None and (
                abs(station_location[0] - station_lat) > 1e-7
                or abs(station_location[1] - station_lon) > 1e-7
            ):
                raise FieldReportError(
                    f"line {line}: station {station_id} changed coordinates; use a new station/calibration ID"
                )
            station_locations[station_id] = (station_lat, station_lon)

            bearing = Bearing(
                station_id=station_id,
                latitude=station_lat,
                longitude=station_lon,
                azimuth_deg=azimuth,
                sigma_deg=sigma,
                observed_at=(row["observed_at"] or "").strip(),
            )
            if any(item.station_id == station_id for item in trials[trial_id]):
                raise FieldReportError(f"line {line}: station {station_id} is duplicated in trial {trial_id}")
            trials[trial_id].append(bearing)

            # Compute calibration error during ingest so malformed, colocated
            # target/station data fail before any report is generated.
            _initial_bearing_deg(station_lat, station_lon, target_lat, target_lon)

    if not trials:
        raise FieldReportError("CSV contains no bearing observations")
    for trial_id, bearings in trials.items():
        if len(bearings) > MAX_STATIONS_PER_TRIAL:
            raise FieldReportError(f"trial {trial_id} exceeds {MAX_STATIONS_PER_TRIAL} stations")
    return dict(trials), targets


def build_report(
    trials: dict[str, list[Bearing]],
    targets: dict[str, tuple[float, float]],
    *,
    minimum_trials: int = 30,
    max_time_delta_sec: int = 1800,
) -> dict:
    if type(minimum_trials) is not int or not 1 <= minimum_trials <= 100_000:
        raise ValueError("minimum_trials must be an integer from 1 to 100000")
    if type(max_time_delta_sec) is not int or not 1 <= max_time_delta_sec <= 604800:
        raise ValueError("max_time_delta_sec must be an integer from 1 second to 7 days")

    station_errors: dict[str, list[float]] = defaultdict(list)
    station_sigmas: dict[str, list[float]] = defaultdict(list)
    trial_results = []
    successful_errors = []
    ellipse_hits = 0
    solver_failures = 0
    observation_count = 0

    for trial_id in sorted(trials):
        bearings = trials[trial_id]
        target_lat, target_lon = targets[trial_id]
        observation_count += len(bearings)
        for bearing in bearings:
            expected = _initial_bearing_deg(
                bearing.latitude, bearing.longitude, target_lat, target_lon
            )
            station_errors[bearing.station_id].append(
                _wrapped_delta_deg(bearing.azimuth_deg, expected)
            )
            station_sigmas[bearing.station_id].append(bearing.sigma_deg)

        try:
            estimate = triangulate(
                bearings,
                max_time_delta_sec=max_time_delta_sec,
            )
        except (ValueError, ArithmeticError) as exc:
            solver_failures += 1
            trial_results.append({
                "trial_id": trial_id,
                "status": "solver_failed",
                "station_count": len(bearings),
                "error_type": type(exc).__name__,
                "error": str(exc)[:240],
            })
            continue

        error_m = _haversine_m(
            estimate.latitude, estimate.longitude, target_lat, target_lon
        )
        inside = _ellipse_contains(estimate, target_lat, target_lon)
        ellipse_hits += int(inside)
        successful_errors.append(error_m)
        trial_results.append({
            "trial_id": trial_id,
            "status": "estimated",
            "station_count": len(bearings),
            "inlier_count": estimate.bearing_count,
            "rejected_station_count": len(estimate.rejected_station_ids),
            "ground_truth_error_m": round(error_m, 3),
            "ellipse_95_contains_target": inside,
            "ellipse_major_95_m": round(estimate.ellipse_major_95_m, 3),
            "ellipse_minor_95_m": round(estimate.ellipse_minor_95_m, 3),
            "ellipse_bearing_deg": round(estimate.ellipse_bearing_deg, 3),
            "rms_angular_error_deg": round(estimate.rms_angular_error_deg, 4),
        })

    successful_count = len(successful_errors)
    coverage = (ellipse_hits / successful_count) if successful_count else None
    if len(trials) < minimum_trials:
        status = "insufficient_trials"
    elif solver_failures or coverage is None or coverage < 0.95:
        status = "calibration_review_required"
    else:
        status = "enough_samples_for_expert_review_only"

    station_report = {
        station_id: _circular_stats(station_errors[station_id], station_sigmas[station_id])
        for station_id in sorted(station_errors)
    }
    return {
        "report_version": 1,
        "status": status,
        "decision": "not_approved_for_operational_use",
        "minimum_trials_required": minimum_trials,
        "trial_count": len(trials),
        "successful_estimates": successful_count,
        "solver_failures": solver_failures,
        "observation_count": observation_count,
        "ground_truth_error_m": {
            "median": round(statistics.median(successful_errors), 3) if successful_errors else None,
            "p95": round(sorted(successful_errors)[max(0, math.ceil(0.95 * successful_count) - 1)], 3)
            if successful_errors else None,
            "maximum": round(max(successful_errors), 3) if successful_errors else None,
        },
        "ellipse_95_coverage": {
            "hits": ellipse_hits,
            "successful_trials": successful_count,
            "observed_rate": round(coverage, 5) if coverage is not None else None,
            "wilson_95_interval": _wilson_interval(ellipse_hits, successful_count),
        },
        "station_angular_calibration": station_report,
        "trials": trial_results,
        "privacy": {
            "coordinates_in_report": False,
            "input_contains_precise_coordinates": True,
            "identifiers_should_be_pseudonymous": True,
        },
        "limitations": [
            "The report evaluates supplied bearings against supplied surveyed targets; it does not validate the radio transport.",
            "Station angular errors are only comparable while the station, mount, alignment and calibration setup remain unchanged.",
            "A 95% ellipse is a local linearized statistical approximation; observed coverage requires enough independent known-target trials.",
            "Even a favourable report requires expert review and separate real-world hardware, legal, privacy and operational acceptance.",
        ],
    }


def report_csv(
    csv_path: str | Path,
    *,
    minimum_trials: int = 30,
    max_time_delta_sec: int = 1800,
) -> dict:
    trials, targets = _read_trials(csv_path)
    return build_report(
        trials,
        targets,
        minimum_trials=minimum_trials,
        max_time_delta_sec=max_time_delta_sec,
    )


def _write_private_report(path: str | Path, rendered: str) -> None:
    output_path = Path(path).expanduser()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    descriptor = os.open(output_path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
        handle.write(rendered)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate known-target triangulation trials; output contains no coordinates."
    )
    parser.add_argument("csv_file", help="Confidential local CSV with surveyed station and target coordinates")
    parser.add_argument("--minimum-trials", type=int, default=30)
    parser.add_argument("--max-time-delta-sec", type=int, default=1800)
    parser.add_argument("--output", default="-", help="JSON report path, or - for stdout")
    args = parser.parse_args(argv)

    try:
        report = report_csv(
            args.csv_file,
            minimum_trials=args.minimum_trials,
            max_time_delta_sec=args.max_time_delta_sec,
        )
        rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output == "-":
            sys.stdout.write(rendered)
        else:
            output_path = Path(args.output).expanduser()
            try:
                _write_private_report(output_path, rendered)
            except FileExistsError as exc:
                raise FieldReportError("refusing to overwrite an existing report file") from exc
            print(f"Private report written: {output_path}", file=sys.stderr)
        return 0 if report["status"] == "enough_samples_for_expert_review_only" else 2
    except (OSError, csv.Error, FieldReportError, ValueError) as exc:
        print(f"Field report failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
