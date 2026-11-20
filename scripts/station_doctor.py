#!/usr/bin/env python3
"""Read-only BeeKeeper station preflight. Hardware probes are opt-in and never transmit."""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from types import SimpleNamespace


@dataclass
class Check:
    name: str
    status: str
    detail: str


class Report:
    def __init__(self) -> None:
        self.checks: list[Check] = []

    def add(self, name: str, status: str, detail: str) -> None:
        self.checks.append(Check(name, status, detail))

    @property
    def failed(self) -> bool:
        return any(item.status == "FAIL" for item in self.checks)

    def render(self, as_json: bool = False) -> None:
        if as_json:
            print(json.dumps({
                "status": "FAIL" if self.failed else "PASS_WITH_WARNINGS"
                if any(x.status == "WARN" for x in self.checks) else "PASS",
                "checks": [asdict(item) for item in self.checks],
            }, ensure_ascii=False, indent=2))
            return
        for item in self.checks:
            print(f"[{item.status:4}] {item.name}: {item.detail}")
        summary = "FAIL" if self.failed else (
            "PASS WITH WARNINGS" if any(x.status == "WARN" for x in self.checks) else "PASS"
        )
        print(f"\nBeeKeeper station preflight: {summary}")


def _version(command: str) -> tuple[int, ...] | None:
    executable = shutil.which(command)
    if not executable:
        return None
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True,
            timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (result.stdout or result.stderr).strip()
    import re
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    if result.returncode != 0 or not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def _is_loopback_url(value: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        host = parsed.hostname.lower()
        if host == "localhost":
            return True
        return socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80),
                                  type=socket.SOCK_STREAM) and all(
            item[4][0].split("%")[0] in {"127.0.0.1", "::1"}
            for item in socket.getaddrinfo(
                host, parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        )
    except (OSError, ValueError):
        return False


def _request(url: str, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            data = response.read(65537)
            if len(data) > 65536:
                raise ValueError("response exceeds 64 KiB preflight limit")
            return int(response.status), data
    except urllib.error.HTTPError as exc:
        body = exc.read(65537)
        return int(exc.code), body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ConnectionError(type(exc).__name__) from None


def _append_path(base: str, suffix: str) -> str:
    return base.rstrip("/") + suffix


def check_repositories(report: Report, root: Path, monitor: Path | None) -> None:
    required = (
        "network/source_api.py",
        "monitor-bridge/bridge.mjs",
        "camera/runtime.py",
        "camera/model_manifest.py",
        "network/meshcore/hardware_probe.py",
        "scripts/install-linux.sh",
        "scripts/Start-BeeKeeperStation.ps1",
    )
    missing = [name for name in required if not (root / name).is_file()]
    report.add(
        "BeeKeeper3000 repository",
        "FAIL" if missing else "PASS",
        "missing: " + ", ".join(missing) if missing else "required station modules and launchers are present",
    )
    if monitor is None:
        report.add("Beekeeper-Monitor repository", "WARN", "checkout not found; pass --monitor-repo to verify it")
        return
    monitor_required = (
        "integrations/local_ingest.py",
        "integrations/event_contracts.py",
        "integrations/event_store.py",
        "integrations/store_backup.py",
    )
    missing = [name for name in monitor_required if not (monitor / name).is_file()]
    report.add(
        "Beekeeper-Monitor repository",
        "FAIL" if missing else "PASS",
        "missing: " + ", ".join(missing) if missing else "receiver, strict event contract, storage and backup modules are present",
    )


def check_versions(report: Report) -> None:
    py = sys.version_info
    report.add(
        "Python runtime",
        "PASS" if py.major == 3 and py.minor >= 11 else "FAIL",
        f"Python {py.major}.{py.minor}.{py.micro}" + ("" if py.minor >= 11 else "; version 3.11+ required"),
    )
    node = _version("node")
    if node is None:
        report.add("Node.js runtime", "FAIL", "Node.js 20+ is required for the bridge; executable not found or version unreadable")
    else:
        report.add("Node.js runtime", "PASS" if node[0] >= 20 else "FAIL",
                   f"Node.js {'.'.join(map(str, node))}" + ("" if node[0] >= 20 else "; version 20+ required"))


def check_bridge_config(report: Report) -> None:
    require_cursor = os.environ.get("BRIDGE_REQUIRE_CURSOR", "").strip().lower()
    if require_cursor == "true":
        report.add("Bridge cursor safety", "PASS", "BRIDGE_REQUIRE_CURSOR=true")
    elif require_cursor == "false":
        report.add("Bridge cursor safety", "FAIL", "lossy latest-only compatibility mode is disabled for operational use")
    else:
        report.add("Bridge cursor safety", "WARN", "BRIDGE_REQUIRE_CURSOR is not visible in this shell; deployment must set it to true")
    state_file = os.environ.get("BRIDGE_STATE_FILE", "").strip()
    if state_file:
        path = Path(state_file).expanduser()
        if path.exists() and path.is_dir():
            report.add("Bridge checkpoint path", "FAIL", "configured checkpoint path is a directory")
        else:
            parent = path.parent
            report.add("Bridge checkpoint path", "PASS" if parent.exists() else "WARN",
                       "configured path is present" if parent.exists() else "parent directory does not exist yet")
    else:
        report.add("Bridge checkpoint path", "WARN", "BRIDGE_STATE_FILE is not visible in this shell; verify persistent protected storage")


def check_services(report: Report, source_url: str, monitor_ingest_url: str) -> None:
    source_key = os.environ.get("HORNET3000_API_KEY", "")
    monitor_token = os.environ.get("BEEKEEPER_MONITOR_INGEST_TOKEN") or os.environ.get("VESPAGUARD_INGEST_TOKEN", "")
    source_base = source_url.rstrip("/")
    monitor_base = monitor_ingest_url.removesuffix("/api/v1/events").rstrip("/")
    for name, url in (("Source API", source_base + "/api/events?limit=1&cursor=start"),
                      ("Monitor receiver", monitor_base + "/api/v1/events?limit=1")):
        if not _is_loopback_url(url):
            report.add(name + " endpoint", "FAIL", "only HTTP(S) loopback endpoints are permitted by this preflight")
            continue
        headers: dict[str, str] = {}
        if name == "Source API" and source_key:
            headers["X-API-Key"] = source_key
        if name == "Monitor receiver" and monitor_token:
            headers["Authorization"] = "Bearer " + monitor_token
        try:
            status, body = _request(url, headers)
            if status == 200:
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (UnicodeError, json.JSONDecodeError):
                    payload = None
                if name == "Source API":
                    valid = isinstance(payload, dict) and isinstance(payload.get("events"), list) and isinstance(payload.get("next_cursor"), str)
                else:
                    valid = isinstance(payload, dict) and isinstance(payload.get("events"), list)
                report.add(name + " authenticated read", "PASS" if valid else "FAIL",
                           "authenticated read-only endpoint returned the expected bounded JSON contract" if valid
                           else "HTTP 200 but response did not match the expected JSON contract")
            elif status == 401 and not (source_key if name == "Source API" else monitor_token):
                report.add(name + " authenticated read", "WARN", "service is reachable, but its token is not available in this shell; authentication was not verified")
            else:
                report.add(name + " authenticated read", "FAIL", f"service returned HTTP {status}")
        except ConnectionError as exc:
            report.add(name + " authenticated read", "FAIL", f"loopback service unavailable ({exc}); check process/service and local firewall")


def check_model(report: Report, root: Path, manifest_arg: str | None) -> None:
    manifest_value = manifest_arg or os.environ.get("BEEKEEPER_MODEL_MANIFEST", "").strip()
    if not manifest_value:
        report.add("Camera model manifest", "WARN", "no model configured; camera AI remains disabled")
        return
    try:
        sys.path.insert(0, str(root))
        from camera.model_manifest import load_manifest
        manifest = load_manifest(manifest_value, verify_model=True)
        report.add("Camera model manifest", "PASS",
                   "model file hash, path confinement, source metadata and license-review gate passed")
        try:
            import onnxruntime
            available = "CPUExecutionProvider" in onnxruntime.get_available_providers()
            report.add("ONNX Runtime CPU", "PASS" if available else "FAIL",
                       "CPUExecutionProvider available" if available else "CPUExecutionProvider missing")
        except ImportError:
            report.add("ONNX Runtime CPU", "FAIL", "onnxruntime is not installed in this Python environment")
        _ = manifest
    except Exception as exc:
        report.add("Camera model manifest", "FAIL", f"model manifest validation failed ({type(exc).__name__}); details omitted to avoid leaking local paths")


def check_camera(report: Report, source: str | None) -> None:
    if not source:
        report.add("Live camera test", "WARN", "skipped; pass --test-camera and --camera-source to open the configured source and read one frame")
        return
    try:
        import cv2
        from camera.runtime import _capture_source
        capture = _capture_source(source)
        try:
            if not capture.isOpened():
                raise RuntimeError("camera did not open")
            ok, frame = capture.read()
            if not ok or frame is None or not hasattr(frame, "shape"):
                raise RuntimeError("camera returned no frame")
            report.add("Live camera test", "PASS", f"camera opened and returned one frame ({frame.shape[1]}x{frame.shape[0]}); frame not saved")
        finally:
            capture.release()
    except Exception as exc:
        report.add("Live camera test", "FAIL", f"camera could not be verified ({type(exc).__name__}); source URL and credentials are not printed")


def check_radio(report: Report, port: str | None, station_id: str | None, signing_key: str | None) -> None:
    if not port:
        report.add("MeshCore hardware test", "WARN", "skipped; pass --probe-radio, --radio-port, --station-id and --signing-key for connect-only test")
        return
    if not station_id or not signing_key:
        report.add("MeshCore hardware test", "FAIL", "station ID and private key path are required for a connect-only probe")
        return
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from network.meshcore.hardware_probe import run_probe
        args = SimpleNamespace(
            port=port, station_id=station_id, signing_key=signing_key,
            channel=0, data_type=0xB301, baudrate=115200,
            probe=True, transmit_test_packet=False,
        )
        result = asyncio.run(run_probe(args))
        if result.get("serial_connected") is True and result.get("transmitted") is False:
            report.add("MeshCore hardware test", "PASS", "radio serial connected and closed; no packet transmitted")
        else:
            report.add("MeshCore hardware test", "FAIL", "radio probe did not confirm a connect-only result")
    except Exception as exc:
        report.add("MeshCore hardware test", "FAIL", f"connect-only probe failed ({type(exc).__name__}); key and port details omitted")


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Read-only BeeKeeper3000 station checks. No data is written or transmitted."
    )
    parser.add_argument("--monitor-repo", default=os.environ.get("BEEKEEPER_MONITOR_REPO", ""))
    parser.add_argument("--source-url", default=os.environ.get("HORNET3000_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--monitor-ingest-url", default=os.environ.get("BEEKEEPER_MONITOR_INGEST_URL", "http://127.0.0.1:8765/api/v1/events"))
    parser.add_argument("--model-manifest", default=None)
    parser.add_argument("--test-camera", action="store_true", help="Explicitly open the configured camera and read one frame")
    parser.add_argument("--camera-source", default=None, help="Camera index, local file or RTSP(S)/HTTP(S) source; never printed")
    parser.add_argument("--probe-radio", action="store_true", help="Explicitly connect to MeshCore; sends no packet")
    parser.add_argument("--radio-port", default=None)
    parser.add_argument("--station-id", default=os.environ.get("HORNET3000_STATION_ID", None))
    parser.add_argument("--signing-key", default=None, help="Path to a private Ed25519 test key; never printed")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    monitor_value = args.monitor_repo.strip()
    if not monitor_value:
        sibling = root.parent / "Beekeeper-Monitor"
        monitor = sibling.resolve() if (sibling / "integrations" / "local_ingest.py").is_file() else None
    else:
        try:
            monitor = Path(monitor_value).expanduser().resolve(strict=True)
        except OSError:
            monitor = None
    report = Report()
    check_repositories(report, root, monitor)
    check_versions(report)
    check_bridge_config(report)
    check_services(report, args.source_url, args.monitor_ingest_url)
    check_model(report, root, args.model_manifest)
    if args.test_camera:
        if not args.camera_source and not os.environ.get("BEEKEEPER_CAMERA_SOURCE"):
            report.add("Live camera test", "FAIL", "--test-camera requires --camera-source or BEEKEEPER_CAMERA_SOURCE")
        else:
            check_camera(report, args.camera_source or os.environ.get("BEEKEEPER_CAMERA_SOURCE"))
    else:
        report.add("Live camera test", "WARN", "skipped; --test-camera is required to access a camera")
    if args.probe_radio:
        check_radio(report, args.radio_port, args.station_id, args.signing_key)
    else:
        report.add("MeshCore hardware test", "WARN", "skipped; radio access is opt-in and no packet is ever transmitted")
    report.render(args.json)
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
