# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Verteiler: schickt einen Alarm parallel über alle konfigurierten Kanäle."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..config import Settings
from ..store import Store
from .base import Notifier
from .sms import AndroidSmsGateway
from .telegram import Telegram
from .webpush import WebPush
from .whatsapp import CallMeBot, WhatsAppCloud


class Hub:
    def __init__(self, s: Settings, store: Store):
        self.s = s
        self.telegram = Telegram(s)
        self.webpush = WebPush(s, store)
        self.channels: dict[str, Notifier] = {"telegram": self.telegram}
        if s.whatsapp_provider == "cloud":
            self.channels["whatsapp"] = WhatsAppCloud(s)
        elif s.whatsapp_provider == "callmebot":
            self.channels["whatsapp"] = CallMeBot(s)
        self.channels["sms"] = AndroidSmsGateway(s)
        self.channels["push"] = self.webpush

    def active(self) -> list[Notifier]:
        return [n for n in self.channels.values() if n.configured()]

    def status(self) -> list[dict]:
        rows = [{"name": n.name, "label": n.label, "configured": n.configured(),
                 "detail": n.describe() if n.configured() else "nicht eingerichtet",
                 "text_only": n.short and n.name != "sms"} for n in self.channels.values()]
        if self.s.whatsapp_provider == "none":
            rows.append({"name": "whatsapp", "label": "WhatsApp", "configured": False,
                         "detail": "nicht eingerichtet", "text_only": False})
        return rows

    # -- Versand ----------------------------------------------------------------------
    @staticmethod
    def _one(n: Notifier, phase: str, long_text: str, short_text: str, path: Path | None, meta: dict | None) -> dict | None:
        text = short_text if n.short else long_text
        t0 = time.time()
        try:
            if phase == "alarm":
                detail = n.send_photo(path, text, meta) if path else n.send_text(text)
            elif phase == "clip":
                if not (n.supports_video and path):
                    return None
                detail = n.send_video(path, text, meta)
            else:
                detail = n.send_text(text)
            return {"ok": True, "detail": detail, "ms": int((time.time() - t0) * 1000), "ts": time.time()}
        except Exception as e:
            return {"ok": False, "detail": f"{type(e).__name__}: {str(e)[:220]}", "ts": time.time()}

    def dispatch(self, phase: str, long_text: str, short_text: str, path: Path | None = None,
                 meta: dict | None = None, only: list[str] | None = None) -> dict:
        """phase: 'alarm' (Foto+Text), 'clip' (Video), 'text'. Rückgabe: {kanal: {phase: ergebnis}}"""
        targets = [n for n in self.active() if not only or n.name in only]
        results: dict[str, dict] = {}
        if not targets:
            return results
        with ThreadPoolExecutor(max_workers=len(targets)) as ex:
            futs = [(n, ex.submit(self._one, n, phase, long_text, short_text, path, meta)) for n in targets]
            for n, f in futs:
                res = f.result()
                if res is not None:
                    results.setdefault(n.name, {})[phase] = res
        return results

    def test_channel(self, name: str) -> dict:
        n = self.channels.get(name)
        if n is None or not n.configured():
            return {"ok": False, "detail": "Kanal nicht eingerichtet"}
        text = "Testnachricht von Hornet3000: Der Kanal funktioniert."
        if n.name == "push":
            r = self._one(n, "alarm", "Hornet3000 – Test\nBenachrichtigungen funktionieren.", "", None,
                          {"url": "/#live", "tag": "hornet-test"})
        else:
            r = self._one(n, "text", text, text, None, None)
        return r or {"ok": False, "detail": "kein Ergebnis"}
