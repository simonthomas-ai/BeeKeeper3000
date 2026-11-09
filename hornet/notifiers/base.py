from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, TypeVar

import httpx

T = TypeVar("T")


class Permanent(RuntimeError):
    """Fehler, bei dem ein erneuter Versuch sinnlos ist (falsches Token, ungültige Nummer …)."""


def with_retry(fn: Callable[[], T], tries: int = 3, delays: tuple[float, ...] = (1.0, 3.0)) -> T:
    last: Exception | None = None
    for i in range(tries):
        try:
            return fn()
        except Permanent:
            raise
        except (httpx.HTTPError, RuntimeError) as e:
            last = e
            if i < tries - 1:
                time.sleep(delays[min(i, len(delays) - 1)])
    assert last is not None
    raise last


class Notifier:
    name = "base"
    label = "Basis"
    short = False          # True: kurzer Text (SMS-artig), False: ausführlicher Text mit Zeilenumbrüchen
    supports_photo = False
    supports_video = False

    def configured(self) -> bool:
        return False

    def describe(self) -> str:
        return ""

    def send_text(self, text: str) -> str:
        raise NotImplementedError

    def send_photo(self, path: Path, caption: str, meta: dict | None = None) -> str:
        return self.send_text(caption)

    def send_video(self, path: Path, caption: str, meta: dict | None = None) -> str:
        raise Permanent("Video wird von diesem Kanal nicht unterstützt")


def mask(value: str, keep: int = 4) -> str:
    return "…" + value[-keep:] if len(value) > keep else "***"
