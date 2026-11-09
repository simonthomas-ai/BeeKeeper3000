"""SMS über 'SMS Gateway for Android' (capcom6, Apache-2.0): das eigene Android-Handy versendet die SMS
über die eigene SIM-Karte – keine Anbietergebühren außer dem Mobilfunktarif.

Lokaler Server:  SMS_URL=http://<handy-ip>:8080        (Handy und PC im selben WLAN)
Cloud-Server:    SMS_URL=https://api.sms-gate.app/3rdparty/v1
"""
from __future__ import annotations

import base64
import io
from pathlib import Path

import httpx
from PIL import Image

from ..config import Settings
from .base import Notifier, Permanent, with_retry


class AndroidSmsGateway(Notifier):
    name = "sms"
    label = "SMS"
    short = True

    def __init__(self, s: Settings):
        self.s = s
        u = s.sms_url
        self.endpoint = u if u.endswith("/message") else f"{u}/message"

    @property
    def supports_photo(self) -> bool:  # type: ignore[override]
        return self.s.sms_mms

    def configured(self) -> bool:
        return bool(self.s.sms_url and self.s.sms_user and self.s.sms_password and self.s.sms_to)

    def describe(self) -> str:
        return f"Android-Gateway → {len(self.s.sms_to)} Nummer(n)" + (", MMS mit Foto" if self.s.sms_mms else "")

    def _post(self, body: dict) -> str:
        def go() -> str:
            try:
                r = httpx.post(self.endpoint, json=body, auth=(self.s.sms_user, self.s.sms_password), timeout=30)
            except httpx.HTTPError as e:
                raise RuntimeError(f"SMS-Gateway: {type(e).__name__}") from e
            if r.status_code in (200, 201, 202):
                return f"an {len(self.s.sms_to)} Nummer(n) übergeben"
            if 400 <= r.status_code < 500 and r.status_code != 429:
                raise Permanent(f"SMS-Gateway HTTP {r.status_code}: {r.text[:120]}")
            raise RuntimeError(f"SMS-Gateway HTTP {r.status_code}")
        return with_retry(go)

    def send_text(self, text: str) -> str:
        return self._post({"textMessage": {"text": text[:480]}, "phoneNumbers": self.s.sms_to})

    def send_photo(self, path: Path, caption: str, meta: dict | None = None) -> str:
        if not self.s.sms_mms:
            return self.send_text(caption)
        im = Image.open(path).convert("RGB")
        im.thumbnail((640, 640))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=70)
        att = {"contentType": "image/jpeg", "name": "hornisse.jpg", "data": base64.b64encode(buf.getvalue()).decode()}
        return self._post({"mmsMessage": {"subject": "Hornissen-Alarm", "text": caption[:480], "attachments": [att]},
                           "phoneNumbers": self.s.sms_to})
