"""Einrichtung in der App: Einstellungen prüfen und in die .env schreiben, Kamera testen, Telegram-Chats finden.

Alle Funktionen hier sind echte Prüfungen gegen echte Geräte/Dienste (ffmpeg, Kamera, Telegram) – keine Simulation.
"""
from __future__ import annotations

import base64
import glob
import platform
import re
import subprocess
import time
from pathlib import Path

import httpx

from .camera import _NOWIN, find_ffmpeg, resolve_source, validate_source
from .config import parse_env_file, write_env_values

# key: (Art, geheim, Auswahl/Grenzen)
SCHEMA: dict[str, dict] = {
    "CAMERA_NAME": {"t": "str"},
    "CAMERA_SOURCE": {"t": "source"},
    "CAMERA_AUDIO_DEVICE": {"t": "str"},
    "DETECT_FPS": {"t": "float", "min": 0.5, "max": 10},
    "CLIP_ENABLED": {"t": "bool"},
    "CLIP_PRE_S": {"t": "int", "min": 0, "max": 30},
    "CLIP_POST_S": {"t": "int", "min": 2, "max": 60},
    "TELEGRAM_BOT_TOKEN": {"t": "str", "secret": True, "re": r"^\d{5,}:[A-Za-z0-9_-]{20,}$"},
    "TELEGRAM_CHAT_IDS": {"t": "list", "re": r"^-?\d+$"},
    "WHATSAPP_PROVIDER": {"t": "enum", "choices": ["none", "cloud", "callmebot"]},
    "WHATSAPP_TOKEN": {"t": "str", "secret": True},
    "WHATSAPP_PHONE_ID": {"t": "str", "re": r"^\d{5,}$"},
    "WHATSAPP_TO": {"t": "list", "re": r"^\+?\d{6,15}$"},
    "WHATSAPP_TEMPLATE": {"t": "str", "re": r"^[a-z0-9_]{0,512}$"},
    "CALLMEBOT_PHONE": {"t": "str", "re": r"^\+?\d{6,15}$"},
    "CALLMEBOT_APIKEY": {"t": "str", "secret": True},
    "SMS_URL": {"t": "url"},
    "SMS_USER": {"t": "str"},
    "SMS_PASSWORD": {"t": "str", "secret": True},
    "SMS_TO": {"t": "list", "re": r"^\+?\d{6,15}$"},
    "SMS_MMS": {"t": "bool"},
    "PUBLIC_URL": {"t": "url"},
    "WEBPUSH_CONTACT": {"t": "str", "re": r"^(mailto:)?[^@\s]+@[^@\s]+\.[^@\s]+$|^https://\S+$|^$"},
    "APIARY_LAT": {"t": "float", "min": -90, "max": 90},
    "APIARY_LON": {"t": "float", "min": -180, "max": 180},
    "SIGHTINGS_RADIUS_KM": {"t": "float", "min": 1, "max": 200},
    "VERIFY_PROVIDER": {"t": "enum", "choices": ["auto", "none", "anthropic", "ollama"]},
    "ANTHROPIC_API_KEY": {"t": "str", "secret": True},
    "VERIFY_MODEL": {"t": "str", "re": r"^[A-Za-z0-9._:-]{0,80}$"},
    "OLLAMA_URL": {"t": "url"},
    "OLLAMA_MODEL": {"t": "str", "re": r"^[A-Za-z0-9._:/-]{0,80}$"},
    "RETENTION_DAYS": {"t": "int", "min": 1, "max": 3650},
    # Funknetz
    "MESH_STATION": {"t": "str", "re": r"^[^\x00-\x1f|@]{0,24}$"},
    "MESH_SHARE_POSITION": {"t": "bool"},
    "MESH_FORWARD": {"t": "bool"},
    "MESH_ACK": {"t": "bool"},
    "MESH_TRUSTED": {"t": "names"},
    "MESH_LORA_ENABLED": {"t": "bool"},
    "MESH_LORA_PORT": {"t": "port"},
    "MESH_LORA_BAUD": {"t": "int", "min": 9600, "max": 921600},
    "MESH_LORA_CHANNEL_IDX": {"t": "int", "min": 1, "max": 7},
    "MESH_LORA_CHANNEL_NAME": {"t": "str", "re": r"^[A-Za-z0-9 _#.\-]{0,31}$"},
    "MESH_LORA_CHANNEL_KEY": {"t": "str", "secret": True, "re": r"^[0-9a-fA-F]{32}$"},
    "MESH_LORA_DUTY": {"t": "float", "min": 0.001, "max": 0.10},
    "MESH_FREENET_ENABLED": {"t": "bool"},
    "MESH_FREENET_RIVERCTL": {"t": "riverctl"},
    "MESH_FREENET_ROOM": {"t": "room"},
    "MESH_FREENET_NODE": {"t": "node"},
}


def read_config(env_path: Path) -> dict:
    """Gespeicherte Werte (Geheimnisse nur als 'gesetzt')."""
    raw = parse_env_file(env_path)
    values, secrets = {}, {}
    for k, spec in SCHEMA.items():
        v = raw.get(k, "")
        if spec.get("secret"):
            secrets[k] = bool(v)
        else:
            values[k] = v
    return {"values": values, "secrets": secrets, "schema": {k: {kk: vv for kk, vv in s.items() if kk in ("t", "choices", "min", "max", "secret")}
                                                             for k, s in SCHEMA.items()}}


def _check(key: str, val: str) -> str:
    spec = SCHEMA[key]
    val = val.strip()
    if "\n" in val or "\r" in val:
        raise ValueError(f"{key}: Zeilenumbrüche nicht erlaubt")
    if val == "":
        return ""
    t = spec["t"]
    if t == "source":
        return validate_source(val)
    if t == "url":
        if not re.match(r"^https?://[^\s/]+(/\S*)?$", val):
            raise ValueError(f"{key}: bitte eine Adresse mit http:// oder https:// angeben")
        return val.rstrip("/")
    if t == "port":
        from .mesh.lora import check_port
        return check_port(val)
    if t == "room":
        from .mesh.freenet import check_room
        return check_room(val)
    if t == "node":
        from .mesh.freenet import check_node
        return check_node(val)
    if t == "riverctl":
        if not re.match(r"^[\w ./\\:\-]{1,260}$", val) or not re.match(r"^riverctl(\.exe)?$", re.split(r"[/\\]", val)[-1], re.I):
            raise ValueError(f"{key}: nur das Programm „riverctl“ (ggf. mit Pfad) ist erlaubt")
        return val
    if t == "names":
        names = [x.strip() for x in re.split(r"[,;]", val) if x.strip()]
        for nme in names:
            if not re.match(r"^[^\x00-\x1f|@]{1,24}$", nme):
                raise ValueError(f"{key}: Stationsname '{nme[:30]}' ist nicht erlaubt")
        return ",".join(names)
    if t == "int":
        try:
            n = int(float(val.replace(",", ".")))
        except (ValueError, OverflowError):
            raise ValueError(f"{key}: bitte eine Zahl angeben") from None
        if not spec["min"] <= n <= spec["max"]:
            raise ValueError(f"{key}: erlaubt sind {spec['min']} bis {spec['max']}")
        return str(n)
    if t == "float":
        try:
            f = float(val.replace(",", "."))
        except (ValueError, OverflowError):
            raise ValueError(f"{key}: bitte eine Zahl angeben") from None
        if not spec["min"] <= f <= spec["max"]:
            raise ValueError(f"{key}: erlaubt sind {spec['min']} bis {spec['max']}")
        return f"{f:g}"
    if t == "bool":
        if val.lower() not in ("true", "false", "1", "0", "ja", "nein"):
            raise ValueError(f"{key}: ja/nein erwartet")
        return "true" if val.lower() in ("true", "1", "ja") else "false"
    if t == "enum":
        if val not in spec["choices"]:
            raise ValueError(f"{key}: erlaubt sind {', '.join(spec['choices'])}")
        return val
    if t == "list":
        items = [x.strip() for x in re.split(r"[,;\s]+", val) if x.strip()]
        for it in items:
            if not re.match(spec["re"], it):
                raise ValueError(f"{key}: '{it}' sieht nicht richtig aus")
        return ",".join(items)
    if spec.get("re") and not re.match(spec["re"], val):
        raise ValueError(f"{key}: Format stimmt nicht")
    return val


def apply_updates(env_path: Path, updates: dict[str, str | None]) -> list[str]:
    """Prüft und speichert. None = unverändert lassen (für Geheimnisse). Rückgabe: geänderte Schlüssel."""
    current = parse_env_file(env_path)
    clean: dict[str, str] = {}
    for k, v in updates.items():
        if k not in SCHEMA:
            raise ValueError(f"Unbekannte Einstellung: {k}")
        if v is None:
            continue
        clean[k] = _check(k, str(v))
    changed = [k for k, v in clean.items() if current.get(k, "") != v]
    if changed:
        write_env_values(env_path, {k: clean[k] for k in changed})
    return changed


# ── Kamera prüfen ───────────────────────────────────────────────────────────────────────────
def _friendly(err: str) -> str:
    low = err.lower()
    if "401" in low and "unauthorized" in low:
        return "Benutzername oder Passwort der Kamera stimmen nicht."
    if "404" in low and "not found" in low:
        return "Die Kamera antwortet, aber der Pfad in der Adresse stimmt nicht (z. B. …/h264Preview_01_main bei Reolink)."
    if "connection refused" in low:
        return "Verbindung abgelehnt: Adresse oder Port falsch, oder RTSP ist in der Kamera ausgeschaltet."
    if "no route to host" in low or "network is unreachable" in low or "timed out" in low:
        return "Kamera nicht erreichbar: Adresse, Netzwerk oder Firewall prüfen."
    if "could not find" in low or "no such file" in low or "cannot open" in low:
        return "Gerät oder Datei nicht gefunden."
    if "device or resource busy" in low or "already in use" in low or "could not run graph" in low:
        return "Die Kamera wird gerade von einem anderen Programm benutzt."
    lines = [ln for ln in err.strip().splitlines() if ln.strip()]
    return " | ".join(lines[-2:])[:300] if lines else "Unbekannter Fehler"


def probe_camera(source: str, audio_device: str = "", ffmpeg_bin: str = "") -> dict:
    """Holt echt ein Bild von der Quelle und meldet Video-/Tonformat."""
    source = validate_source(source)
    if source.strip().lower() == "phone":
        return {"ok": False, "phone": True,
                "error": "„Handy als Kamera“ lässt sich hier nicht testen – dafür unten „QR-Code anzeigen“ "
                        "verwenden und mit dem Handy verbinden. Der Verbindungsstatus erscheint dann im Reiter „Live“."}
    spec = resolve_source(source, audio_device)
    cmd = [find_ffmpeg(ffmpeg_bin), "-hide_banner", "-nostdin", *spec.inputs, "-map", spec.vmap, "-frames:v", "1",
           "-vf", "scale=960:-2", "-q:v", "4", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=35, **_NOWIN)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Zeitüberschreitung: nach 35 s kein Bild. Adresse und Netzwerk prüfen."}
    err = r.stderr.decode("utf-8", "replace")
    jpeg = r.stdout if r.stdout[:2] == b"\xff\xd8" else b""
    if not jpeg:
        return {"ok": False, "error": _friendly(err)}
    v = re.search(r"Stream #\d+:\d+[^\n]*?: Video: (\w+)[^\n]*?, (\d{2,5})x(\d{2,5})", err)
    a = re.search(r"Stream #\d+:\d+[^\n]*?: Audio: (\w+)[^\n]*?, (\d+) Hz, (\w+)", err)
    return {
        "ok": True,
        "seconds": round(time.time() - t0, 1),
        "image": base64.b64encode(jpeg).decode(),
        "video": f"{v.group(1)} {v.group(2)}×{v.group(3)}" if v else "unbekannt",
        "audio": f"{a.group(1)} {a.group(2)} Hz" if a else None,
        "audio_note": None if a else "Die Quelle liefert keinen Ton. Bei Netzwerkkameras Mikrofon/Audio in der Kamera einschalten; "
                                     "bei Webcams ein Mikrofon unter „Mikrofon“ eintragen.",
    }


# ── Geräte auflisten ───────────────────────────────────────────────────────────────────────
def parse_dshow(stderr: str) -> dict:
    video, audio = [], []
    for m in re.finditer(r'"([^"]+)" \((video|audio)[^)]*\)', stderr):
        (video if m.group(2) == "video" else audio).append(m.group(1))
    return {"video": list(dict.fromkeys(video)), "audio": list(dict.fromkeys(audio))}


def parse_avfoundation(stderr: str) -> dict:
    video, audio, section = [], [], None
    for line in stderr.splitlines():
        if "AVFoundation video devices" in line:
            section = video
        elif "AVFoundation audio devices" in line:
            section = audio
        else:
            m = re.search(r"\[(\d+)\] (.+)$", line)
            if m and section is not None:
                section.append(f"{m.group(1)}:{m.group(2).strip()}")
    return {"video": video, "audio": audio}


def list_devices(ffmpeg_bin: str = "") -> dict:
    system = platform.system()
    ff = find_ffmpeg(ffmpeg_bin)
    if system == "Windows":
        r = subprocess.run([ff, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                           capture_output=True, timeout=30, **_NOWIN)
        d = parse_dshow(r.stderr.decode("utf-8", "replace"))
        return {"system": system, "video": [{"label": n, "source": f"dshow:{n}"} for n in d["video"]],
                "audio": [{"label": n, "value": n} for n in d["audio"]]}
    if system == "Darwin":
        r = subprocess.run([ff, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                           capture_output=True, timeout=30)
        d = parse_avfoundation(r.stderr.decode("utf-8", "replace"))
        return {"system": system, "video": [{"label": n.split(":", 1)[1], "source": f"avfoundation:{n.split(':', 1)[0]}"} for n in d["video"]],
                "audio": [{"label": n.split(":", 1)[1], "value": n.split(":", 1)[0]} for n in d["audio"]]}
    return {"system": system, "video": [{"label": p, "source": f"v4l2:{p}"} for p in sorted(glob.glob("/dev/video*"))],
            "audio": []}


# ── Telegram ───────────────────────────────────────────────────────────────────────────────
def telegram_discover(token: str, api_base: str = "https://api.telegram.org") -> dict:
    """Prüft den Bot-Token und listet Chats, die dem Bot geschrieben haben (Chat-IDs für den Alarm)."""
    if not re.match(r"^\d{5,}:[A-Za-z0-9_-]{20,}$", token.strip()):
        return {"ok": False, "error": "Das sieht nicht wie ein Bot-Token aus (Format 123456789:ABC…, von @BotFather)."}
    base = f"{api_base}/bot{token.strip()}"
    try:
        me = httpx.get(f"{base}/getMe", timeout=15).json()
        if not me.get("ok"):
            return {"ok": False, "error": f"Telegram lehnt den Token ab: {me.get('description', 'unbekannt')}"}
        up = httpx.post(f"{base}/getUpdates", data={"timeout": 0, "limit": 100}, timeout=20)
        j = up.json()
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Telegram nicht erreichbar ({type(e).__name__}). Internetverbindung prüfen."}
    bot = "@" + (me.get("result") or {}).get("username", "?")
    if up.status_code == 409:
        return {"ok": True, "bot": bot, "chats": [], "note": "Der Bot wird gerade vom Programm selbst abgefragt. "
                "Schreibe ihm /start – er antwortet mit deiner Chat-ID."}
    chats: dict[str, dict] = {}
    for u in j.get("result", []):
        m = u.get("message") or u.get("edited_message") or u.get("channel_post") or {}
        c = m.get("chat")
        if c and "id" in c:
            name = c.get("title") or " ".join(x for x in (c.get("first_name"), c.get("last_name")) if x) or c.get("username") or ""
            chats[str(c["id"])] = {"id": str(c["id"]), "name": name, "type": c.get("type", "")}
    return {"ok": True, "bot": bot, "chats": list(chats.values()),
            "note": None if chats else f"Noch keine Nachricht gefunden. Öffne {bot} in Telegram, schreibe /start und versuche es erneut."}
