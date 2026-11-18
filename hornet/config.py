# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Konfiguration aus .env / Umgebungsvariablen. Keine Abhängigkeiten außer der Standardbibliothek."""
from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_env_file(path: Path) -> dict[str, str]:
    """Liest KEY=VALUE-Zeilen einer .env-Datei (Kommentare und Anführungszeichen werden berücksichtigt)."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        elif " #" in val:
            val = val.split(" #", 1)[0].strip()
        out[key] = val
    return out


def load_env(path: Path, override: bool = False) -> None:
    """Übernimmt die .env in os.environ. Bereits gesetzte Variablen haben Vorrang, außer override=True
    (wird beim Neustart nach Änderungen in der Einrichtung benutzt)."""
    for key, val in parse_env_file(path).items():
        if override:
            os.environ[key] = val
        else:
            os.environ.setdefault(key, val)


ENV_HEADER = (
    "# Hornet3000 Wächter – Einstellungen. Wird von der Einrichtung in der App verwaltet.\n"
    "# Von Hand ändern ist möglich; danach das Programm neu starten.\n"
)


def restrict(path: Path, mode: int) -> None:
    """Zugriffsrechte einschränken (Linux/macOS). Unter Windows regelt der Benutzerordner den Zugriff."""
    if os.name == "nt":
        return
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def ensure_private_dir(path: Path) -> Path:
    """Legt den Ordner an und erlaubt nur dem Besitzer den Zugriff (enthält Alarme, Videos, Datenbank)."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    restrict(path, 0o700)
    return path


def ensure_env_file(path: Path | None = None) -> Path:
    """Legt die .env an. Sie enthält Zugangsschlüssel und Zugangsdaten und ist nur für den Besitzer lesbar."""
    path = path or ROOT / ".env"
    if not path.is_file():
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(ENV_HEADER)
    restrict(path, 0o600)
    return path


def _env_quote(val: str) -> str:
    if "\n" in val or "\r" in val:
        raise ValueError("Zeilenumbrüche sind in Einstellungen nicht erlaubt")
    if val != val.strip() or " #" in val or val.startswith(("#", '"', "'")):
        if '"' in val:
            raise ValueError("Anführungszeichen sind in diesem Wert nicht erlaubt")
        return f'"{val}"'
    return val


def write_env_values(path: Path, updates: dict[str, str]) -> None:
    """Setzt/ergänzt Schlüssel in der .env, alle anderen Zeilen (auch Kommentare) bleiben unverändert."""
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.is_file() else ENV_HEADER.splitlines()
    pending = {k: _env_quote(v) for k, v in updates.items()}
    out: list[str] = []
    for line in lines:
        m = re.match(r"^\s*([A-Za-z0-9_]+)\s*=", line)
        if m and m.group(1) in pending:
            out.append(f"{m.group(1)}={pending.pop(m.group(1))}")
        else:
            out.append(line)
    for k, v in pending.items():
        out.append(f"{k}={v}")
    tmp = path.with_suffix(".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    restrict(tmp, 0o600)
    tmp.replace(path)


def _s(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _i(key: str, default: int) -> int:
    try:
        return int(_s(key, str(default)))
    except ValueError:
        return default


def _f(key: str, default: float) -> float:
    try:
        return float(_s(key, str(default)).replace(",", "."))
    except ValueError:
        return default


def _b(key: str, default: bool) -> bool:
    v = _s(key, "true" if default else "false").lower()
    return v in ("1", "true", "yes", "ja", "on", "an")


def _l(key: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,;]", _s(key)) if p.strip()]


@dataclass
class Settings:
    # Server
    host: str = "0.0.0.0"  # nosec B104 - bewusst: Handy/PC im Heimnetz, geschützt durch Zugangsschlüssel (siehe Sicherheitsdoku)
    port: int = 8080
    public_url: str = ""
    access_token: str = ""
    data_dir: Path = ROOT / "data"
    ssl_certfile: str = ""
    ssl_keyfile: str = ""
    retention_days: int = 90

    # Kamera
    camera_name: str = "Bienenstock 1"
    camera_source: str = ""
    camera_audio_device: str = ""
    detect_fps: float = 3.0
    pipe_width: int = 960
    ffmpeg_bin: str = ""

    # Erkennung
    model_path: str = "models/hornet_yolov8s.onnx"
    ort_providers: list[str] = field(default_factory=list)
    alert_classes: list[str] = field(default_factory=lambda: ["vvel"])
    protected_classes: list[str] = field(default_factory=lambda: ["vcra"])
    conf_min: float = 0.30
    conf_alert: float = 0.60
    confirm_hits: int = 3
    confirm_window: int = 6
    event_gap_s: int = 300
    reminder_s: int = 1800
    escalate_min_s: int = 60

    # Clip mit Ton
    clip_enabled: bool = True
    clip_pre_s: int = 6
    clip_post_s: int = 8
    segment_s: int = 2
    clip_video: str = "x264"  # x264 | copy
    clip_width: int = 960

    # Prüfung durch Bild-KI (optional)
    verify_provider: str = "auto"  # auto | none | anthropic | ollama
    anthropic_api_key: str = ""
    verify_model: str = "claude-sonnet-5"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5vl:7b"
    verify_timeout_s: int = 20

    # Kanäle
    telegram_bot_token: str = ""
    telegram_chat_ids: list[str] = field(default_factory=list)
    telegram_api_base: str = "https://api.telegram.org"
    telegram_commands: bool = True

    whatsapp_provider: str = "none"  # none | cloud | callmebot
    whatsapp_token: str = ""
    whatsapp_phone_id: str = ""
    whatsapp_to: list[str] = field(default_factory=list)
    whatsapp_template: str = ""
    whatsapp_template_lang: str = "de"
    whatsapp_api_version: str = "v23.0"
    whatsapp_api_base: str = "https://graph.facebook.com"
    callmebot_phone: str = ""
    callmebot_apikey: str = ""
    callmebot_url: str = "https://api.callmebot.com/whatsapp.php"

    sms_url: str = ""
    sms_user: str = ""
    sms_password: str = ""
    sms_to: list[str] = field(default_factory=list)
    sms_mms: bool = False

    webpush_contact: str = ""

    # Standort des Bienenstands (für Sichtungen in der Umgebung)
    apiary_lat: float = 0.0
    apiary_lon: float = 0.0
    sightings_radius_km: float = 20.0
    gbif_base: str = "https://api.gbif.org/v1"

    # Funknetz zwischen den Stationen (beide Wege sind ab Werk aus und unabhängig schaltbar)
    mesh_station: str = ""                 # leer = Name des Bienenstands
    mesh_share_position: bool = False      # Standort (auf ca. 1 km gerundet) mitsenden
    mesh_forward: bool = True              # Meldungen anderer Stationen an die eigenen Meldewege weiterreichen
    mesh_ack: bool = True                  # Empfang bestätigen (Quittung)
    mesh_trusted: list[str] = field(default_factory=list)
    mesh_lora_enabled: bool = False
    mesh_lora_port: str = ""               # z. B. /dev/ttyUSB0, COM3; "auto" = erstes erkanntes Funkgerät
    mesh_lora_baud: int = 115200
    mesh_lora_channel_idx: int = 1         # Kanal 0 ist der öffentliche MeshCore-Kanal und wird nie benutzt
    mesh_lora_channel_name: str = "hornet3000"
    mesh_lora_channel_key: str = ""        # 32 Hex-Zeichen (16 Byte); leer = Kanal am Gerät nicht verändern
    mesh_lora_duty: float = 0.01           # erlaubter Sendeanteil (1 % = EU868-Teilband g1)
    mesh_freenet_enabled: bool = False
    mesh_freenet_riverctl: str = "riverctl"
    mesh_freenet_room: str = ""            # Raum-Schlüssel (Owner-Key) des River-Raums
    mesh_freenet_node: str = "ws://127.0.0.1:7509"

    @property
    def mesh_station_name(self) -> str:
        return (self.mesh_station or self.camera_name or "Station").strip()

    @property
    def webpush_sub(self) -> str:
        """Kontaktangabe für Web-Push (VAPID 'sub'): E-Mail des Betreibers oder die https-Adresse der App."""
        c = self.webpush_contact.strip()
        if c.startswith(("mailto:", "https://")):
            return c
        if "@" in c:
            return "mailto:" + c
        if self.public_url.startswith("https://"):
            return self.public_url
        return ""

    @property
    def alerts_dir(self) -> Path:
        return self.data_dir / "alerts"

    @property
    def segments_dir(self) -> Path:
        return self.data_dir / "segments"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "hornet.db"

    def resolve_model(self) -> Path:
        p = Path(self.model_path)
        return p if p.is_absolute() else ROOT / p

    @staticmethod
    def from_env(env_file: Path | None = None, override: bool = False) -> "Settings":
        load_env(env_file or ROOT / ".env", override)
        data_dir = Path(_s("DATA_DIR", str(ROOT / "data")))
        if not data_dir.is_absolute():
            data_dir = ROOT / data_dir
        s = Settings(
            host=_s("HOST", "0.0.0.0"),  # nosec B104
            port=_i("PORT", 8080),
            public_url=_s("PUBLIC_URL").rstrip("/"),
            access_token=_s("ACCESS_TOKEN"),
            data_dir=data_dir,
            ssl_certfile=_s("SSL_CERTFILE"),
            ssl_keyfile=_s("SSL_KEYFILE"),
            retention_days=_i("RETENTION_DAYS", 90),
            camera_name=_s("CAMERA_NAME", "Bienenstock 1"),
            camera_source=_s("CAMERA_SOURCE", ""),
            camera_audio_device=_s("CAMERA_AUDIO_DEVICE"),
            detect_fps=_f("DETECT_FPS", 3.0),
            pipe_width=_i("PIPE_WIDTH", 960),
            ffmpeg_bin=_s("FFMPEG_BIN"),
            model_path=_s("MODEL_PATH", "models/hornet_yolov8s.onnx"),
            ort_providers=_l("ORT_PROVIDERS"),
            alert_classes=_l("ALERT_CLASSES") or ["vvel"],
            protected_classes=_l("PROTECTED_CLASSES") if "PROTECTED_CLASSES" in os.environ else ["vcra"],
            conf_min=_f("CONF_MIN", 0.30),
            conf_alert=_f("CONF_ALERT", 0.60),
            confirm_hits=_i("CONFIRM_HITS", 3),
            confirm_window=_i("CONFIRM_WINDOW", 6),
            event_gap_s=_i("EVENT_GAP_S", 300),
            reminder_s=_i("REMINDER_S", 1800),
            escalate_min_s=_i("ESCALATE_MIN_S", 60),
            clip_enabled=_b("CLIP_ENABLED", True),
            clip_pre_s=_i("CLIP_PRE_S", 6),
            clip_post_s=_i("CLIP_POST_S", 8),
            segment_s=max(1, _i("SEGMENT_S", 2)),
            clip_video=_s("CLIP_VIDEO", "x264").lower(),
            clip_width=_i("CLIP_WIDTH", 960),
            verify_provider=_s("VERIFY_PROVIDER", "auto").lower(),
            anthropic_api_key=_s("ANTHROPIC_API_KEY"),
            verify_model=_s("VERIFY_MODEL", "claude-sonnet-5"),
            ollama_url=_s("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
            ollama_model=_s("OLLAMA_MODEL", "qwen2.5vl:7b"),
            verify_timeout_s=_i("VERIFY_TIMEOUT_S", 20),
            telegram_bot_token=_s("TELEGRAM_BOT_TOKEN"),
            telegram_chat_ids=_l("TELEGRAM_CHAT_IDS"),
            telegram_api_base=_s("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/"),
            telegram_commands=_b("TELEGRAM_COMMANDS", True),
            whatsapp_provider=_s("WHATSAPP_PROVIDER", "none").lower(),
            whatsapp_token=_s("WHATSAPP_TOKEN"),
            whatsapp_phone_id=_s("WHATSAPP_PHONE_ID"),
            whatsapp_to=_l("WHATSAPP_TO"),
            whatsapp_template=_s("WHATSAPP_TEMPLATE"),
            whatsapp_template_lang=_s("WHATSAPP_TEMPLATE_LANG", "de"),
            whatsapp_api_version=_s("WHATSAPP_API_VERSION", "v23.0"),
            whatsapp_api_base=_s("WHATSAPP_API_BASE", "https://graph.facebook.com").rstrip("/"),
            callmebot_phone=_s("CALLMEBOT_PHONE"),
            callmebot_apikey=_s("CALLMEBOT_APIKEY"),
            callmebot_url=_s("CALLMEBOT_URL", "https://api.callmebot.com/whatsapp.php"),
            sms_url=_s("SMS_URL").rstrip("/"),
            sms_user=_s("SMS_USER"),
            sms_password=_s("SMS_PASSWORD"),
            sms_to=_l("SMS_TO"),
            sms_mms=_b("SMS_MMS", False),
            webpush_contact=_s("WEBPUSH_CONTACT"),
            apiary_lat=_f("APIARY_LAT", 0.0),
            apiary_lon=_f("APIARY_LON", 0.0),
            sightings_radius_km=_f("SIGHTINGS_RADIUS_KM", 20.0),
            gbif_base=_s("GBIF_BASE", "https://api.gbif.org/v1").rstrip("/"),
            mesh_station=_s("MESH_STATION"),
            mesh_share_position=_b("MESH_SHARE_POSITION", False),
            mesh_forward=_b("MESH_FORWARD", True),
            mesh_ack=_b("MESH_ACK", True),
            mesh_trusted=_l("MESH_TRUSTED"),
            mesh_lora_enabled=_b("MESH_LORA_ENABLED", False),
            mesh_lora_port=_s("MESH_LORA_PORT"),
            mesh_lora_baud=_i("MESH_LORA_BAUD", 115200),
            mesh_lora_channel_idx=_i("MESH_LORA_CHANNEL_IDX", 1),
            mesh_lora_channel_name=_s("MESH_LORA_CHANNEL_NAME", "hornet3000"),
            mesh_lora_channel_key=_s("MESH_LORA_CHANNEL_KEY").lower(),
            mesh_lora_duty=_f("MESH_LORA_DUTY", 0.01),
            mesh_freenet_enabled=_b("MESH_FREENET_ENABLED", False),
            mesh_freenet_riverctl=_s("MESH_FREENET_RIVERCTL", "riverctl"),
            mesh_freenet_room=_s("MESH_FREENET_ROOM"),
            mesh_freenet_node=_s("MESH_FREENET_NODE", "ws://127.0.0.1:7509"),
        )
        return s


def ensure_access_token(s: Settings, env_file: Path | None = None) -> bool:
    """Erzeugt beim ersten Start einen Zugangsschlüssel und schreibt ihn in die .env.
    Gibt True zurück, wenn ein neuer Schlüssel erzeugt wurde."""
    if s.access_token:
        return False
    s.access_token = secrets.token_urlsafe(18)
    path = env_file or ROOT / ".env"
    try:
        text = path.read_text(encoding="utf-8-sig") if path.is_file() else ""
        if re.search(r"^ACCESS_TOKEN=.*$", text, flags=re.M):
            text = re.sub(r"^ACCESS_TOKEN=.*$", f"ACCESS_TOKEN={s.access_token}", text, flags=re.M)
        else:
            text = text.rstrip("\n") + f"\nACCESS_TOKEN={s.access_token}\n"
        path.write_text(text, encoding="utf-8")
        restrict(path, 0o600)
    except OSError:
        pass
    return True
