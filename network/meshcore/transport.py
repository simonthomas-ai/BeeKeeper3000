"""Optional MeshCore companion-radio adapter. Imports upstream code lazily."""
from __future__ import annotations

import inspect

from .protocol import encode_event, MeshCoreProtocolError, MAX_WIRE_BYTES


class MeshCoreTransportError(RuntimeError):
    """MeshCore configuration, connection or transmission error."""


class MeshCoreSerialTransport:
    def __init__(self, *, port: str, channel: int, data_type: int,
                 station_id: str, signing_key, baudrate: int = 115200,
                 key_id: str | None = None):
        if not isinstance(port, str) or not port.strip():
            raise ValueError("serial port is required")
        if not 0 <= channel <= 255:
            raise ValueError("MeshCore channel must be 0..255")
        if not 1 <= data_type <= 65535:
            raise ValueError("MeshCore data type must be 1..65535")
        if not isinstance(station_id, str) or not station_id:
            raise ValueError("station_id is required")
        if not 300 <= baudrate <= 2_000_000:
            raise ValueError("invalid serial baud rate")
        self.port = port
        self.channel = channel
        self.data_type = data_type
        self.station_id = station_id
        self.signing_key = signing_key
        self.baudrate = baudrate
        self.key_id = key_id
        self._meshcore = None

    async def connect(self):
        if self._meshcore is not None:
            return self._meshcore
        try:
            from meshcore import MeshCore, EventType
        except ImportError as exc:
            raise MeshCoreTransportError(
                "Optional dependency missing: install network/meshcore/requirements.txt"
            ) from exc
        try:
            client = await MeshCore.create_serial(self.port, self.baudrate)
        except Exception as exc:
            raise MeshCoreTransportError(f"Could not connect to MeshCore radio on {self.port}") from exc
        if client is None or not client.is_connected:
            raise MeshCoreTransportError("MeshCore companion radio did not connect")
        self._meshcore = client
        self._event_type_error = EventType.ERROR
        return client

    async def send_event(self, event: dict):
        if self._meshcore is None:
            raise MeshCoreTransportError("Connect to the MeshCore radio first")
        if event.get("station_id") != self.station_id:
            raise MeshCoreTransportError("event station_id does not match this station")
        try:
            payload = encode_event(event, self.signing_key, key_id=self.key_id)
        except MeshCoreProtocolError as exc:
            raise MeshCoreTransportError(str(exc)) from exc
        if len(payload) > MAX_WIRE_BYTES:
            raise MeshCoreTransportError("MeshCore payload exceeds 163 bytes")
        try:
            result = await self._meshcore.commands.send_channel_data(self.channel, self.data_type, payload)
        except Exception as exc:
            raise MeshCoreTransportError("MeshCore channel-data transmission failed") from exc
        if result is None or result.type == self._event_type_error:
            reason = getattr(result, "payload", "no radio acknowledgement")
            raise MeshCoreTransportError(f"MeshCore rejected the event: {reason}")
        return {"bytes": len(payload), "channel": self.channel, "data_type": self.data_type}

    async def subscribe(self, callback):
        """Subscribe to raw channel-data events for this configured channel/type."""
        if self._meshcore is None:
            raise MeshCoreTransportError("Connect to the MeshCore radio first")
        from meshcore import EventType

        async def filtered(event):
            data = event.payload if isinstance(event.payload, dict) else {}
            if data.get("channel_idx") != self.channel or data.get("data_type") != self.data_type:
                return
            try:
                raw = bytes.fromhex(data.get("payload", ""))
                result = callback(raw)
                if inspect.isawaitable(result):
                    await result
            except (ValueError, TypeError):
                return

        return self._meshcore.subscribe(EventType.CHANNEL_DATA_RECV, filtered)

    async def disconnect(self):
        if self._meshcore is None:
            return
        client, self._meshcore = self._meshcore, None
        try:
            await client.disconnect()
        except Exception as exc:
            raise MeshCoreTransportError("Error disconnecting MeshCore radio") from exc
