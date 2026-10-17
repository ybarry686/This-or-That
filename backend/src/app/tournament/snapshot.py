"""The tournament section of a room snapshot, as seen by one participant."""

from app.models import Matchup, MatchupStatus, Participant, Room, RoomStatus
from app.rooms import schemas


def current_matchup(room: Room) -> Matchup | None:
    """The matchup whose vote (or revote) is open or about to open."""
    return next(
        (m for m in room.matchups if m.status in (MatchupStatus.VOTING, MatchupStatus.REVOTE)),
        None,
    )


def phase(matchup: Matchup) -> int:
    return 1 if matchup.status is MatchupStatus.REVOTE else 0


def eligible_participants(room: Room, matchup: Matchup) -> list[Participant]:
    """Participants present when the matchup first opened (SPEC §7)."""
    return [p for p in room.participants if p.joined_at <= matchup.opened_at]


def phase_votes(matchup: Matchup) -> dict[str, str]:
    """participant id -> contender id for the matchup's current phase."""
    current = phase(matchup)
    return {v.participant_id: v.contender_id for v in matchup.votes if v.phase == current}


def _matchup_out(matchup: Matchup) -> schemas.MatchupOut:
    return schemas.MatchupOut(
        id=matchup.id,
        round=matchup.round,
        index=matchup.index,
        contender_a_id=matchup.contender_a_id,
        contender_b_id=matchup.contender_b_id,
        winner_id=matchup.winner_id,
        is_bye=matchup.is_bye,
        status=matchup.status,
        outcome=matchup.outcome,
        votes_a=matchup.votes_a,
        votes_b=matchup.votes_b,
    )


def _current_out(room: Room, me: Participant | None) -> schemas.CurrentMatchup | None:
    matchup = current_matchup(room)
    if matchup is None:
        return None
    eligible = eligible_participants(room, matchup)
    votes = phase_votes(matchup)
    return schemas.CurrentMatchup(
        matchup_id=matchup.id,
        phase="revote" if phase(matchup) else "vote",
        starts_at=matchup.starts_at,
        ends_at=matchup.ends_at,
        eligible_count=len(eligible),
        # Who has voted is public; what they voted stays secret until the matchup closes.
        voted_participant_ids=[p.id for p in eligible if p.id in votes],
        my_vote=votes.get(me.id) if me else None,
        can_vote=me is not None and any(p.id == me.id for p in eligible),
    )


def build_tournament(room: Room, me: Participant | None) -> schemas.TournamentOut | None:
    """The bracket as `me` sees it (None for an anonymous results viewer)."""
    if room.status is RoomStatus.LOBBY or not room.matchups:
        return None

    submitters: dict[str, list[str]] = {}
    for submission in room.submissions:
        ids = submitters.setdefault(submission.key, [])
        if submission.participant_id not in ids:
            ids.append(submission.participant_id)

    round_count = max(m.round for m in room.matchups) + 1
    rounds: list[list[schemas.MatchupOut]] = [[] for _ in range(round_count)]
    for matchup in room.matchups:
        rounds[matchup.round].append(_matchup_out(matchup))

    final = next(m for m in room.matchups if m.round == round_count - 1)
    return schemas.TournamentOut(
        contenders=[
            schemas.TournamentContender(
                id=c.id, display_text=c.display_text, submitter_ids=submitters.get(c.key, [])
            )
            for c in room.contenders
        ],
        rounds=rounds,
        current=_current_out(room, me),
        champion_id=final.winner_id,
    )
