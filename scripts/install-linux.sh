#!/usr/bin/env bash
# Install/upgrade BeeKeeper local services on systemd-based Linux hosts.
set -Eeuo pipefail

BEEKEEPER_REPO=""
MONITOR_REPO=""
VALIDATE_ONLY=0
usage() {
  echo "Usage: sudo bash scripts/install-linux.sh --beekeeper-repo DIR --monitor-repo DIR"
  echo "       bash scripts/install-linux.sh --beekeeper-repo DIR --monitor-repo DIR --validate-only"
}
die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "[BeeKeeper] $*"; }

while (($#)); do
  case "$1" in
    --beekeeper-repo) (($# >= 2)) || die "Missing BeeKeeper repository path"; BEEKEEPER_REPO=$2; shift 2 ;;
    --monitor-repo) (($# >= 2)) || die "Missing Monitor repository path"; MONITOR_REPO=$2; shift 2 ;;
    --validate-only) VALIDATE_ONLY=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done
[[ -n "$BEEKEEPER_REPO" && -n "$MONITOR_REPO" ]] || { usage >&2; die "Both repositories are required."; }
command -v realpath >/dev/null 2>&1 || die "realpath is required."
BEEKEEPER_REPO=$(realpath "$BEEKEEPER_REPO") || die "BeeKeeper repository not found."
MONITOR_REPO=$(realpath "$MONITOR_REPO") || die "Monitor repository not found."
[[ -f "$BEEKEEPER_REPO/network/source_api.py" ]] || die "Missing network/source_api.py."
[[ -f "$BEEKEEPER_REPO/monitor-bridge/bridge.mjs" ]] || die "Missing monitor-bridge/bridge.mjs."
[[ -f "$MONITOR_REPO/integrations/local_ingest.py" ]] || die "Missing integrations/local_ingest.py."
for unit in beekeeper-monitor.service beekeeper-source-api.service beekeeper-bridge.service; do
  [[ -f "$BEEKEEPER_REPO/deploy/systemd/$unit" ]] || die "Missing systemd template $unit."
done
PYTHON=$(command -v python3) || die "Python 3 is required."
NODE=$(command -v node) || die "Node.js is required."
PY_MAJOR=$("$PYTHON" -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$("$PYTHON" -c 'import sys; print(sys.version_info.minor)')
NODE_MAJOR=$("$NODE" -p 'process.versions.node.split(".")[0]')
[[ "$PY_MAJOR" == "3" && "$PY_MINOR" -ge 11 ]] || die "Python 3.11 or newer is required."
[[ "$NODE_MAJOR" -ge 20 ]] || die "Node.js 20 or newer is required."

if ((VALIDATE_ONLY)); then
  log "Prerequisite validation passed."
  log "BeeKeeper3000: $BEEKEEPER_REPO"
  log "Beekeeper-Monitor: $MONITOR_REPO"
  log "Python $("$PYTHON" --version 2>&1); Node $("$NODE" --version)"
  log "No installation, files, users, secrets or services were changed."
  exit 0
fi
[[ "$EUID" -eq 0 ]] || die "Run with sudo/root."
for cmd in systemctl useradd groupadd getent install tar find sed; do
  command -v "$cmd" >/dev/null 2>&1 || die "Required command missing: $cmd"
done
[[ -d /run/systemd/system ]] || die "systemd is not running."

APP_ROOT=/opt/beekeeper3000
MONITOR_ROOT=/opt/beekeeper-monitor
STATE_ROOT=/var/lib/beekeeper3000
CONFIG_ROOT=/etc/beekeeper3000
ENV_FILE=$CONFIG_ROOT/station.env
for root in "$APP_ROOT" "$MONITOR_ROOT"; do
  [[ ! -e "$root/current" || -L "$root/current" ]] || die "$root/current exists and is not a symlink."
done
getent group beekeeper >/dev/null || groupadd --system beekeeper
getent passwd beekeeper >/dev/null || useradd --system --gid beekeeper --home-dir "$STATE_ROOT" --no-create-home --shell /usr/sbin/nologin beekeeper
install -d -o root -g root -m 0755 "$APP_ROOT/releases" "$MONITOR_ROOT/releases"
install -d -o beekeeper -g beekeeper -m 0700 "$STATE_ROOT"
chown beekeeper:beekeeper "$STATE_ROOT"
chmod 0700 "$STATE_ROOT"
install -d -o root -g beekeeper -m 0750 "$CONFIG_ROOT"

copy_release() {
  source=$1
  root=$2
  stage=$(mktemp -d "$root/releases/.stage.XXXXXX")
  if ! tar --exclude='./.git' --exclude='./.venv' --exclude='./venv' \
    --exclude='*/__pycache__' --exclude='./node_modules' --exclude='*/node_modules' \
    --exclude='./datasets' --exclude='./runs' --exclude='*.sqlite*' \
    --exclude='*.pt' --exclude='*.onnx' -C "$source" -cf - . | tar -C "$stage" -xf -; then
    rm -rf -- "$stage"
    die "Could not stage source code from $source."
  fi
  chown -R root:root "$stage"
  find "$stage" -type d -exec chmod 0755 {} +
  find "$stage" -type f ! -perm /111 -exec chmod 0644 {} +
  find "$stage" -type f -perm /111 -exec chmod 0755 {} +
  release="$root/releases/$(date -u +%Y%m%dT%H%M%SZ)-$$"
  mv -- "$stage" "$release"
  printf '%s' "$release"
}
atomic_link() {
  target=$1
  link=$2
  temporary=$link.new.$$
  rm -f -- "$temporary"
  ln -s -- "$target" "$temporary"
  mv -Tf -- "$temporary" "$link"
}
new_app=$(copy_release "$BEEKEEPER_REPO" "$APP_ROOT")
new_monitor=$(copy_release "$MONITOR_REPO" "$MONITOR_ROOT")

if [[ ! -e "$ENV_FILE" ]]; then
  "$PYTHON" - "$ENV_FILE" "$STATE_ROOT" <<'PY'
import os, secrets, sys
target, state = sys.argv[1], sys.argv[2]
monitor_token = secrets.token_urlsafe(48)
values = {
    "HORNET3000_API_KEY": secrets.token_urlsafe(48),
    "HORNET3000_CURSOR_SECRET": secrets.token_urlsafe(48),
    "VESPAGUARD_INGEST_TOKEN": monitor_token,
    "BEEKEEPER_MONITOR_INGEST_TOKEN": monitor_token,
    "HORNET3000_EVENT_DB": state + "/source-events.sqlite3",
    "HORNET3000_EVENT_RETENTION_DAYS": "30",
    "HORNET3000_EVENT_MAX_ROWS": "250000",
    "VESPAGUARD_INGEST_DB": state + "/monitor-events.sqlite3",
    "VESPAGUARD_RETENTION_DAYS": "90",
    "VESPAGUARD_MAX_EVENTS": "100000",
    "HORNET3000_URL": "http://127.0.0.1:8787",
    "BEEKEEPER_MONITOR_INGEST_URL": "http://127.0.0.1:8765/api/v1/events",
    "POLL_INTERVAL_MS": "10000",
    "BRIDGE_REQUIRE_CURSOR": "true",
    "BRIDGE_STATE_FILE": state + "/bridge-state.json",
}
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    for key, value in values.items():
        stream.write(key + "=" + value + "\n")
PY
fi
chown root:beekeeper "$ENV_FILE"
chmod 0640 "$ENV_FILE"
for key in HORNET3000_API_KEY HORNET3000_CURSOR_SECRET VESPAGUARD_INGEST_TOKEN BEEKEEPER_MONITOR_INGEST_TOKEN; do
  grep -qE "^$key=[A-Za-z0-9_-]{32,}$" "$ENV_FILE" || die "Missing/invalid secret setting: $key"
done
receiver_token=$(sed -n 's/^VESPAGUARD_INGEST_TOKEN=//p' "$ENV_FILE")
bridge_token=$(sed -n 's/^BEEKEEPER_MONITOR_INGEST_TOKEN=//p' "$ENV_FILE")
[[ -n "$receiver_token" && "$receiver_token" == "$bridge_token" ]] || die "Monitor and bridge receiver tokens do not match."

render_unit() {
  sed -e "s|@BEEKEEPER_ROOT@|$APP_ROOT/current|g" \
      -e "s|@MONITOR_ROOT@|$MONITOR_ROOT/current|g" \
      -e "s|@PYTHON@|$PYTHON|g" -e "s|@NODE@|$NODE|g" "$1" > "$2"
  chown root:root "$2"
  chmod 0644 "$2"
}
render_unit "$new_app/deploy/systemd/beekeeper-monitor.service" /etc/systemd/system/beekeeper-monitor.service
render_unit "$new_app/deploy/systemd/beekeeper-source-api.service" /etc/systemd/system/beekeeper-source-api.service
render_unit "$new_app/deploy/systemd/beekeeper-bridge.service" /etc/systemd/system/beekeeper-bridge.service

# Do not stop a running station until the replacement code, secrets and unit
# files have all been staged and validated successfully.
old_app=""
old_monitor=""
[[ -L "$APP_ROOT/current" ]] && old_app=$(readlink "$APP_ROOT/current")
[[ -L "$MONITOR_ROOT/current" ]] && old_monitor=$(readlink "$MONITOR_ROOT/current")
systemctl stop beekeeper-monitor.service beekeeper-source-api.service beekeeper-bridge.service >/dev/null 2>&1 || true
atomic_link "$new_app" "$APP_ROOT/current"
atomic_link "$new_monitor" "$MONITOR_ROOT/current"

rollback() {
  log "Activation failed; restoring previous code links."
  systemctl disable --now beekeeper-monitor.service beekeeper-source-api.service beekeeper-bridge.service >/dev/null 2>&1 || true
  if [[ -n "$old_app" ]]; then atomic_link "$old_app" "$APP_ROOT/current"; else rm -f -- "$APP_ROOT/current"; fi
  if [[ -n "$old_monitor" ]]; then atomic_link "$old_monitor" "$MONITOR_ROOT/current"; else rm -f -- "$MONITOR_ROOT/current"; fi
  systemctl daemon-reload >/dev/null 2>&1 || true
  if [[ -n "$old_app" && -n "$old_monitor" ]]; then
    systemctl enable --now beekeeper-monitor.service beekeeper-source-api.service beekeeper-bridge.service >/dev/null 2>&1 || true
  fi
}
if ! systemctl daemon-reload; then rollback; die "systemd could not reload unit files."; fi
if ! systemctl enable --now beekeeper-monitor.service beekeeper-source-api.service beekeeper-bridge.service; then
  rollback
  die "Services failed to start; previous links were restored where available."
fi
if ! systemctl is-active --quiet beekeeper-bridge.service; then
  rollback
  die "The Monitor bridge did not remain active after startup."
fi

if ! "$PYTHON" - "$ENV_FILE" <<'PY'
import json, sys, time, urllib.request
config = {}
with open(sys.argv[1], encoding="utf-8") as stream:
    for line in stream:
        if "=" in line and not line.startswith("#"):
            key, value = line.strip().split("=", 1)
            config[key] = value
def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=3) as response:
        return response.status, response.read(2 * 1024 * 1024)
deadline = time.monotonic() + 30
last_error = "not ready"
while time.monotonic() < deadline:
    try:
        status, _ = get("http://127.0.0.1:8765/")
        if status != 200:
            raise RuntimeError("Monitor health check failed")
        status, payload = get("http://127.0.0.1:8787/api/events?limit=1&cursor=start",
                              {"X-API-Key": config["HORNET3000_API_KEY"]})
        data = json.loads(payload.decode("utf-8"))
        if status != 200 or not all(k in data for k in ("events", "next_cursor", "has_more")):
            raise RuntimeError("Source API cursor check failed")
        print("Loopback Monitor and source API health checks passed.")
        raise SystemExit(0)
    except Exception as exc:
        last_error = type(exc).__name__
        time.sleep(1)
print("Local API health checks failed: " + last_error, file=sys.stderr)
raise SystemExit(1)
PY
then
  rollback
  die "Local health checks failed; inspect journalctl for service details."
fi
log "BeeKeeper station installed/updated; local APIs health-checked."
log "PWA: http://127.0.0.1:8765/; source API: 127.0.0.1:8787 (loopback only)."
log "Status: systemctl status beekeeper-monitor beekeeper-source-api beekeeper-bridge"
log "Logs: journalctl -u beekeeper-monitor -u beekeeper-source-api -u beekeeper-bridge"
log "State: $STATE_ROOT (preserved on upgrades); secrets: $ENV_FILE (never printed)."
log "Previous releases retained under /opt; camera and MeshCore radio are not started."
