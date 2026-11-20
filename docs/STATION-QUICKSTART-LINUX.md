# BeeKeeper local station — Linux / Raspberry Pi

Status: installable base services; camera and radio remain optional, separately configured components.

The installer provisions three services:

1. **Monitor** — local PWA and authenticated SQLite receiver at 127.0.0.1:8765.
2. **Source API** — authenticated SQLite source journal at 127.0.0.1:8787.
3. **Bridge** — cursor-based metadata delivery from the source journal to the Monitor.

It uses systemd, a dedicated unprivileged beekeeper account, a private state directory, an OS-protected environment file and root-owned versioned application releases. The services bind to loopback and must not be exposed directly to the internet.

## Requirements

- A systemd-based Linux distribution (Debian Bookworm / Raspberry Pi OS Bookworm or newer recommended).
- Python 3.11 or newer.
- Node.js 20 or newer.
- Root access for installation.
- Local clones of both repositories.

The base services use Python and Node standard libraries; optional camera and MeshCore dependencies are not installed by this script.

## Install

From a BeeKeeper3000 checkout with a sibling Beekeeper-Monitor checkout:

~~~sh
sudo bash scripts/install-linux.sh \
  --beekeeper-repo "$PWD" \
  --monitor-repo "../Beekeeper-Monitor"
~~~

The installer creates:

| Path | Purpose |
|---|---|
| /opt/beekeeper3000/current | Active BeeKeeper3000 code release |
| /opt/beekeeper-monitor/current | Active Monitor code release |
| /opt/beekeeper3000/releases and /opt/beekeeper-monitor/releases | Versioned read-only code snapshots; previous releases are retained |
| /var/lib/beekeeper3000 | SQLite databases and bridge checkpoint |
| /etc/beekeeper3000/station.env | API keys and local settings; root-owned, group-readable only by beekeeper, mode 0640 |

Random source API, cursor-signing and Monitor receiver secrets are generated locally and are never printed. The secrets file is reused on upgrades. Database files and the bridge cursor are preserved across code upgrades.

After installation the installer health-checks the Monitor root page and authenticated, cursor-paginated source API. Inspect service state and logs:

~~~sh
systemctl status beekeeper-monitor beekeeper-source-api beekeeper-bridge
journalctl -u beekeeper-monitor -u beekeeper-source-api -u beekeeper-bridge
~~~

Open the PWA locally:

http://127.0.0.1:8765/

## Upgrade

Run the same installer with updated source checkouts. It stops only the BeeKeeper services, stages new versioned code, switches active symlinks atomically, reloads systemd and restarts the stack. Previous code releases remain under /opt; the installer does not delete them or touch station databases.

The existing station.env is reused. Never regenerate the cursor-signing secret while retaining the bridge checkpoint: doing so invalidates the signed source cursor.

## Stop / remove services

Stop the stack:

~~~sh
sudo systemctl disable --now beekeeper-bridge beekeeper-source-api beekeeper-monitor
~~~

To remove only service definitions while preserving every database, key and code release:

~~~sh
sudo rm -f /etc/systemd/system/beekeeper-monitor.service \
  /etc/systemd/system/beekeeper-source-api.service \
  /etc/systemd/system/beekeeper-bridge.service
sudo systemctl daemon-reload
~~~

No destructive data-purge command is provided. Protect the state and configuration directories with encrypted-disk, access-control and backup policies.

## Optional camera runtime

The base installer does **not** install OpenCV / ONNX Runtime, start a camera or enable AI detection. This avoids consuming Raspberry Pi resources or creating false confidence before a model has been reviewed.

After a locally obtained model has passed per-file source/license review, SHA-256 verification, the input/output contract check and human review:

1. Create the protected model directory and place the ONNX file plus manifest there. The manifest must set the licence review to approved/public-domain and carry the exact model hash; the validator rejects unreviewed licences and invalid hashes.
2. Copy docs/camera.env.example to /etc/beekeeper3000/camera.env, edit it with sudoedit, set a station pseudonym and camera source, then set root:beekeeper ownership and mode 0640. Keep RTSP credentials only in this protected file.
3. Run sudo bash scripts/install-camera-linux.sh. This creates an isolated camera virtual environment, installs pinned OpenCV/ONNX Runtime dependencies and verifies the model manifest. It installs the separate systemd unit but does not start it by default.
4. Start only after the operator has checked the camera source and the model's experimental/validation status: sudo systemctl enable --now beekeeper-camera. For a local /dev/video camera, the installer adds the service account to the video group. For RTSP, no local video-device group is needed.
5. Inspect journalctl -u beekeeper-camera -f and confirm stable capture, CPU load, outbox delivery and recovery behaviour before leaving the station unattended.

The optional service uses V4L2 for local Linux cameras, DirectShow for Windows, and FFmpeg for network/file sources. No model weights or camera images are downloaded by the installer. All detections remain candidate events until human review; the service does not make confirmed species or nest-location claims.

## Network, privacy and radio boundaries

- Both HTTP services listen on loopback only. For remote access, use a separately reviewed authenticated TLS VPN/reverse proxy; never port-forward ports 8765 or 8787.
- The bridge transfers bounded metadata, not raw images, video, audio or precise GPS.
- Station event data is sensitive. Use full-disk encryption and station backup tooling; backups are not application-encrypted.
- MeshCore is not installed or started by this base installer. Radio hardware, antennas, airtime, coverage, frequency rules, station bearing calibration and real triangulation require separate field verification.
- A triangulation result is a search hypothesis, not a confirmed nest location.

## Validate without installing

This mode checks repository structure and Python/Node versions without root access, creating secrets or starting processes:

~~~sh
bash scripts/install-linux.sh \
  --beekeeper-repo "$PWD" \
  --monitor-repo "../Beekeeper-Monitor" \
  --validate-only
~~~
