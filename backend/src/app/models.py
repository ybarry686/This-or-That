"""Database models for rooms, participants, and submissions."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_id() -> str:
    return uuid.uuid4().hex


class RoomStatus(StrEnum):
    LOBBY = "lobby"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    EXPIRED = "expired"


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(6), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[RoomStatus] = mapped_column(
        Enum(RoomStatus, name="room_status", values_callable=lambda e: [m.value for m in e]),
        default=RoomStatus.LOBBY,
    )
    max_participants: Mapped[int] = mapped_column(Integer, default=20)
    max_submissions: Mapped[int] = mapped_column(Integer, default=3)
    vote_seconds: Mapped[int] = mapped_column(Integer, default=30)
    version: Mapped[int] = mapped_column(Integer, default=0)
    seed: Mapped[int | None] = mapped_column(Integer, default=None)
    host_participant_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "participants.id",
            use_alter=True,
            ondelete="SET NULL",
            name="rooms_host_participant_id_fkey",
        ),
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    host: Mapped["Participant | None"] = relationship(foreign_keys=[host_participant_id])
    participants: Mapped[list["Participant"]] = relationship(
        foreign_keys="Participant.room_id",
        back_populates="room",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Participant.joined_at",
    )
    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Submission.created_at",
    )


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("room_id", "nickname"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    nickname: Mapped[str] = mapped_column(String(20))
    avatar: Mapped[int] = mapped_column(Integer)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # Set only on the room creator: lets them reclaim the host role from any device.
    recovery_hash: Mapped[str | None] = mapped_column(String(64), unique=True, default=None)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    room: Mapped[Room] = relationship(foreign_keys=[room_id], back_populates="participants")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    # Duplicate-merge key: the normalized text, or the target key when the host merges options.
    key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    room: Mapped[Room] = relationship(back_populates="submissions")
