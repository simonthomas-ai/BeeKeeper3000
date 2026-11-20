"""Compact, signed, privacy-minimizing MeshCore channel-data envelope.

Wire format v1 is deliberately smaller than MeshCore's 163-byte binary
channel-data payload limit. Exact GPS coordinates and media are never encoded.
Ed25519 signatures are verified against an explicit public-key allowlist.
"""
from __future__ import annotations

import hashlib
import re
import struct
from datetime import datetime, timezone
from typing import Iterable, Mapping

from Crypto.PublicKey import ECC
from Crypto.Signature import eddsa

MAGIC = b"BK"
VERSION = 1
MAX_WIRE_BYTES = 163
SIGNATURE_BYTES = 64
_HEADER = struct.Struct("<2sBBBBBB16s16s16sII")
_FLAG_BEARING = 0x01
_ALLOWED_FLAGS = _FLAG_BEARING
MAX_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_CLOCK_SKEW_SECONDS = 300

EVENT_TYPES = {"sighting": 1, "bearing": 2, "station_heartbeat": 3, "expert_verification": 4}
EVENT_TYPES_REVERSE = {value: key for key, value in EVENT_TYPES.items()}
TAXA = {"unknown": 0, "Vespa_velutina": 1, "Vespa_crabro": 2, "other": 3}
TAXA_REVERSE = {value: key for key, value in TAXA.items()}
VERIFICATION = {"unverified": 0, "photo_reviewed": 1, "expert_confirmed": 2, "rejected": 3}
VERIFICATION_REVERSE = {value: key for key, value in VERIFICATION.items()}


class MeshCoreProtocolError(ValueError):
    """Invalid or unverifiable BeeKeeper radio envelope."""


def _parse_time(value: object, field: str) -> int:
    if not isinstance(value, str) or len(value) > 40:
        raise MeshCoreProtocolError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MeshCoreProtocolError(f"invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MeshCoreProtocolError(f"{field} must include a timezone")
    epoch = int(parsed.astimezone(timezone.utc).timestamp())
    if not 0 <= epoch <= 0xFFFFFFFF:
        raise MeshCoreProtocolError(f"{field} is outside the wire-format date range")
    return epoch


def _hex_or_hash(value: str, size: int) -> bytes:
    if not isinstance(value, str) or not value or len(value) > 160:
        raise MeshCoreProtocolError("event and station identifiers must be non-empty strings")
    if size == 16 and re.fullmatch(r"[0-9a-fA-F]{32}", value):
        return bytes.fromhex(value)
    return hashlib.sha256(value.encode("utf-8")).digest()[:size]


def _private_key(value):
    try:
        key = value if hasattr(value, "curve") else ECC.import_key(value)
    except (ValueError, TypeError, IndexError) as exc:
        raise MeshCoreProtocolError("invalid Ed25519 private key") from exc
    if key.curve != "Ed25519" or not key.has_private():
        raise MeshCoreProtocolError("a private Ed25519 key is required")
    return key


def _public_key(value):
    try:
        key = value if hasattr(value, "curve") else ECC.import_key(value, curve_name="Ed25519")
    except (ValueError, TypeError, IndexError) as exc:
        raise MeshCoreProtocolError("invalid Ed25519 public key") from exc
    if key.curve != "Ed25519":
        raise MeshCoreProtocolError("only Ed25519 public keys are accepted")
    return key.public_key()


def public_key_fingerprint(key) -> str:
    """Return the 16-byte SHA-256 fingerprint used by the wire protocol."""
    if getattr(key, "has_private", lambda: False)():
        public = _private_key(key).public_key()
    else:
        public = _public_key(key)
    raw = public.export_key(format="raw")
    return hashlib.sha256(raw).digest()[:16].hex()


def encode_event(event: Mapping, signing_key, *, key_id: str | None = None,
                 now_epoch: int | None = None) -> bytes:
    """Validate and sign one observation into a compact MeshCore binary payload.

    Transmitted fields are hashes of station/event IDs, timestamps, coded event
    and taxon types, verification claim, confidence and optional bearing only.
    No raw location, image, audio, filename, credential or free text is sent.
    """
    if not isinstance(event, Mapping):
        raise MeshCoreProtocolError("event must be a mapping")
    try:
        event_type = EVENT_TYPES[event["event_type"]]
        taxon = TAXA[event["candidate_taxon"]]
        verification = VERIFICATION[event.get("verification_status", "unverified")]
        station_hash = _hex_or_hash(event["station_id"], 16)
        event_hash = _hex_or_hash(event["event_id"], 16)
    except KeyError as exc:
        raise MeshCoreProtocolError(f"unsupported or missing event field: {exc.args[0]}") from exc

    private = _private_key(signing_key)
    key_fingerprint = hashlib.sha256(private.public_key().export_key(format="raw")).digest()[:16]
    if key_id is not None:
        if not isinstance(key_id, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", key_id):
            raise MeshCoreProtocolError("key_id must be a 32-character public-key fingerprint")
        key_fingerprint = bytes.fromhex(key_id)
        expected = hashlib.sha256(private.public_key().export_key(format="raw")).digest()[:16]
        if key_fingerprint != expected:
            raise MeshCoreProtocolError("key_id does not match the signing key")

    confidence_value = event.get("confidence", 0.0)
    if isinstance(confidence_value, bool) or not isinstance(confidence_value, (int, float)):
        raise MeshCoreProtocolError("confidence must be numeric")
    if not 0 <= float(confidence_value) <= 1:
        raise MeshCoreProtocolError("confidence must be between 0 and 1")
    confidence = round(float(confidence_value) * 100)

    observed = _parse_time(event.get("observed_at"), "observed_at")
    expires = _parse_time(event.get("expires_at"), "expires_at")
    if expires <= observed or expires - observed > MAX_TTL_SECONDS:
        raise MeshCoreProtocolError("expires_at must be after observed_at and no more than 7 days later")
    now = int(datetime.now(timezone.utc).timestamp()) if now_epoch is None else int(now_epoch)
    if observed > now + MAX_CLOCK_SKEW_SECONDS:
        raise MeshCoreProtocolError("observed_at is too far in the future")
    if expires < now:
        raise MeshCoreProtocolError("event has expired")

    flags = 0
    extension = b""
    if event_type == EVENT_TYPES["bearing"] or "bearing_deg" in event or "bearing_sigma_deg" in event:
        if "bearing_deg" not in event or "bearing_sigma_deg" not in event:
            raise MeshCoreProtocolError("bearing events require bearing_deg and bearing_sigma_deg")
        bearing = event["bearing_deg"]
        sigma = event["bearing_sigma_deg"]
        if isinstance(bearing, bool) or not isinstance(bearing, (int, float)) or not 0 <= bearing < 360:
            raise MeshCoreProtocolError("bearing_deg must be in [0, 360)")
        if isinstance(sigma, bool) or not isinstance(sigma, (int, float)) or not 0.5 <= sigma <= 45:
            raise MeshCoreProtocolError("bearing_sigma_deg must be in [0.5, 45]")
        flags |= _FLAG_BEARING
        extension = struct.pack("<HH", round(float(bearing) * 100), round(float(sigma) * 100))

    header = _HEADER.pack(
        MAGIC, VERSION, flags, event_type, taxon, verification, confidence,
        station_hash, key_fingerprint, event_hash, observed, expires
    )
    signed = header + extension
    signature = eddsa.new(private, mode="rfc8032").sign(signed)
    payload = signed + signature
    if len(payload) > MAX_WIRE_BYTES:
        raise MeshCoreProtocolError("encoded event exceeds MeshCore's 163-byte channel-data limit")
    return payload


def decode_event(payload: bytes, trusted_public_keys: Mapping[str, object], *,
                 trusted_expert_fingerprints: Iterable[str] = (),
                 now_epoch: int | None = None) -> dict:
    """Verify a received envelope and return a normalized event.

    Unknown keys and invalid signatures are rejected. An expert-confirmed claim
    is downgraded unless its key is explicitly in the expert trust allowlist.
    """
    if not isinstance(payload, (bytes, bytearray)):
        raise MeshCoreProtocolError("payload must be bytes")
    payload = bytes(payload)
    if len(payload) < _HEADER.size + SIGNATURE_BYTES or len(payload) > MAX_WIRE_BYTES:
        raise MeshCoreProtocolError("invalid MeshCore event length")
    try:
        (magic, version, flags, event_code, taxon_code, verification_code,
         confidence, station_hash, key_fingerprint, event_hash,
         observed, expires) = _HEADER.unpack_from(payload)
    except struct.error as exc:
        raise MeshCoreProtocolError("truncated event header") from exc

    if magic != MAGIC or version != VERSION:
        raise MeshCoreProtocolError("unsupported MeshCore event magic/version")
    if flags & ~_ALLOWED_FLAGS:
        raise MeshCoreProtocolError("unknown event flags")
    if event_code not in EVENT_TYPES_REVERSE or taxon_code not in TAXA_REVERSE or verification_code not in VERIFICATION_REVERSE:
        raise MeshCoreProtocolError("unknown event/taxon/verification code")

    extension_size = 4 if flags & _FLAG_BEARING else 0
    signed_size = _HEADER.size + extension_size
    if len(payload) != signed_size + SIGNATURE_BYTES:
        raise MeshCoreProtocolError("event length does not match flags")
    signed, signature = payload[:signed_size], payload[signed_size:]

    fingerprint = key_fingerprint.hex()
    candidate_key = trusted_public_keys.get(fingerprint)
    if candidate_key is None:
        raise MeshCoreProtocolError("signing key is not trusted")
    public = _public_key(candidate_key)
    expected_fingerprint = hashlib.sha256(public.export_key(format="raw")).digest()[:16].hex()
    if expected_fingerprint != fingerprint:
        raise MeshCoreProtocolError("public-key fingerprint mismatch")
    try:
        eddsa.new(public, mode="rfc8032").verify(signed, signature)
    except (ValueError, TypeError) as exc:
        raise MeshCoreProtocolError("invalid Ed25519 signature") from exc

    now = int(datetime.now(timezone.utc).timestamp()) if now_epoch is None else int(now_epoch)
    if expires <= observed or expires - observed > MAX_TTL_SECONDS:
        raise MeshCoreProtocolError("invalid event expiry")
    if expires < now:
        raise MeshCoreProtocolError("event has expired")
    if observed > now + MAX_CLOCK_SKEW_SECONDS:
        raise MeshCoreProtocolError("event timestamp is too far in the future")

    bearing = {}
    if flags & _FLAG_BEARING:
        bearing_cdeg, sigma_cdeg = struct.unpack_from("<HH", payload, _HEADER.size)
        if bearing_cdeg >= 36000 or not 50 <= sigma_cdeg <= 4500:
            raise MeshCoreProtocolError("invalid bearing extension")
        bearing = {"bearing_deg": bearing_cdeg / 100, "bearing_sigma_deg": sigma_cdeg / 100}

    verification_status = VERIFICATION_REVERSE[verification_code]
    if (verification_status == "expert_confirmed" and
            fingerprint not in set(trusted_expert_fingerprints)):
        verification_status = "unverified"

    return {
        "schema_version": VERSION,
        "event_id": event_hash.hex(),
        "station_id": station_hash.hex(),
        "observed_at": datetime.fromtimestamp(observed, timezone.utc).isoformat().replace("+00:00", "Z"),
        "expires_at": datetime.fromtimestamp(expires, timezone.utc).isoformat().replace("+00:00", "Z"),
        "event_type": EVENT_TYPES_REVERSE[event_code],
        "candidate_taxon": TAXA_REVERSE[taxon_code],
        "confidence": confidence / 100,
        "verification_status": verification_status,
        "signature_key_id": fingerprint,
        "signature": signature.hex(),
        **bearing,
    }
