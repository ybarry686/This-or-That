"""Server-owned voting deadlines and early closes outside a request (SPEC §7, §9).

One timer per room fires at the open phase's `ends_at`. Whenever the phase may have changed,
`sync_deadline` re-reads the database and reschedules (or cancels) it, so the database stays the
source of truth and a stale timer can never close the wrong phase.
"""

from datetime import datetime

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Room, RoomStatus
from app.realtime.hub import hub
from app.tournament import service
from app.tournament.service import Event
from app.tournament.snapshot import current_matchup


def _key(room_id: str) -> str:
    return f"deadline:{room_id}"


def _current_deadline(room_id: str) -> tuple[str, datetime] | None:
    with SessionLocal() as session:
        room = session.get(Room, room_id)
        if room is None or room.status is not RoomStatus.IN_PROGRESS:
            return None
        matchup = current_matchup(room)
        return (matchup.id, matchup.ends_at) if matchup else None


async def sync_deadline(room_id: str) -> None:
    deadline = await run_in_threadpool(_current_deadline, room_id)
    if deadline is None:
        hub.cancel(_key(room_id))
        return
    matchup_id, ends_at = deadline
    delay = max(0.0, (ends_at - service.utcnow()).total_seconds())
    hub.schedule(_key(room_id), delay, lambda: _on_deadline(room_id, matchup_id, ends_at))


def expire_phase(room_id: str, matchup_id: str, ends_at: datetime) -> list[Event]:
    """Close the phase whose deadline passed, unless the room has already moved on."""
    with SessionLocal() as session:
        room = session.get(Room, room_id, with_for_update=True)
        if room is None or room.status is not RoomStatus.IN_PROGRESS:
            return []
        matchup = current_matchup(room)
        if matchup is None or matchup.id != matchup_id or matchup.ends_at != ends_at:
            return []
        events = service.close_phase(room, matchup, service.utcnow())
        session.commit()
        return events


async def _publish(room_id: str, events: list[Event]) -> None:
    for type, version, data in events:
        await hub.publish(room_id, type, version, data)


async def _on_deadline(room_id: str, matchup_id: str, ends_at: datetime) -> None:
    events = await run_in_threadpool(expire_phase, room_id, matchup_id, ends_at)
    await _publish(room_id, events)
    await sync_deadline(room_id)


def _close_if_everyone_voted(room_id: str) -> list[Event]:
    with SessionLocal() as session:
        room = session.get(Room, room_id, with_for_update=True)
        if room is None or room.status is not RoomStatus.IN_PROGRESS:
            return []
        matchup = current_matchup(room)
        if matchup is None:
            return []
        events = service.close_if_everyone_voted(
            room, matchup, hub.connected_ids(room_id), service.utcnow()
        )
        session.commit()
        return events


async def check_everyone_voted(room_id: str) -> None:
    """Re-check the early-close rule after someone disconnects (SPEC §7)."""
    events = await run_in_threadpool(_close_if_everyone_voted, room_id)
    if events:
        await _publish(room_id, events)
        await sync_deadline(room_id)


def _running_room_ids() -> list[str]:
    with SessionLocal() as session:
        return list(session.scalars(select(Room.id).where(Room.status == RoomStatus.IN_PROGRESS)))


async def recover_deadlines() -> None:
    """Reschedule every running room's deadline after a (re)start; overdue ones fire at once."""
    for room_id in await run_in_threadpool(_running_room_ids):
        await sync_deadline(room_id)
