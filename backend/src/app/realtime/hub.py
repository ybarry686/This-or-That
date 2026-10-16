"""In-process registry of room WebSocket connections (single-instance deployment, SPEC §11)."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import WebSocket

from app.config import get_settings


def event(type: str, version: int, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": type, "version": version, "data": data or {}}


class RoomHub:
    def __init__(self) -> None:
        self.host_grace_seconds: float = get_settings().host_grace_seconds
        self._sockets: dict[str, dict[str, set[WebSocket]]] = {}
        self._timers: dict[str, asyncio.Task] = {}

    def connected_ids(self, room_id: str) -> set[str]:
        return set(self._sockets.get(room_id, {}))

    def add(self, room_id: str, participant_id: str, websocket: WebSocket) -> bool:
        """Register a socket; True if this participant was not connected before."""
        sockets = self._sockets.setdefault(room_id, {}).setdefault(participant_id, set())
        sockets.add(websocket)
        return len(sockets) == 1

    def remove(self, room_id: str, participant_id: str, websocket: WebSocket) -> bool:
        """Unregister a socket; True if this was the participant's last one."""
        room = self._sockets.get(room_id, {})
        sockets = room.get(participant_id, set())
        sockets.discard(websocket)
        if sockets:
            return False
        room.pop(participant_id, None)
        if not room:
            self._sockets.pop(room_id, None)
        return True

    async def broadcast(
        self, room_id: str, message: dict[str, Any], exclude: WebSocket | None = None
    ) -> None:
        targets = [
            ws
            for sockets in self._sockets.get(room_id, {}).values()
            for ws in sockets
            if ws is not exclude
        ]
        for ws in targets:
            # A socket that is closing will be cleaned up by its own handler.
            with contextlib.suppress(Exception):
                await ws.send_json(message)

    async def publish(
        self, room_id: str, type: str, version: int, data: dict[str, Any] | None = None
    ) -> None:
        await self.broadcast(room_id, event(type, version, data))

    def schedule(self, key: str, delay: float, callback: Callable[[], Awaitable[None]]) -> None:
        """Run `callback` after `delay` seconds unless cancelled or rescheduled first."""
        self.cancel(key)

        async def run() -> None:
            await asyncio.sleep(delay)
            self._timers.pop(key, None)
            await callback()

        self._timers[key] = asyncio.create_task(run())

    def cancel(self, key: str) -> None:
        task = self._timers.pop(key, None)
        if task is not None:
            task.cancel()

    def reset(self) -> None:
        for task in self._timers.values():
            task.cancel()
        self._timers.clear()
        self._sockets.clear()


hub = RoomHub()
