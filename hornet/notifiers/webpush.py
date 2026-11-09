"""Web-Push für die PWA (VAPID). Funktioniert nur über HTTPS (oder http://localhost)."""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

from ..config import Settings
from ..store import Store
from .base import Notifier

log = logging.getLogger("hornet.webpush")


class WebPush(Notifier):
    name = "push"
    label = "App-Benachrichtigung (PWA)"
    supports_photo = True

    def __init__(self, s: Settings, store: Store):
        self.s = s
        self.store = store
        self.key_path = s.data_dir / "vapid_private.pem"
        self.public_key = ""
        try:
            self._init_keys()
        except Exception as e:  # pywebpush/cryptography fehlt o. ä.
            log.warning("Web-Push nicht verfügbar: %s", e)

    def _init_keys(self) -> None:
        from cryptography.hazmat.primitives import serialization
        from py_vapid import Vapid01

        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        if self.key_path.is_file():
            v = Vapid01.from_file(str(self.key_path))
        else:
            v = Vapid01()
            v.generate_keys()
            v.save_key(str(self.key_path))
        raw = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.public_key = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    @property
    def ready(self) -> bool:
        """Schlüssel vorhanden und Kontaktangabe (E-Mail oder https-Adresse) eingetragen."""
        return bool(self.public_key) and bool(self.s.webpush_sub)

    def configured(self) -> bool:
        return self.ready and len(self.store.push_list()) > 0

    def describe(self) -> str:
        return f"{len(self.store.push_list())} Gerät(e) angemeldet"

    def push(self, title: str, body: str, url: str = "/#alarme", image: str | None = None,
             tag: str = "hornet", alert_id: int | None = None) -> str:
        from pywebpush import WebPushException, webpush

        if not self.s.webpush_sub:
            raise RuntimeError("Kontakt-E-Mail für App-Benachrichtigungen fehlt (Einrichtung)")
        subs = self.store.push_list()
        if not subs:
            raise RuntimeError("Kein Gerät angemeldet")
        payload = json.dumps({"title": title, "body": body, "url": url, "image": image, "tag": tag,
                              "alertId": alert_id}, ensure_ascii=False)
        ok, dead, errors = 0, 0, []
        for sub in subs:
            try:
                webpush(subscription_info=sub, data=payload, vapid_private_key=str(self.key_path),
                        vapid_claims={"sub": self.s.webpush_sub}, ttl=3600,
                        headers={"Urgency": "high"})
                ok += 1
            except WebPushException as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status in (404, 410):
                    self.store.push_remove(sub["endpoint"])
                    dead += 1
                else:
                    errors.append(str(e)[:120])
            except Exception as e:
                errors.append(f"{type(e).__name__}: {str(e)[:100]}")
        if ok == 0:
            raise RuntimeError("; ".join(errors) or "alle Abos abgelaufen")
        return f"an {ok} Gerät(e)" + (f", {dead} abgelaufen entfernt" if dead else "")

    def send_text(self, text: str) -> str:
        lines = text.strip().splitlines()
        return self.push(lines[0][:120], "\n".join(lines[1:])[:300] or lines[0])

    def send_photo(self, path: Path, caption: str, meta: dict | None = None) -> str:
        meta = meta or {}
        lines = caption.strip().splitlines()
        title = lines[0][:120]
        body = "\n".join(lines[1:])[:300] or title
        image = meta.get("image_url")
        return self.push(title, body, url=meta.get("url", "/#alarme"), image=image,
                         tag=meta.get("tag", "hornet"), alert_id=meta.get("alert_id"))
