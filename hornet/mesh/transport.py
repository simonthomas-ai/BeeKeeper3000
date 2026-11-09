"""Gemeinsame Schnittstelle der Übertragungswege (LoRa/MeshCore, Freenet/River)."""
from __future__ import annotations

from typing import Callable

ReceiveFn = Callable[[str, str, float], None]  # (Text, Weg, Zeitpunkt)


class TransportError(RuntimeError):
    """Senden oder Verbinden ist fehlgeschlagen (Meldung ist für den Betreiber lesbar)."""


class Transport:
    name = "base"
    label = "Basis"
    max_bytes = 118

    def __init__(self) -> None:
        self.on_receive: ReceiveFn | None = None

    # Lebenszyklus
    def start(self, on_receive: ReceiveFn) -> None:
        self.on_receive = on_receive

    def stop(self) -> None:
        pass

    # Senden – blockiert höchstens kurz, wirft TransportError
    def send(self, text: str) -> None:
        raise NotImplementedError

    def can_send_now(self, text: str, now: float) -> bool:
        """Darf jetzt gesendet werden (z. B. Sendezeit-Budget)?"""
        return True

    def status(self) -> dict:
        return {"name": self.name, "label": self.label, "online": False, "detail": ""}
