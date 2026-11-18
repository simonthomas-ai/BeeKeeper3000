# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Telegram-Bot: Alarm mit Foto und Video (mit Ton) + Befehle /status /foto /stumm /laut."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

import httpx

from ..config import Settings
from .base import Notifier, Permanent, mask, with_retry

log = logging.getLogger("hornet.telegram")

HELP = (
    "Befehle:\n/status – Zustand der Anlage\n/foto – aktuelles Kamerabild\n"
    "/stumm [Minuten] – Alarme pausieren (Standard 60)\n/laut – Alarme wieder einschalten\n/id – deine Chat-ID"
)


class Telegram(Notifier):
    name = "telegram"
    label = "Telegram"
    supports_photo = True
    supports_video = True

    def __init__(self, s: Settings):
        self.s = s
        self.token = s.telegram_bot_token
        self.chats = list(s.telegram_chat_ids)
        self.base = f"{s.telegram_api_base}/bot{self.token}"

    def configured(self) -> bool:
        return bool(self.token and self.chats)

    def describe(self) -> str:
        return f"Bot {mask(self.token)} → {len(self.chats)} Chat(s)"

    # -- API ----------------------------------------------------------------------------
    def _call(self, method: str, data: dict | None = None, files: dict | None = None, timeout: float = 30) -> dict:
        try:
            r = httpx.post(f"{self.base}/{method}", data=data, files=files, timeout=timeout)
        except httpx.HTTPError as e:
            raise RuntimeError(f"Telegram {method}: {type(e).__name__}") from e
        try:
            j = r.json()
        except ValueError:
            j = {}
        if r.status_code == 429:
            wait = min(10, int((j.get("parameters") or {}).get("retry_after", 2)))
            time.sleep(wait)
            raise RuntimeError("Telegram: Rate-Limit")
        if not j.get("ok"):
            msg = j.get("description") or f"HTTP {r.status_code}"
            if 400 <= r.status_code < 500:
                raise Permanent(f"Telegram {method}: {msg}")
            raise RuntimeError(f"Telegram {method}: {msg}")
        return j

    def _each_chat(self, fn: Callable[[str], None]) -> str:
        errors = []
        for chat in self.chats:
            try:
                with_retry(lambda c=chat: fn(c))
            except Exception as e:
                errors.append(f"{chat}: {e}")
        if errors and len(errors) == len(self.chats):
            raise RuntimeError("; ".join(errors))
        ok = len(self.chats) - len(errors)
        return f"an {ok}/{len(self.chats)} Chat(s)" + (f" (Fehler: {'; '.join(errors)})" if errors else "")

    # -- Senden -------------------------------------------------------------------------
    def send_text_to(self, chat: str, text: str) -> None:
        self._call("sendMessage", {"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"})

    def send_photo_to(self, chat: str, data: bytes, caption: str) -> None:
        self._call("sendPhoto", {"chat_id": chat, "caption": caption[:1024]},
                   files={"photo": ("hornisse.jpg", data, "image/jpeg")}, timeout=60)

    def send_text(self, text: str) -> str:
        return self._each_chat(lambda c: self.send_text_to(c, text))

    def send_photo(self, path: Path, caption: str, meta: dict | None = None) -> str:
        data = Path(path).read_bytes()
        return self._each_chat(lambda c: self.send_photo_to(c, data, caption))

    def send_video(self, path: Path, caption: str, meta: dict | None = None) -> str:
        data = Path(path).read_bytes()
        if len(data) > 49 * 1024 * 1024:
            raise Permanent("Clip größer als 50 MB (Telegram-Limit)")
        return self._each_chat(lambda c: self._call(
            "sendVideo", {"chat_id": c, "caption": caption[:1024], "supports_streaming": "true"},
            files={"video": ("hornisse.mp4", data, "video/mp4")}, timeout=180))


class TelegramCommands:
    """Long-Polling für Bot-Befehle. Nicht freigeschaltete Chats erhalten nur ihre eigene Chat-ID."""

    def __init__(self, tg: Telegram, handlers: dict[str, Callable[[str, str], str | None]]):
        self.tg = tg
        self.handlers = handlers
        self._stop = threading.Event()

    def start(self) -> None:
        if not self.tg.token:
            return
        threading.Thread(target=self._loop, daemon=True, name="telegram-commands").start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        offset = 0
        while not self._stop.is_set():
            try:
                r = httpx.post(f"{self.tg.base}/getUpdates",
                               data={"timeout": 25, "offset": offset, "allowed_updates": '["message"]'}, timeout=40)
                j = r.json()
                if r.status_code == 409:  # anderer Prozess pollt denselben Bot
                    self._stop.wait(30)
                    continue
                if not j.get("ok"):
                    self._stop.wait(10)
                    continue
                for u in j.get("result", []):
                    offset = max(offset, int(u["update_id"]) + 1)
                    msg = u.get("message") or {}
                    if msg.get("text"):
                        try:
                            self._handle(msg)
                        except Exception as e:
                            log.warning("Befehl fehlgeschlagen: %s", e)
            except Exception:
                self._stop.wait(8)

    def _handle(self, msg: dict) -> None:
        chat = str(msg["chat"]["id"])
        parts = msg["text"].strip().split()
        cmd = parts[0].split("@")[0].lower()
        args = " ".join(parts[1:])
        authorised = chat in self.tg.chats
        if cmd in ("/start", "/id"):
            txt = f"Deine Chat-ID: {chat}"
            txt += ("\n\n" + HELP) if authorised else "\n\nTrage diese ID als TELEGRAM_CHAT_IDS in der .env ein und starte neu."
            self.tg.send_text_to(chat, txt)
            return
        if not authorised:
            self.tg.send_text_to(chat, f"Nicht freigeschaltet. Deine Chat-ID: {chat}")
            return
        name = {"/hilfe": "help", "/help": "help"}.get(cmd, cmd.lstrip("/"))
        if name == "help":
            self.tg.send_text_to(chat, HELP)
            return
        h = self.handlers.get(name)
        if h is None:
            self.tg.send_text_to(chat, "Unbekannter Befehl.\n\n" + HELP)
            return
        reply = h(chat, args)
        if reply:
            self.tg.send_text_to(chat, reply)
