"""Room retention (SPEC §4): idle lobbies expire, old games are deleted."""

from datetime import datetime, timedelta

from sqlalchemy import delete, or_, update
from sqlalchemy.orm import Session

from app.models import Room, RoomStatus

LOBBY_IDLE_LIMIT = timedelta(hours=24)
RETENTION = timedelta(days=30)


def cleanup_rooms(session: Session, now: datetime) -> None:
    """Expire lobbies idle for 24 h; delete finished or expired rooms older than 30 days."""
    session.execute(
        update(Room)
        .where(Room.status == RoomStatus.LOBBY, Room.updated_at < now - LOBBY_IDLE_LIMIT)
        .values(status=RoomStatus.EXPIRED, version=Room.version + 1)
    )
    session.execute(
        delete(Room).where(
            or_(
                (Room.status == RoomStatus.FINISHED) & (Room.finished_at < now - RETENTION),
                (Room.status == RoomStatus.EXPIRED) & (Room.updated_at < now - RETENTION),
            )
        )
    )
    session.commit()
