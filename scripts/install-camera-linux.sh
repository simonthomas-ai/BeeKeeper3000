#!/usr/bin/env bash
# Prepare optional local camera runtime; does not download model weights.
set -Eeuo pipefail

START=0
while (($#)); do
  case "$1" in
    --start) START=1; shift ;;
    --help|-h)
      echo "Usage: sudo bash scripts/install-camera-linux.sh [--start]"
      echo "Prepares the optional camera venv and systemd unit. --start also enables it at boot."
      exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 1 ;;
  esac
done
die() { echo "ERROR: $*" >&2; exit 1; }
[[ "$EUID" -eq 0 ]] || die "Run with sudo/root."
for cmd in systemctl getent usermod install sed grep stat; do
  command -v "$cmd" >/dev/null 2>&1 || die "Required command missing: $cmd"
done
[[ -d /run/systemd/system ]] || die "systemd is not running."
APP_ROOT=/opt/beekeeper3000/current
STATE_ROOT=/var/lib/beekeeper3000
CONFIG_ROOT=/etc/beekeeper3000
STATION_ENV=$CONFIG_ROOT/station.env
CAMERA_ENV=$CONFIG_ROOT/camera.env
MODEL_DIR=$STATE_ROOT/models
MANIFEST=$MODEL_DIR/manifest.json
UNIT_TEMPLATE=$APP_ROOT/deploy/systemd/beekeeper-camera.service
UNIT_TARGET=/etc/systemd/system/beekeeper-camera.service
VENV=/opt/beekeeper3000/venv-camera

[[ -L /opt/beekeeper3000/current && -f "$APP_ROOT/camera/runtime.py" ]] || die "BeeKeeper3000 base station is not installed."
[[ -f "$STATION_ENV" ]] || die "Base station secrets file is missing."
[[ -f "$CAMERA_ENV" ]] || die "Create $CAMERA_ENV from docs/camera.env.example first."
[[ -f "$MANIFEST" ]] || die "Place a reviewed ONNX model and manifest at $MANIFEST first."
[[ -f "$UNIT_TEMPLATE" ]] || die "Camera systemd unit template is missing."
[[ -d "$STATE_ROOT" && -d "$MODEL_DIR" ]] || die "Protected station state/model directories are missing."
[[ "$(stat -c '%U:%G:%a' "$STATE_ROOT")" == "beekeeper:beekeeper:700" ]] || die "Station state directory must be beekeeper:beekeeper mode 0700."
[[ "$(stat -c '%U:%G:%a' "$MODEL_DIR")" == "beekeeper:beekeeper:750" ]] || die "Model directory must be beekeeper:beekeeper mode 0750."

grep -qE '^HORNET3000_API_KEY=[A-Za-z0-9_-]{32,}$' "$STATION_ENV" || die "Station API key is missing or invalid."
for key in BEEKEEPER_CAMERA_SOURCE HORNET3000_STATION_ID BEEKEEPER_MODEL_MANIFEST BEEKEEPER_CAMERA_OUTBOX; do
  grep -qE "^$key=.+$" "$CAMERA_ENV" || die "Camera configuration is missing $key."
done
grep -qE '^BEEKEEPER_MODEL_MANIFEST=/var/lib/beekeeper3000/models/manifest\.json$' "$CAMERA_ENV" || die "Model manifest must be in the protected station model directory."
grep -qE '^BEEKEEPER_CAMERA_OUTBOX=/var/lib/beekeeper3000/camera-outbox\.sqlite3$' "$CAMERA_ENV" || die "Camera outbox must be in the protected station state directory."
chown root:beekeeper "$CAMERA_ENV"
chmod 0640 "$CAMERA_ENV"

camera_source=$(sed -n 's/^BEEKEEPER_CAMERA_SOURCE=//p' "$CAMERA_ENV" | tail -n 1)
camera_source=${camera_source#\"}
camera_source=${camera_source%\"}
camera_source=${camera_source#\'}
camera_source=${camera_source%\'}
[[ -n "$camera_source" ]] || die "BEEKEEPER_CAMERA_SOURCE is empty."
if [[ "$camera_source" =~ ^[0-9]+$ || "$camera_source" =~ ^/dev/video[0-9]+$ ]]; then
  getent group video >/dev/null || die "Local V4L2 source configured but the video group does not exist."
  usermod -aG video beekeeper
fi

PYTHON=$(command -v python3) || die "Python 3 is required."
PY_MINOR=$("$PYTHON" -c 'import sys; print(sys.version_info.minor if sys.version_info.major == 3 else 0)')
[[ "$PY_MINOR" -ge 11 ]] || die "Python 3.11 or newer is required."
if [[ ! -x "$VENV/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV" || die "Could not create camera virtual environment; install the OS python3-venv package."
fi
"$VENV/bin/python" -m pip install --disable-pip-version-check --requirement "$APP_ROOT/camera/requirements.txt"
PYTHONPATH="$APP_ROOT" "$VENV/bin/python" - <<'PY'
import cv2
import onnxruntime
providers = onnxruntime.get_available_providers()
if "CPUExecutionProvider" not in providers:
    raise SystemExit("ONNX Runtime CPUExecutionProvider is unavailable")
print("Camera dependencies verified:", cv2.__version__, onnxruntime.__version__)
PY
PYTHONPATH="$APP_ROOT" "$VENV/bin/python" - "$MANIFEST" <<'PY'
import sys
from camera.model_manifest import load_manifest
manifest = load_manifest(sys.argv[1], verify_model=True)
print("Reviewed model manifest and SHA-256 verified:", manifest.model_version)
PY

sed -e "s|@BEEKEEPER_ROOT@|$APP_ROOT|g" "$UNIT_TEMPLATE" > "$UNIT_TARGET"
chown root:root "$UNIT_TARGET"
chmod 0644 "$UNIT_TARGET"
systemctl daemon-reload

if ((START)); then
  systemctl enable --now beekeeper-camera.service || die "Camera service could not start; inspect journalctl -u beekeeper-camera."
  systemctl is-active --quiet beekeeper-camera.service || die "Camera service did not remain active."
  echo "Camera service enabled and active."
else
  echo "Camera runtime prepared. It has NOT been started or enabled."
  echo "Review the source and model manifest, then run: sudo systemctl enable --now beekeeper-camera"
fi
echo "Logs: journalctl -u beekeeper-camera -f"
echo "No images or model weights were downloaded by this installer."
