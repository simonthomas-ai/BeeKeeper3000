"""NMEA 0183 GNSS/heading parser and metadata-only serial adapter.

Coordinates are retained only inside the parser's in-memory fix object. The
outbound event contains bearing and quality metadata but never exact position,
raw NMEA sentences, serial port names or receiver diagnostics.
"""
from __future__ import annotations

import asyncio
import math
import re
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from adapters.lifecycle import AdapterConfigurationError, AdapterTransientError


_MAX_SENTENCE_BYTES = 128
_TIME_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})(?:\.(\d{1,6}))?$")
_DATE_RE = re.compile(r"^\d{6}$")
_HEX_RE = re.compile(r"^[0-9A-Fa-f]{2}$")


@dataclass(frozen=True)
class NmeaFix:
    """Private in-memory GNSS fix. Coordinates must never be put in an event."""

    latitude_degrees: float
    longitude_degrees: float
    captured_at: datetime
    fix_quality: int
    satellites: int
    hdop: float
    received_monotonic: float


@dataclass(frozen=True)
class NmeaHeading:
    """Calibrated true heading with monotonic receipt time."""

    true_degrees: float
    source: str
    received_monotonic: float


def _checksum_body(line: str | bytes) -> str:
    if isinstance(line, bytes):
        if len(line) > _MAX_SENTENCE_BYTES:
            raise ValueError("nmea_sentence_too_long")
        try:
            text = line.decode("ascii", errors="strict")
        except UnicodeDecodeError:
            raise ValueError("nmea_non_ascii") from None
    elif isinstance(line, str):
        text = line
        if len(text.encode("ascii", errors="ignore")) != len(text):
            raise ValueError("nmea_non_ascii")
        if len(text) > _MAX_SENTENCE_BYTES:
            raise ValueError("nmea_sentence_too_long")
    else:
        raise ValueError("nmea_sentence_type_invalid")

    text = text.strip("\r\n")
    if not text.startswith("$") or text.count("*") != 1:
        raise ValueError("nmea_framing_invalid")
    body, checksum = text[1:].split("*", 1)
    if not _HEX_RE.fullmatch(checksum) or not body:
        raise ValueError("nmea_checksum_missing")
    computed = 0
    for character in body:
        computed ^= ord(character)
    if computed != int(checksum, 16):
        raise ValueError("nmea_checksum_mismatch")
    if any(ord(character) < 0x20 or ord(character) > 0x7E for character in body):
        raise ValueError("nmea_control_character")
    return body


def _parse_time_of_day(value: str) -> tuple[float, tuple[int, int, int, int]]:
    match = _TIME_RE.fullmatch(value)
    if match is None:
        raise ValueError("nmea_time_invalid")
    hour, minute, second = (int(match.group(i)) for i in (1, 2, 3))
    fraction = match.group(4) or ""
    microsecond = int(fraction.ljust(6, "0")) if fraction else 0
    if hour > 23 or minute > 59 or second > 59:
        raise ValueError("nmea_time_out_of_range")
    total = hour * 3600 + minute * 60 + second + microsecond / 1_000_000
    return total, (hour, minute, second, microsecond)


def _parse_date(value: str) -> date:
    if not _DATE_RE.fullmatch(value):
        raise ValueError("nmea_date_invalid")
    day, month, year_short = int(value[:2]), int(value[2:4]), int(value[4:6])
    year = 1900 + year_short if year_short >= 80 else 2000 + year_short
    try:
        return date(year, month, day)
    except ValueError:
        raise ValueError("nmea_date_out_of_range") from None


def _coordinate(raw: str, hemisphere: str, *, latitude: bool) -> float:
    if not raw or hemisphere not in ({"N", "S"} if latitude else {"E", "W"}):
        raise ValueError("nmea_coordinate_missing")
    try:
        number = float(raw)
    except ValueError:
        raise ValueError("nmea_coordinate_invalid") from None
    if not math.isfinite(number) or number < 0:
        raise ValueError("nmea_coordinate_invalid")
    degrees = int(number // 100)
    minutes = number - degrees * 100
    maximum = 90 if latitude else 180
    if minutes >= 60 or degrees > maximum or (degrees == maximum and minutes != 0):
        raise ValueError("nmea_coordinate_out_of_range")
    result = degrees + minutes / 60.0
    if hemisphere in {"S", "W"}:
        result = -result
    if not math.isfinite(result):
        raise ValueError("nmea_coordinate_invalid")
    return result


def _angle(value: str) -> float:
    try:
        angle = float(value)
    except ValueError:
        raise ValueError("nmea_heading_invalid") from None
    if not math.isfinite(angle) or not 0 <= angle < 360:
        raise ValueError("nmea_heading_out_of_range")
    return angle


def _signed_direction(value: str, hemisphere: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise ValueError("nmea_variation_invalid") from None
    if not math.isfinite(number) or not 0 <= number <= 180 or hemisphere not in {"E", "W"}:
        raise ValueError("nmea_variation_invalid")
    return number if hemisphere == "E" else -number


class Nmea0183Parser:
    """Strict subset parser for GGA/RMC GNSS fixes and HDT/HDM/HDG headings."""

    def __init__(self, *, magnetic_declination_degrees: float | None = None):
        if magnetic_declination_degrees is not None:
            if (
                isinstance(magnetic_declination_degrees, bool)
                or not isinstance(magnetic_declination_degrees, (int, float))
                or not math.isfinite(float(magnetic_declination_degrees))
                or not -180 <= float(magnetic_declination_degrees) <= 180
            ):
                raise ValueError("magnetic_declination_degrees must be finite and in [-180, 180]")
            magnetic_declination_degrees = float(magnetic_declination_degrees)
        self.magnetic_declination_degrees = magnetic_declination_degrees
        self.fix: NmeaFix | None = None
        self.heading: NmeaHeading | None = None
        self._rmc_date: date | None = None
        self._rmc_time: float | None = None
        self._rmc_active = False
        self._rmc_position: tuple[float, float] | None = None
        self._gga: tuple[float, float, float, int, int, float] | None = None
        self._rmc_received_monotonic: float | None = None
        self._gga_received_monotonic: float | None = None

    @staticmethod
    def _pair_distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
        latitude = math.radians((a[0] + b[0]) / 2)
        north = (a[0] - b[0]) * 111_132.0
        east = (a[1] - b[1]) * 111_320.0 * math.cos(latitude)
        return math.hypot(north, east)

    def _refresh_fix(self, received_monotonic: float) -> None:
        if (
            not self._rmc_active
            or self._rmc_date is None
            or self._rmc_time is None
            or self._rmc_position is None
            or self._gga is None
            or self._rmc_received_monotonic is None
            or self._gga_received_monotonic is None
        ):
            self.fix = None
            return

        gga_time, latitude, longitude, quality, satellites, hdop = self._gga
        time_difference = abs(gga_time - self._rmc_time)
        time_difference = min(time_difference, 86_400.0 - time_difference)
        if time_difference > 1.0:
            self.fix = None
            return
        if abs(self._gga_received_monotonic - self._rmc_received_monotonic) > 2.0:
            self.fix = None
            return
        if self._pair_distance_m((latitude, longitude), self._rmc_position) > 250.0:
            self.fix = None
            return
        # Accept autonomous/DGPS/PPS/RTK fixes only. Dead-reckoning,
        # manual and simulated GGA quality codes are not GNSS station fixes.
        if quality not in {1, 2, 3, 4, 5} or satellites <= 0 or hdop <= 0 or not math.isfinite(hdop):
            self.fix = None
            return

        hour = int(gga_time // 3600)
        minute = int((gga_time % 3600) // 60)
        seconds_float = gga_time - hour * 3600 - minute * 60
        second = int(seconds_float)
        microsecond = int(round((seconds_float - second) * 1_000_000))
        if microsecond >= 1_000_000:
            second += 1
            microsecond -= 1_000_000
        base_date = datetime(
            self._rmc_date.year, self._rmc_date.month, self._rmc_date.day,
            tzinfo=timezone.utc,
        )
        rmc_stamp = base_date + timedelta(seconds=self._rmc_time)
        gga_candidates = [
            base_date + timedelta(days=day_offset, seconds=gga_time)
            for day_offset in (-1, 0, 1)
        ]
        captured = min(gga_candidates, key=lambda candidate: abs((candidate - rmc_stamp).total_seconds()))
        if captured.microsecond != microsecond:
            captured = captured.replace(microsecond=microsecond)
        self.fix = NmeaFix(
            latitude_degrees=latitude,
            longitude_degrees=longitude,
            captured_at=captured,
            fix_quality=quality,
            satellites=satellites,
            hdop=hdop,
            received_monotonic=received_monotonic,
        )

    def feed(self, sentence: str | bytes, *, received_monotonic: float | None = None) -> bool:
        """Parse one checksummed sentence; return True if supported data changed."""
        received = time.monotonic() if received_monotonic is None else float(received_monotonic)
        if not math.isfinite(received) or received < 0:
            raise ValueError("received_monotonic_invalid")
        body = _checksum_body(sentence)
        fields = body.split(",")
        identifier = fields[0]
        kind = identifier[-3:] if len(identifier) >= 5 else ""
        if not re.fullmatch(r"[A-Z0-9]{5}", identifier):
            raise ValueError("nmea_talker_invalid")

        if kind == "RMC":
            if len(fields) < 10:
                raise ValueError("nmea_rmc_fields_missing")
            time_value, time_parts = _parse_time_of_day(fields[1])
            status = fields[2]
            if status != "A":
                self._rmc_active = False
                self._rmc_received_monotonic = None
                self.fix = None
                return True
            latitude = _coordinate(fields[3], fields[4], latitude=True)
            longitude = _coordinate(fields[5], fields[6], latitude=False)
            parsed_date = _parse_date(fields[9])
            mode = fields[12] if len(fields) > 12 else ""
            if mode.upper() == "N":
                self._rmc_active = False
                self._rmc_received_monotonic = None
                self.fix = None
                return True
            self._rmc_date = parsed_date
            self._rmc_time = time_value
            self._rmc_position = (latitude, longitude)
            self._rmc_received_monotonic = received
            self._rmc_active = True
            self._refresh_fix(received)
            return True

        if kind == "GGA":
            if len(fields) < 9:
                raise ValueError("nmea_gga_fields_missing")
            time_value, _ = _parse_time_of_day(fields[1])
            latitude = _coordinate(fields[2], fields[3], latitude=True)
            longitude = _coordinate(fields[4], fields[5], latitude=False)
            try:
                quality = int(fields[6])
                satellites = int(fields[7])
                hdop = float(fields[8])
            except ValueError:
                raise ValueError("nmea_gga_quality_invalid") from None
            if quality < 0 or quality > 8 or satellites < 0 or satellites > 99:
                raise ValueError("nmea_gga_quality_out_of_range")
            if not math.isfinite(hdop) or hdop < 0 or hdop > 100:
                raise ValueError("nmea_gga_hdop_out_of_range")
            self._gga = (time_value, latitude, longitude, quality, satellites, hdop)
            self._gga_received_monotonic = received
            self._refresh_fix(received)
            return True

        if kind == "HDT":
            if len(fields) < 3 or fields[2] != "T":
                raise ValueError("nmea_hdt_reference_invalid")
            self.heading = NmeaHeading(_angle(fields[1]), "HDT_TRUE", received)
            return True

        if kind == "HDM":
            if len(fields) < 3 or fields[2] != "M":
                raise ValueError("nmea_hdm_reference_invalid")
            if self.magnetic_declination_degrees is None:
                return False
            angle = (_angle(fields[1]) + self.magnetic_declination_degrees) % 360.0
            self.heading = NmeaHeading(angle, "HDM_WITH_CONFIGURED_DECLINATION", received)
            return True

        if kind == "HDG":
            if len(fields) < 6:
                raise ValueError("nmea_hdg_fields_missing")
            if not fields[2] or not fields[3] or not fields[4] or not fields[5]:
                raise ValueError("nmea_hdg_corrections_missing")
            magnetic = _angle(fields[1])
            deviation = _signed_direction(fields[2], fields[3])
            variation = _signed_direction(fields[4], fields[5])
            self.heading = NmeaHeading(
                (magnetic + deviation + variation) % 360.0,
                "HDG_WITH_SENTENCE_CORRECTIONS",
                received,
            )
            return True

        return False


class NmeaSerialAdapter:
    """Optional serial NMEA adapter. Exact GNSS position never leaves this process."""

    def __init__(
        self,
        *,
        port: str,
        station_id: str,
        permission_granted: bool,
        calibrated_heading_accuracy_degrees: float,
        baudrate: int = 4800,
        read_timeout_seconds: float = 1.0,
        maximum_fix_age_seconds: float = 3.0,
        maximum_pair_skew_seconds: float = 2.0,
        minimum_satellites: int = 4,
        maximum_hdop: float = 5.0,
        magnetic_declination_degrees: float | None = None,
        serial_factory: Callable[..., Any] | None = None,
        parser: Nmea0183Parser | None = None,
    ):
        if type(permission_granted) is not bool or not permission_granted:
            raise AdapterConfigurationError("serial_device_permission_not_granted")
        if not isinstance(port, str) or not port.strip() or len(port) > 128 or "://" in port:
            raise ValueError("serial port must be an explicit local device path")
        if not isinstance(station_id, str) or not 1 <= len(station_id.strip()) <= 80:
            raise ValueError("station_id must be a non-empty identifier up to 80 characters")
        for name, value in (
            ("calibrated_heading_accuracy_degrees", calibrated_heading_accuracy_degrees),
            ("maximum_fix_age_seconds", maximum_fix_age_seconds),
            ("maximum_pair_skew_seconds", maximum_pair_skew_seconds),
            ("maximum_hdop", maximum_hdop),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
        if not 0.5 <= float(calibrated_heading_accuracy_degrees) <= 45:
            raise ValueError("calibrated heading sigma must be within 0.5..45 degrees")
        if not 0.2 <= float(read_timeout_seconds) <= 5:
            raise ValueError("serial read timeout must be between 0.2 and 5 seconds")
        if not 0.5 <= float(maximum_fix_age_seconds) <= 30:
            raise ValueError("maximum fix age must be between 0.5 and 30 seconds")
        if not 0.1 <= float(maximum_pair_skew_seconds) <= 10:
            raise ValueError("maximum pair skew must be between 0.1 and 10 seconds")
        if type(baudrate) is not int or baudrate not in {4800, 9600, 19200, 38400, 57600, 115200}:
            raise ValueError("unsupported NMEA baudrate")
        if type(minimum_satellites) is not int or not 3 <= minimum_satellites <= 32:
            raise ValueError("minimum_satellites must be between 3 and 32")
        if not 0.5 <= float(maximum_hdop) <= 20:
            raise ValueError("maximum_hdop must be between 0.5 and 20")

        self.port = port.strip()
        self.station_id = station_id.strip()
        self.baudrate = baudrate
        self.read_timeout_seconds = float(read_timeout_seconds)
        self.maximum_fix_age_seconds = float(maximum_fix_age_seconds)
        self.maximum_pair_skew_seconds = float(maximum_pair_skew_seconds)
        self.minimum_satellites = minimum_satellites
        self.maximum_hdop = float(maximum_hdop)
        self.calibrated_heading_accuracy_degrees = float(calibrated_heading_accuracy_degrees)
        self.serial_factory = serial_factory
        self.parser = parser or Nmea0183Parser(
            magnetic_declination_degrees=magnetic_declination_degrees
        )
        self._serial = None
        self._started = False
        self._last_emitted: tuple[datetime, float] | None = None

    async def discover(self) -> bool:
        if self.serial_factory is None:
            try:
                import serial
            except ImportError:
                raise AdapterConfigurationError("pyserial_optional_dependency_missing") from None
            self.serial_factory = serial.Serial
        return callable(self.serial_factory)

    async def capabilities(self) -> Mapping[str, bool]:
        return {"nmea_serial": callable(self.serial_factory), "nmea0183_parser": True}

    async def permissions(self) -> Mapping[str, bool]:
        # Explicit constructor consent is required before serial opening.
        return {"serial_device_access": True}

    async def start(self) -> None:
        if not callable(self.serial_factory):
            raise AdapterConfigurationError("nmea_adapter_not_discovered")
        try:
            self._serial = self.serial_factory(
                self.port,
                baudrate=self.baudrate,
                timeout=self.read_timeout_seconds,
                write_timeout=1.0,
            )
        except Exception:
            raise AdapterTransientError("nmea_serial_open_failed") from None
        if self._serial is None or getattr(self._serial, "is_open", True) is not True:
            self._close_serial()
            raise AdapterTransientError("nmea_serial_open_failed")
        self._started = True

    async def read_event(self, timeout_seconds: float) -> Mapping[str, Any] | None:
        if not self._started or self._serial is None:
            raise AdapterConfigurationError("nmea_serial_not_started")
        try:
            raw = await asyncio.to_thread(
                self._serial.read_until, b"\n", _MAX_SENTENCE_BYTES + 1
            )
        except Exception:
            raise AdapterTransientError("nmea_serial_read_failed") from None
        if not raw:
            return None
        if len(raw) > _MAX_SENTENCE_BYTES:
            return None
        now = time.monotonic()
        try:
            self.parser.feed(raw, received_monotonic=now)
        except ValueError:
            return None

        fix = self.parser.fix
        heading = self.parser.heading
        if fix is None or heading is None:
            return None
        if fix.fix_quality <= 0 or fix.satellites < self.minimum_satellites:
            return None
        if fix.hdop > self.maximum_hdop:
            return None
        if now - fix.received_monotonic > self.maximum_fix_age_seconds:
            return None
        if now - heading.received_monotonic > self.maximum_pair_skew_seconds:
            return None
        if abs(fix.received_monotonic - heading.received_monotonic) > self.maximum_pair_skew_seconds:
            return None
        signature = (fix.captured_at, heading.true_degrees)
        if signature == self._last_emitted:
            return None
        self._last_emitted = signature
        # Coordinates remain in parser.fix only; outbound bearing metadata is
        # explicitly safe for the common metadata-only event supervisor.
        observed_at = fix.captured_at.astimezone(timezone.utc)
        expires_at = observed_at + timedelta(hours=1)
        return {
            "event_id": uuid.uuid4().hex,
            "station_id": self.station_id,
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "event_type": "bearing",
            "candidate_taxon": "unknown",
            "confidence": 0.0,
            "verification_status": "unverified",
            "bearing_deg": round(heading.true_degrees, 4),
            "bearing_sigma_deg": round(self.calibrated_heading_accuracy_degrees, 3),
        }

    async def health(self) -> Mapping[str, Any]:
        return {"healthy": self._started and self._serial is not None and getattr(self._serial, "is_open", True) is True}

    def _close_serial(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            finally:
                self._serial = None

    async def stop(self) -> None:
        self._close_serial()
        self._started = False
