# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""TESTATTRAPPE – nur für Tests, gehört nicht zum Programm.

Simuliert ein MeshCore-Funkgerät im Companion-Modus auf einem Pseudo-Terminal (pty). Es spricht die Rahmen so,
wie sie die offizielle Python-Bibliothek `meshcore` erwartet bzw. erzeugt (Byte-Layouts dort nachgelesen). Damit
lässt sich der Client prüfen, ohne Hardware – es ersetzt KEINEN Test an einem echten Funkgerät.
"""
from __future__ import annotations

import os
import struct
import threading
import time
import tty

FREQ_KHZ, BW_HZ, SF, CR = 869525, 62500, 8, 5


class FakeMeshDevice:
    def __init__(self, name: str = "TESTSTAND-Funk", channels: dict[int, tuple[str, bytes]] | None = None,
                 fw_ver: int = 3):
        self.name = name
        self.channels = dict(channels if channels is not None else {1: ("hornet3000", bytes(range(16)))})
        self.sent: list[tuple[int, str]] = []          # (Kanal, Text), was die App gesendet hat
        self.set_channel_calls: list[tuple[int, str, bytes]] = []
        self.commands: list[int] = []
        self.pending: list[bytes] = []                  # fertige Antwortrahmen für SYNC_NEXT_MESSAGE
        self.fail_next_send = False
        self.silent = False                             # antwortet nicht mehr
        self.clock_set: int | None = None
        self.fw_ver = fw_ver
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._master, self._slave = os.openpty()
        tty.setraw(self._slave)
        self.path = os.ttyname(self._slave)
        self._buf = bytearray()
        self._t = threading.Thread(target=self._loop, daemon=True, name="fake-mesh-device")
        self._t.start()

    # -- Steuerung durch den Test ------------------------------------------------------------------
    def inject_channel_text(self, text: str, channel: int = 1, sender: str = "Nachbar", v3: bool = True,
                            push: bool = True) -> None:
        body = f"{sender}: {text}".encode("utf-8")
        ts = struct.pack("<I", int(time.time()))
        if v3:
            frame = bytes([17]) + struct.pack("<b", 28) + b"\0\0" + bytes([channel, 2, 0]) + ts + body
        else:
            frame = bytes([8, channel, 2, 0]) + ts + body
        with self._lock:
            self.pending.append(frame)
        if push:
            self._write(bytes([0x83]))

    def inject_raw_pending(self, frame: bytes, push: bool = True) -> None:
        with self._lock:
            self.pending.append(frame)
        if push:
            self._write(bytes([0x83]))

    def write_garbage(self, data: bytes) -> None:
        os.write(self._master, data)

    def close(self) -> None:
        self._stop.set()
        self._t.join(timeout=2)   # erst den Thread beenden, dann die Deskriptoren schließen (Nummern werden wiederverwendet)
        for fd in (self._master, self._slave):
            try:
                os.close(fd)
            except OSError:
                pass

    # -- Protokoll --------------------------------------------------------------------------------------
    def _write(self, payload: bytes) -> None:
        if self.silent:
            return
        try:
            os.write(self._master, b">" + len(payload).to_bytes(2, "little") + payload)
        except OSError:
            pass

    def _loop(self) -> None:
        import select
        while not self._stop.is_set():
            try:
                r, _, _ = select.select([self._master], [], [], 0.1)
                if not r:
                    continue
                data = os.read(self._master, 4096)
            except OSError:
                return
            self._buf += data
            while True:
                i = self._buf.find(b"<")
                if i < 0:
                    self._buf.clear()
                    break
                del self._buf[:i]
                if len(self._buf) < 3:
                    break
                n = self._buf[1] | (self._buf[2] << 8)
                if len(self._buf) < 3 + n:
                    break
                payload = bytes(self._buf[3:3 + n])
                del self._buf[:3 + n]
                self._handle(payload)

    def _self_info(self) -> bytes:
        return (bytes([5, 1, 14, 22]) + bytes(range(32)) + struct.pack("<ii", 0, 0) + b"\0\0\0\0"
                + struct.pack("<II", FREQ_KHZ, BW_HZ) + bytes([SF, CR]) + self.name.encode())

    def _handle(self, p: bytes) -> None:
        cmd = p[0]
        self.commands.append(cmd)
        if self.silent:
            return
        if cmd == 1:                                   # APP_START
            self._write(self._self_info())
        elif cmd == 22:                                # DEVICE_QUERY
            self._write(bytes([13, self.fw_ver, 50, 8]) + (1234).to_bytes(4, "little") + b"build".ljust(12, b"\0")
                        + b"FakeBoard".ljust(40, b"\0") + b"v1.0".ljust(20, b"\0"))
        elif cmd == 31:                                # GET_CHANNEL
            idx = p[1]
            if idx in self.channels:
                name, secret = self.channels[idx]
                self._write(bytes([18, idx]) + name.encode().ljust(32, b"\0") + secret)
            else:
                self._write(bytes([1, 2]))
        elif cmd == 32:                                # SET_CHANNEL
            idx, name, secret = p[1], p[2:34].split(b"\0", 1)[0].decode(), bytes(p[34:50])
            self.channels[idx] = (name, secret)
            self.set_channel_calls.append((idx, name, secret))
            self._write(bytes([0]))
        elif cmd == 6:                                 # SET_DEVICE_TIME
            self.clock_set = struct.unpack_from("<I", p, 1)[0]
            self._write(bytes([0]))
        elif cmd == 3:                                 # SEND_CHANNEL_TXT_MSG
            if self.fail_next_send:
                self.fail_next_send = False
                self._write(bytes([1, 3]))
                return
            idx, text = p[2], p[7:].decode("utf-8", "replace")
            self.sent.append((idx, text))
            self._write(bytes([0]))                    # Kanaltext wird mit OK quittiert (Bibliothek erwartet OK/ERROR)
        elif cmd == 10:                                # SYNC_NEXT_MESSAGE
            with self._lock:
                frame = self.pending.pop(0) if self.pending else None
            self._write(frame if frame is not None else bytes([10]))
        else:
            self._write(bytes([1, 1]))
