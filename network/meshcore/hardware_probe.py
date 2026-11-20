"""Safe MeshCore companion-radio probe.

Default mode only signs and sizes a synthetic heartbeat packet; it does not
open a serial port or transmit. --probe opens the configured radio but sends
nothing. A packet is sent only with --transmit-test-packet.
"""
from __future__ import annotations
import argparse, asyncio, os, stat, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from Crypto.PublicKey import ECC
from .protocol import encode_event, public_key_fingerprint, MAX_WIRE_BYTES
from .transport import MeshCoreSerialTransport, MeshCoreTransportError

def load_private_key(path: str):
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise ValueError("signing key must not be a symbolic link")
    target = candidate.resolve(strict=True)
    details = target.stat()
    if not stat.S_ISREG(details.st_mode):
        raise ValueError("signing key must be a regular file")
    if os.name == "posix":
        if details.st_uid != os.getuid():
            raise PermissionError("signing key must belong to the current service account")
        if stat.S_IMODE(details.st_mode) & 0o077:
            raise PermissionError("signing key permissions must be owner-only (0600 or stricter)")
    key = ECC.import_key(target.read_bytes())
    if key.curve != "Ed25519" or not key.has_private():
        raise ValueError("a private Ed25519 signing key is required")
    return key

def make_test_event(station_id: str, *, now: datetime | None = None) -> dict:
    if not isinstance(station_id, str) or not station_id.strip() or len(station_id) > 128:
        raise ValueError("station_id must be a non-empty identifier up to 128 characters")
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("test event time must be timezone-aware")
    observed = moment.astimezone(timezone.utc)
    expires = observed + timedelta(minutes=5)
    return {
        "event_id": "hardware-probe-" + uuid4().hex,
        "station_id": station_id,
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
        "event_type": "station_heartbeat",
        "candidate_taxon": "unknown",
        "verification_status": "unverified",
        "confidence": 0.0,
    }

async def run_probe(args) -> dict:
    key = load_private_key(args.signing_key)
    event = make_test_event(args.station_id)
    payload = encode_event(event, key)
    if len(payload) > MAX_WIRE_BYTES:
        raise RuntimeError("signed test packet exceeds MeshCore channel-data limit")
    result = {
        "mode": "transmit" if args.transmit_test_packet else "connect" if args.probe else "dry_run",
        "station_id": args.station_id,
        "port": args.port,
        "channel": args.channel,
        "data_type": args.data_type,
        "packet_bytes": len(payload),
        "packet_limit_bytes": MAX_WIRE_BYTES,
        "signing_key_fingerprint": public_key_fingerprint(key),
        "event_id": event["event_id"],
        "transmitted": False,
    }
    if not args.probe:
        return result
    transport = MeshCoreSerialTransport(
        port=args.port, channel=args.channel, data_type=args.data_type,
        station_id=args.station_id, signing_key=key, baudrate=args.baudrate,
    )
    await transport.connect()
    try:
        result["serial_connected"] = True
        if args.transmit_test_packet:
            receipt = await transport.send_event(event)
            result["transmitted"] = True
            result["local_send_receipt"] = receipt
    finally:
        await transport.disconnect()
    return result

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BeeKeeper3000 MeshCore hardware probe")
    parser.add_argument("--port", required=True, help="Serial port, e.g. COM5 or /dev/ttyUSB0")
    parser.add_argument("--station-id", required=True)
    parser.add_argument("--signing-key", required=True, help="Path to owner-only private Ed25519 key")
    parser.add_argument("--channel", type=int, default=0)
    parser.add_argument("--data-type", type=lambda value: int(value, 0), default=0xB301)
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--probe", action="store_true", help="Open and close serial radio; do not transmit")
    parser.add_argument("--transmit-test-packet", action="store_true",
                        help="Transmit exactly one synthetic heartbeat; requires --probe")
    return parser

def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.channel not in range(256):
        parser.error("--channel must be in 0..255")
    if not 1 <= args.data_type <= 65535:
        parser.error("--data-type must be in 1..65535")
    if not 300 <= args.baudrate <= 2_000_000:
        parser.error("--baudrate must be in 300..2000000")
    if args.transmit_test_packet and not args.probe:
        parser.error("--transmit-test-packet requires --probe")
    try:
        report = asyncio.run(run_probe(args))
    except (OSError, ValueError, RuntimeError, MeshCoreTransportError) as exc:
        print(f"MeshCore probe failed: {exc}", file=sys.stderr)
        return 2
    import json
    print(json.dumps(report, indent=2))
    if args.transmit_test_packet:
        print("LOCAL SEND ONLY: remote reception is not proven.", file=sys.stderr)
    elif args.probe:
        print("CONNECTED ONLY: no radio packet was transmitted.", file=sys.stderr)
    else:
        print("DRY RUN ONLY: no serial port was opened and nothing was transmitted.", file=sys.stderr)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
