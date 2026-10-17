import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Contender,
    Matchup,
    MatchupStatus,
    Participant,
    Room,
    RoomStatus,
    Submission,
    Vote,
)


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


def make_contender(session, room, key="pizza") -> Contender:
    contender = Contender(room_id=room.id, key=key, display_text=key.title())
    session.add(contender)
    session.flush()
    return contender


def test_contender_key_is_unique_within_a_room(session):
    room = make_room(session)
    make_contender(session, room, "pizza")

    with pytest.raises(IntegrityError):
        make_contender(session, room, "pizza")


def test_matchup_defaults_and_position_uniqueness(session):
    room = make_room(session)
    a, b = make_contender(session, room, "a"), make_contender(session, room, "b")
    matchup = Matchup(room_id=room.id, round=0, index=0, contender_a_id=a.id, contender_b_id=b.id)
    session.add(matchup)
    session.flush()

    assert matchup.status is MatchupStatus.PENDING
    assert (matchup.votes_a, matchup.votes_b) == (0, 0)
    assert matchup.winner_id is None and matchup.outcome is None
    assert matchup.is_bye is False

    session.add(Matchup(room_id=room.id, round=0, index=0))
    with pytest.raises(IntegrityError):
        session.flush()


def test_one_vote_per_participant_per_phase(session):
    room = make_room(session)
    voter = make_participant(session, room)
    a, b = make_contender(session, room, "a"), make_contender(session, room, "b")
    matchup = Matchup(room_id=room.id, round=0, index=0, contender_a_id=a.id, contender_b_id=b.id)
    session.add(matchup)
    session.flush()

    session.add(Vote(matchup_id=matchup.id, participant_id=voter.id, contender_id=a.id, phase=0))
    session.add(Vote(matchup_id=matchup.id, participant_id=voter.id, contender_id=b.id, phase=1))
    session.flush()

    session.add(Vote(matchup_id=matchup.id, participant_id=voter.id, contender_id=b.id, phase=0))
    with pytest.raises(IntegrityError):
        session.flush()


def test_deleting_room_cascades_tournament_rows(session):
    room = make_room(session)
    voter = make_participant(session, room)
    a, b = make_contender(session, room, "a"), make_contender(session, room, "b")
    matchup = Matchup(room_id=room.id, round=0, index=0, contender_a_id=a.id, contender_b_id=b.id)
    session.add(matchup)
    session.flush()
    session.add(Vote(matchup_id=matchup.id, participant_id=voter.id, contender_id=a.id, phase=0))
    session.flush()

    session.delete(room)
    session.flush()

    assert session.scalars(select(Contender)).all() == []
    assert session.scalars(select(Matchup)).all() == []
    assert session.scalars(select(Vote)).all() == []
