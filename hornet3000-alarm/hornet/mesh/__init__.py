# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Funknetz zwischen den Stationen: LoRa (MeshCore) und Freenet (River) als zwei unabhängige Übertragungswege."""
from __future__ import annotations

import logging
from pathlib import Path

from ..config import Settings
from .service import MeshService
from .transport import Transport

log = logging.getLogger("hornet.mesh")


def build_transports(s: Settings) -> tuple[dict[str, Transport], list[str]]:
    """Erzeugt die eingeschalteten Wege. Fehlerhafte Einstellungen schalten nur den betroffenen Weg ab
    (mit lesbarer Meldung), nie das ganze Programm."""
    out: dict[str, Transport] = {}
    problems: list[str] = []
    if s.mesh_lora_enabled:
        try:
            from .lora import LoraTransport

            out["lora"] = LoraTransport(s.mesh_lora_port or "auto", s.mesh_lora_baud, s.mesh_lora_channel_idx,
                                        s.mesh_lora_channel_name, s.mesh_lora_channel_key, s.mesh_lora_duty)
        except Exception as e:
            problems.append(f"LoRa: {e}")
    if s.mesh_freenet_enabled:
        try:
            from .freenet import FreenetTransport

            out["freenet"] = FreenetTransport(s.mesh_freenet_riverctl, s.mesh_freenet_room, s.mesh_freenet_node,
                                              s.data_dir / "river")
        except Exception as e:
            problems.append(f"Freenet: {e}")
    for p in problems:
        log.error("Funknetz: %s", p)
    return out, problems


def create_service(s: Settings, store, *, bus=None, hub=None, forward_ok=None) -> tuple[MeshService, list[str]]:
    transports, problems = build_transports(s)
    return MeshService(s, store, transports, bus=bus, hub=hub, forward_ok=forward_ok), problems
