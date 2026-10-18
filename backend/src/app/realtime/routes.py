"""Room WebSocket: presence, event delivery, and lobby host hand-off (SPEC §3, §9).

Clients receive `{type, version, data}` events and refetch the REST snapshot whenever they see one
(or detect a version gap). Client-to-server messages are ignored for now.
"""

import logging

import anyio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from app.db import SessionLocal
from app.errors import AppError, NotFound
from app.models import Room, RoomStatus
from app.realtime.hub import event, hub
from app.rooms import service
from app.tournament import timers

router = APIRouter()
logger = logging.getLogger(__name__)

CLOSE_UNAUTHORIZED = 4401
CLOSE_NOT_FOUND = 4404


def _authenticate(code: str, token: str | None) -> tuple[str, str]:
    with SessionLocal() as session:
        room = service.load_room(session, code)
        return room.id, service.authenticate(session, room, token).id


def _bump(room_id: str) -> tuple[int, bool]:
    with SessionLocal() as session:
        room = service.record_presence_change(session, room_id)
        return room.version, room.status is RoomStatus.LOBBY


def _host_timer_key(room_id: str) -> str:
    return f"host-grace:{room_id}"


async def _hand_off_host(room_id: str, absent_host_id: str) -> None:
    def hand_off():
        with SessionLocal() as session:
            return service.hand_off_host(
                session, room_id, absent_host_id, hub.connected_ids(room_id)
            )

    room = await run_in_threadpool(hand_off)
    if room is not None:
        await hub.broadcast(
            room_id,
            event("host_changed", room.version, {"host_participant_id": room.host_participant_id}),
        )


@router.websocket("/rooms/{code}/ws")
async def room_socket(websocket: WebSocket, code: str, token: str | None = None) -> None:
    try:
        room_id, participant_id = await run_in_threadpool(_authenticate, code, token)
    except AppError as error:
        close_code = CLOSE_NOT_FOUND if isinstance(error, NotFound) else CLOSE_UNAUTHORIZED
        await websocket.close(code=close_code, reason=error.detail)
        return

    await websocket.accept()
    if await _is_host(room_id, participant_id):
        hub.cancel(_host_timer_key(room_id))
    first = hub.add(room_id, participant_id, websocket)
    # From here on the socket is registered, so every exit path must run the cleanup below.
    try:
        if first:
            version, _ = await run_in_threadpool(_bump, room_id)
            # Tell everyone else first: this client may vanish before it reads its welcome.
            await hub.broadcast(
                room_id,
                event("participant_connected", version, {"participant_id": participant_id}),
                exclude=websocket,
            )
        else:
            version = await run_in_threadpool(_current_version, room_id)
        await websocket.send_json(event("welcome", version))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        # A client that went away mid-send; treat it like any other disconnect.
        logger.info("Room socket for %s closed unexpectedly", participant_id, exc_info=True)
    finally:
        # Shielded so presence cleanup completes even if the handler is being cancelled.
        with anyio.CancelScope(shield=True):
            if hub.remove(room_id, participant_id, websocket):
                await _on_last_disconnect(room_id, participant_id)


async def _on_last_disconnect(room_id: str, participant_id: str) -> None:
    try:
        version, in_lobby = await run_in_threadpool(_bump, room_id)
    except NotFound:
        return
    await hub.broadcast(
        room_id, event("participant_disconnected", version, {"participant_id": participant_id})
    )
    if in_lobby and await _is_host(room_id, participant_id):
        hub.schedule(
            _host_timer_key(room_id),
            hub.host_grace_seconds,
            lambda: _hand_off_host(room_id, participant_id),
        )
    elif not in_lobby:
        # Everyone still connected may now have voted.
        await timers.check_everyone_voted(room_id)


def _current_version(room_id: str) -> int:
    with SessionLocal() as session:
        room = session.get(Room, room_id)
        return room.version if room else 0


async def _is_host(room_id: str, participant_id: str) -> bool:
    def check() -> bool:
        with SessionLocal() as session:
            room = session.get(Room, room_id)
            return room is not None and room.host_participant_id == participant_id

    return await run_in_threadpool(check)
