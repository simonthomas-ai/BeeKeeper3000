"""WhatsApp: offizielle Cloud-API von Meta (Text, Foto, Video) oder CallMeBot (nur Text, privat/kostenlos)."""
from __future__ import annotations

import re
from pathlib import Path

import httpx

from ..config import Settings
from .base import Notifier, Permanent, mask, with_retry

REENGAGEMENT = 131047  # Meta: 24-Stunden-Fenster abgelaufen -> nur noch Vorlagen (Templates) erlaubt


class WAError(Permanent):
    def __init__(self, code: int | None, msg: str, status: int):
        super().__init__(f"WhatsApp {code or status}: {msg}")
        self.code, self.status = code, status


def _digits(num: str) -> str:
    return re.sub(r"\D", "", num)


def _template_param(text: str) -> str:
    """Vorlagen-Parameter dürfen keine Zeilenumbrüche/Tabs und keine 4+ Leerzeichen in Folge enthalten."""
    t = re.sub(r"[\r\n\t]+", " | ", text)
    t = re.sub(r" {4,}", "   ", t)
    return t[:1000]


class WhatsAppCloud(Notifier):
    name = "whatsapp"
    label = "WhatsApp"
    supports_photo = True
    supports_video = True

    def __init__(self, s: Settings):
        self.s = s
        self.base = f"{s.whatsapp_api_base}/{s.whatsapp_api_version}/{s.whatsapp_phone_id}"
        self.to = [_digits(x) for x in s.whatsapp_to]

    def configured(self) -> bool:
        return bool(self.s.whatsapp_token and self.s.whatsapp_phone_id and self.to)

    def describe(self) -> str:
        tpl = f", Vorlage '{self.s.whatsapp_template}'" if self.s.whatsapp_template else ", keine Vorlage"
        return f"Cloud-API → {len(self.to)} Nummer(n){tpl}"

    # -- HTTP ---------------------------------------------------------------------------
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.s.whatsapp_token}"}

    def _check(self, r: httpx.Response) -> dict:
        try:
            j = r.json()
        except ValueError:
            j = {}
        if r.status_code >= 400:
            err = j.get("error", {}) if isinstance(j, dict) else {}
            code = err.get("code")
            msg = (err.get("error_data") or {}).get("details") or err.get("message") or f"HTTP {r.status_code}"
            if code == REENGAGEMENT:
                raise WAError(code, msg, r.status_code)
            if 400 <= r.status_code < 500 and r.status_code != 429:
                raise Permanent(str(WAError(code, msg, r.status_code)))
            raise RuntimeError(str(WAError(code, msg, r.status_code)))
        return j

    def _post(self, payload: dict) -> dict:
        try:
            r = httpx.post(f"{self.base}/messages", headers=self._headers(), json=payload, timeout=30)
        except httpx.HTTPError as e:
            raise RuntimeError(f"WhatsApp: {type(e).__name__}") from e
        return self._check(r)

    def _upload(self, path: Path, mime: str) -> str:
        try:
            r = httpx.post(f"{self.base}/media", headers=self._headers(),
                           data={"messaging_product": "whatsapp", "type": mime},
                           files={"file": (Path(path).name, Path(path).read_bytes(), mime)}, timeout=120)
        except httpx.HTTPError as e:
            raise RuntimeError(f"WhatsApp Upload: {type(e).__name__}") from e
        return self._check(r)["id"]

    def _template(self, to: str, text: str) -> None:
        tpl = self.s.whatsapp_template
        if not tpl:
            raise Permanent("24-h-Fenster abgelaufen und keine WHATSAPP_TEMPLATE konfiguriert – "
                            "kurz eine Nachricht an die Business-Nummer senden oder Vorlage anlegen")
        self._post({"messaging_product": "whatsapp", "to": to, "type": "template",
                    "template": {"name": tpl, "language": {"code": self.s.whatsapp_template_lang},
                                 "components": [{"type": "body",
                                                 "parameters": [{"type": "text", "text": _template_param(text)}]}]}})

    # -- Senden -------------------------------------------------------------------------
    def _to_each(self, build, fallback_text: str) -> str:
        errors, via_tpl = [], 0
        for to in self.to:
            try:
                try:
                    with_retry(lambda t=to: self._post(build(t)))
                except WAError as e:
                    if e.code != REENGAGEMENT:
                        raise
                    with_retry(lambda t=to: self._template(t, fallback_text))
                    via_tpl += 1
            except Exception as e:
                errors.append(f"{to[-4:]}: {e}")
        if errors and len(errors) == len(self.to):
            raise RuntimeError("; ".join(errors))
        ok = len(self.to) - len(errors)
        return f"an {ok}/{len(self.to)} Nummer(n)" + (f", davon {via_tpl}× per Vorlage (Text ohne Medien)" if via_tpl else "") \
            + (f" (Fehler: {'; '.join(errors)})" if errors else "")

    def send_text(self, text: str) -> str:
        return self._to_each(lambda to: {"messaging_product": "whatsapp", "to": to, "type": "text",
                                         "text": {"body": text[:4000], "preview_url": False}}, text)

    def send_photo(self, path: Path, caption: str, meta: dict | None = None) -> str:
        media_id = with_retry(lambda: self._upload(path, "image/jpeg"))
        return self._to_each(lambda to: {"messaging_product": "whatsapp", "to": to, "type": "image",
                                         "image": {"id": media_id, "caption": caption[:1000]}}, caption)

    def send_video(self, path: Path, caption: str, meta: dict | None = None) -> str:
        media_id = with_retry(lambda: self._upload(path, "video/mp4"))
        return self._to_each(lambda to: {"messaging_product": "whatsapp", "to": to, "type": "video",
                                         "video": {"id": media_id, "caption": caption[:1000]}}, caption)


class CallMeBot(Notifier):
    """Kostenloser privater Dienst (nur Text). Einrichtung: https://www.callmebot.com/blog/free-api-whatsapp-messages/"""
    name = "whatsapp"
    label = "WhatsApp (CallMeBot)"
    short = True

    def __init__(self, s: Settings):
        self.s = s

    def configured(self) -> bool:
        return bool(self.s.callmebot_phone and self.s.callmebot_apikey)

    def describe(self) -> str:
        return f"CallMeBot → {mask(self.s.callmebot_phone)} (nur Text)"

    def send_text(self, text: str) -> str:
        def go():
            try:
                r = httpx.get(self.s.callmebot_url, params={
                    "phone": self.s.callmebot_phone, "text": text[:1500], "apikey": self.s.callmebot_apikey}, timeout=30)
            except httpx.HTTPError as e:
                raise RuntimeError(f"CallMeBot: {type(e).__name__}") from e
            if r.status_code == 200:
                return "gesendet"
            if 400 <= r.status_code < 500:
                raise Permanent(f"CallMeBot HTTP {r.status_code}: {r.text[:120]}")
            raise RuntimeError(f"CallMeBot HTTP {r.status_code}")
        return with_retry(go)
