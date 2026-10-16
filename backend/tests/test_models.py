import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Participant, Room, RoomStatus, Submission


def make_room(session, code="ABC234", **kwargs) -> Room:
    room = Room(code=code, title="Where to eat?", **kwargs)
    session.add(room)
    session.flush()
    return room


def make_participant(session, room, nickname="Sam", token_hash=None) -> Participant:
    participant = Participant(
        room_id=room.id, nickname=nickname, avatar=0, token_hash=token_hash or f"hash-{nickname}"
    )
    session.add(participant)
    session.flush()
    return participant


def test_room_defaults(session):
    room = make_room(session)

    assert room.status is RoomStatus.LOBBY
    assert room.version == 0
    assert room.max_participants == 20
    assert room.max_submissions == 3
    assert room.vote_seconds == 30
    assert room.description == ""
    assert room.seed is None
    assert room.created_at is not None


def test_room_code_is_unique(session):
    make_room(session, code="ABC234")

    with pytest.raises(IntegrityError):
        make_room(session, code="ABC234")


def test_nickname_unique_within_room_but_not_across_rooms(session):
    room_a = make_room(session, code="AAAAAA")
    room_b = make_room(session, code="BBBBBB")
    make_participant(session, room_a, "Sam", token_hash="h1")
    make_participant(session, room_b, "Sam", token_hash="h2")

    with pytest.raises(IntegrityError):
        make_participant(session, room_a, "Sam", token_hash="h3")


def test_token_hash_is_unique(session):
    room = make_room(session)
    make_participant(session, room, "Sam", token_hash="same")

    with pytest.raises(IntegrityError):
        make_participant(session, room, "Alex", token_hash="same")


def test_deleting_room_cascades(session):
    room = make_room(session)
    participant = make_participant(session, room)
    session.add(
        Submission(room_id=room.id, participant_id=participant.id, text="Pizza", key="pizza")
    )
    session.flush()

    session.delete(room)
    session.flush()

    assert session.scalars(select(Participant)).all() == []
    assert session.scalars(select(Submission)).all() == []


def test_room_host_relationship(session):
    room = make_room(session)
    host = make_participant(session, room)
    room.host_participant_id = host.id
    session.flush()

    assert room.host.nickname == "Sam"
