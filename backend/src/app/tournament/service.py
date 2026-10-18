"""Tournament rules: start, vote, close a phase, advance the bracket (SPEC §6-§8).

Like the lobby service, every mutation locks the room row and bumps `room.version`. Functions
return the events to broadcast as `(type, version, data)` tuples; callers publish them after the
commit.
"""

import random
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.engine.bracket import Bracket, generate_bracket
from app.engine.bracket import Matchup as EngineMatchup
from app.engine.tally import Outcome, resolve_matchup
from app.errors import Conflict, Forbidden, Invalid
from app.models import Contender, Matchup, MatchupStatus, Room, RoomStatus, Vote, new_id
from app.rooms import service as rooms
from app.tournament.snapshot import current_matchup, eligible_participants, phase, phase_votes

Event = tuple[str, int, dict[str, Any]]

# Coin flips for tied revotes. Replaced with a stub in tests.
coin: random.Random = random.SystemRandom()

MIN_CONTENDERS = 2


def utcnow() -> datetime:
    return datetime.now(UTC)


def _require_running(room: Room) -> None:
    if room.status is not RoomStatus.IN_PROGRESS:
        raise Conflict("The tournament is not running.")


def _find_open(room: Room, matchup_id: str) -> Matchup:
    current = current_matchup(room)
    if current is None or current.id != matchup_id:
        raise Conflict("This matchup is not open for voting.")
    return current


def _engine_bracket(room: Room) -> Bracket:
    round_count = max(m.round for m in room.matchups) + 1
    rounds: list[list[EngineMatchup]] = [[] for _ in range(round_count)]
    for m in sorted(room.matchups, key=lambda m: (m.round, m.index)):
        rounds[m.round].append(
            EngineMatchup(
                round=m.round,
                index=m.index,
                a=m.contender_a_id,
                b=m.contender_b_id,
                winner=m.winner_id,
                is_bye=m.is_bye,
            )
        )
    return Bracket(seed=room.seed, rounds=rounds)


def _row(room: Room, round: int, index: int) -> Matchup:
    return next(m for m in room.matchups if m.round == round and m.index == index)


def _window(now: datetime, seconds: float) -> tuple[datetime, datetime]:
    starts_at = now + timedelta(seconds=get_settings().reveal_seconds)
    return starts_at, starts_at + timedelta(seconds=seconds)


def _open_next(room: Room, bracket: Bracket, now: datetime) -> list[Event]:
    playable = bracket.current_matchup()
    matchup = _row(room, playable.round, playable.index)
    matchup.status = MatchupStatus.VOTING
    matchup.starts_at, matchup.ends_at = _window(now, room.vote_seconds)
    matchup.opened_at = matchup.starts_at
    return [
        (
            "matchup_opened",
            room.version,
            {
                "matchup_id": matchup.id,
                "round": matchup.round,
                "starts_at": matchup.starts_at.isoformat(),
                "ends_at": matchup.ends_at.isoformat(),
            },
        )
    ]


def start_tournament(session: Session, code: str, token: str | None) -> tuple[Room, list[Event]]:
    room = rooms.load_room(session, code, lock=True)
    rooms.require_host(room, rooms.authenticate(session, room, token))
    if room.status is not RoomStatus.LOBBY:
        raise Conflict("The tournament has already started.")
    merged = rooms.lobby_contenders(room)
    if len(merged) < MIN_CONTENDERS:
        raise Conflict(f"At least {MIN_CONTENDERS} different options are needed to start.")

    contenders = [
        Contender(id=new_id(), room_id=room.id, key=c.key, display_text=c.display_text, position=i)
        for i, c in enumerate(merged)
    ]
    room.contenders.extend(contenders)
    room.seed = secrets.randbelow(2**31)
    bracket = generate_bracket([c.id for c in contenders], room.seed)
    for matchups in bracket.rounds:
        for m in matchups:
            room.matchups.append(
                Matchup(
                    room_id=room.id,
                    round=m.round,
                    index=m.index,
                    contender_a_id=m.a,
                    contender_b_id=m.b,
                    winner_id=m.winner,
                    is_bye=m.is_bye,
                    status=MatchupStatus.DECIDED if m.is_bye else MatchupStatus.PENDING,
                    outcome="bye" if m.is_bye else None,
                )
            )
    room.status = RoomStatus.IN_PROGRESS
    room.version += 1
    events: list[Event] = [("tournament_started", room.version, {})]
    events += _open_next(room, bracket, utcnow())
    session.commit()
    return room, events


def cast_vote(
    session: Session,
    code: str,
    token: str | None,
    matchup_id: str,
    contender_id: str,
    connected_ids: Callable[[str], set[str]],
) -> tuple[Room, list[Event]]:
    room = rooms.load_room(session, code, lock=True)
    participant = rooms.authenticate(session, room, token)
    _require_running(room)
    matchup = _find_open(room, matchup_id)
    now = utcnow()
    if now < matchup.starts_at:
        raise Conflict("Voting has not started yet.")
    if now >= matchup.ends_at:
        raise Conflict("Voting has closed for this matchup.")
    if participant.joined_at > matchup.opened_at:
        raise Forbidden("You joined after this matchup opened. You can vote in the next one.")
    if contender_id not in (matchup.contender_a_id, matchup.contender_b_id):
        raise Invalid("That option is not in this matchup.")

    current_phase = phase(matchup)
    existing = next(
        (
            v
            for v in matchup.votes
            if v.participant_id == participant.id and v.phase == current_phase
        ),
        None,
    )
    if existing is not None:
        existing.contender_id = contender_id
    else:
        matchup.votes.append(
            Vote(participant_id=participant.id, contender_id=contender_id, phase=current_phase)
        )
    room.version += 1
    voters = set(phase_votes(matchup))
    events: list[Event] = [
        ("vote_cast", room.version, {"matchup_id": matchup.id, "voted_count": len(voters)})
    ]
    events += close_if_everyone_voted(room, matchup, connected_ids(room.id), now)
    session.commit()
    return room, events


def close_if_everyone_voted(
    room: Room, matchup: Matchup, connected_ids: set[str], now: datetime
) -> list[Event]:
    """Close the phase early once every connected eligible participant has voted (SPEC §7)."""
    if now < matchup.starts_at:
        return []
    waiting_on = {p.id for p in eligible_participants(room, matchup) if p.id in connected_ids}
    if not waiting_on or not waiting_on <= set(phase_votes(matchup)):
        return []
    return close_phase(room, matchup, now)


def close_matchup(
    session: Session, code: str, token: str | None, matchup_id: str
) -> tuple[Room, list[Event]]:
    """Host force-close of the open phase."""
    room = rooms.load_room(session, code, lock=True)
    rooms.require_host(room, rooms.authenticate(session, room, token))
    _require_running(room)
    matchup = _find_open(room, matchup_id)
    events = close_phase(room, matchup, utcnow())
    session.commit()
    return room, events


def close_phase(room: Room, matchup: Matchup, now: datetime) -> list[Event]:
    """Tally the open phase and apply the result: revote, or decide and advance the bracket."""
    a, b = matchup.contender_a_id, matchup.contender_b_id
    resolution = resolve_matchup(
        a, b, phase_votes(matchup), is_revote=phase(matchup) == 1, rng=coin
    )
    matchup.votes_a, matchup.votes_b = resolution.votes[a], resolution.votes[b]
    tally = {a: matchup.votes_a, b: matchup.votes_b}
    room.version += 1

    if resolution.outcome is Outcome.REVOTE:
        matchup.status = MatchupStatus.REVOTE
        matchup.starts_at, matchup.ends_at = _window(now, get_settings().revote_seconds)
        return [
            (
                "revote_started",
                room.version,
                {
                    "matchup_id": matchup.id,
                    "votes": tally,
                    "starts_at": matchup.starts_at.isoformat(),
                    "ends_at": matchup.ends_at.isoformat(),
                },
            )
        ]

    bracket = _engine_bracket(room)
    bracket.record_winner(matchup.round, matchup.index, resolution.winner)
    matchup.status = MatchupStatus.DECIDED
    matchup.winner_id = resolution.winner
    matchup.outcome = "coin_flip" if resolution.outcome is Outcome.COIN_FLIP else "votes"
    matchup.starts_at = matchup.ends_at = None
    for engine_round in bracket.rounds:
        for m in engine_round:
            row = _row(room, m.round, m.index)
            row.contender_a_id, row.contender_b_id = m.a, m.b

    events: list[Event] = [
        (
            "matchup_decided",
            room.version,
            {
                "matchup_id": matchup.id,
                "winner_id": matchup.winner_id,
                "outcome": matchup.outcome,
                "votes": tally,
            },
        )
    ]
    if bracket.champion is not None:
        room.status = RoomStatus.FINISHED
        room.finished_at = now
        events.append(("champion_crowned", room.version, {"contender_id": bracket.champion}))
        return events

    opened = _open_next(room, bracket, now)
    next_round = opened[0][2]["round"]
    if next_round > matchup.round:
        events.append(("round_started", room.version, {"round": next_round}))
    return events + opened
