"""Database models for rooms, participants, submissions, and the tournament."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
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


class MatchupStatus(StrEnum):
    PENDING = "pending"  # not reached yet (or waiting for its slots to fill)
    VOTING = "voting"  # open for the first vote
    REVOTE = "revote"  # tied once; sudden-death revote open
    DECIDED = "decided"  # has a winner (including byes)


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
    contenders: Mapped[list["Contender"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="Contender.position"
    )
    matchups: Mapped[list["Matchup"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: [Matchup.round, Matchup.index],
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


class Contender(Base):
    """An option frozen into the bracket when the tournament starts.

    Its submissions (and so every submitter) are the room's submissions with the same `key`.
    """

    __tablename__ = "contenders"
    __table_args__ = (UniqueConstraint("room_id", "key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(Text)
    display_text: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)


class Matchup(Base):
    __tablename__ = "matchups"
    __table_args__ = (UniqueConstraint("room_id", "round", "index"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    round: Mapped[int] = mapped_column(Integer)
    index: Mapped[int] = mapped_column(Integer)
    contender_a_id: Mapped[str | None] = mapped_column(
        ForeignKey("contenders.id", ondelete="CASCADE"), default=None
    )
    contender_b_id: Mapped[str | None] = mapped_column(
        ForeignKey("contenders.id", ondelete="CASCADE"), default=None
    )
    winner_id: Mapped[str | None] = mapped_column(
        ForeignKey("contenders.id", ondelete="CASCADE"), default=None
    )
    is_bye: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[MatchupStatus] = mapped_column(
        Enum(MatchupStatus, name="matchup_status", values_callable=lambda e: [m.value for m in e]),
        default=MatchupStatus.PENDING,
    )
    # How the winner was decided: "votes", "coin_flip", or "bye".
    outcome: Mapped[str | None] = mapped_column(String(16), default=None)
    # Tally of the most recently closed phase (the tie during a revote, the final result after).
    votes_a: Mapped[int] = mapped_column(Integer, default=0)
    votes_b: Mapped[int] = mapped_column(Integer, default=0)
    # When the matchup first opened: only participants who joined by then may vote in it.
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Voting window of the current phase. Votes are accepted from starts_at until ends_at.
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    votes: Mapped[list["Vote"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class Vote(Base):
    """A participant's current choice in one phase (0 = vote, 1 = revote) of a matchup."""

    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("matchup_id", "participant_id", "phase"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    matchup_id: Mapped[str] = mapped_column(
        ForeignKey("matchups.id", ondelete="CASCADE"), index=True
    )
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"))
    contender_id: Mapped[str] = mapped_column(ForeignKey("contenders.id", ondelete="CASCADE"))
    phase: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
