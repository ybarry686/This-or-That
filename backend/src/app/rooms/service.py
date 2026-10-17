"""Room, identity and lobby business rules (SPEC §3-§5).

Every mutation locks the room row, applies its change, bumps `room.version`, and commits, so
changes to one room are serialized and clients can detect missed updates.
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.normalize import Submission as EngineSubmission
from app.engine.normalize import merge_submissions, normalize_option, validate_option_text
from app.errors import Conflict, Forbidden, Invalid, NotFound, Unauthorized
from app.models import Participant, Room, RoomStatus, Submission
from app.rooms import schemas
from app.security import hash_token, new_token
from app.tournament.snapshot import build_tournament

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6
AVATAR_COUNT = 16
NICKNAME_MAX = 20
MAX_OPTIONS = 64


@dataclass
class IssuedSession:
    room: Room
    participant: Participant
    token: str


def _normalize_code(code: str) -> str:
    return code.strip().upper()


def _generate_code(session: Session) -> str:
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if session.scalar(select(Room.id).where(Room.code == code)) is None:
            return code


def load_room(session: Session, code: str, *, lock: bool = False) -> Room:
    query = select(Room).where(Room.code == _normalize_code(code))
    if lock:
        query = query.with_for_update()
    room = session.scalar(query)
    if room is None:
        raise NotFound("Room not found.")
    return room


def authenticate(session: Session, room: Room, token: str | None) -> Participant:
    if not token:
        raise Unauthorized("Missing participant token.")
    participant = session.scalar(
        select(Participant).where(
            Participant.room_id == room.id, Participant.token_hash == hash_token(token)
        )
    )
    if participant is None:
        raise Unauthorized("Invalid participant token for this room.")
    return participant


def require_host(room: Room, participant: Participant) -> None:
    if room.host_participant_id != participant.id:
        raise Forbidden("Only the host can do that.")


def _require_lobby(room: Room, action: str) -> None:
    if room.status is not RoomStatus.LOBBY:
        raise Conflict(f"{action} is only possible before the tournament starts.")


def _unique_nickname(room: Room, requested: str) -> str:
    taken = {p.nickname.casefold() for p in room.participants}
    if requested.casefold() not in taken:
        return requested
    n = 2
    while True:
        suffix = f" {n}"
        candidate = requested[: NICKNAME_MAX - len(suffix)].rstrip() + suffix
        if candidate.casefold() not in taken:
            return candidate
        n += 1


def _add_participant(session: Session, room: Room, nickname: str) -> IssuedSession:
    token = new_token()
    participant = Participant(
        room_id=room.id,
        nickname=_unique_nickname(room, nickname),
        avatar=len(room.participants) % AVATAR_COUNT,
        token_hash=hash_token(token),
    )
    room.participants.append(participant)
    session.flush()
    return IssuedSession(room=room, participant=participant, token=token)


def create_room(session: Session, request: schemas.CreateRoomRequest) -> tuple[IssuedSession, str]:
    room = Room(
        code=_generate_code(session),
        title=request.title,
        description=request.description,
        max_participants=request.settings.max_participants,
        max_submissions=request.settings.max_submissions,
        vote_seconds=request.settings.vote_seconds,
    )
    session.add(room)
    session.flush()

    issued = _add_participant(session, room, request.nickname)
    recovery_token = new_token()
    issued.participant.recovery_hash = hash_token(recovery_token)
    room.host_participant_id = issued.participant.id
    session.commit()
    return issued, recovery_token


def join_room(session: Session, code: str, nickname: str) -> IssuedSession:
    room = load_room(session, code, lock=True)
    if room.status in (RoomStatus.FINISHED, RoomStatus.EXPIRED):
        raise Conflict("This room has already finished.")
    if len(room.participants) >= room.max_participants:
        raise Conflict("This room is full.")

    issued = _add_participant(session, room, nickname)
    room.version += 1
    session.commit()
    return issued


def update_room(
    session: Session, code: str, token: str | None, request: schemas.UpdateRoomRequest
) -> Room:
    room = load_room(session, code, lock=True)
    require_host(room, authenticate(session, room, token))
    _require_lobby(room, "Changing settings")

    changes = request.model_dump(exclude_none=True)
    if changes.get("max_participants", room.max_participants) < len(room.participants):
        raise Conflict("The participant limit cannot be lower than the number of participants.")
    for field, value in changes.items():
        setattr(room, field, value)
    room.version += 1
    session.commit()
    return room


def _effective_key(room: Room, text: str) -> str:
    """Normalized key, following any host merge that already absorbed the same text."""
    normalized = normalize_option(text)
    for submission in room.submissions:
        if normalize_option(submission.text) == normalized:
            return submission.key
    return normalized


def submit_option(session: Session, code: str, token: str | None, text: str) -> Submission:
    room = load_room(session, code, lock=True)
    participant = authenticate(session, room, token)
    _require_lobby(room, "Submitting options")
    try:
        display = validate_option_text(text)
    except ValueError as error:
        raise Invalid(str(error)) from None

    mine = [s for s in room.submissions if s.participant_id == participant.id]
    if len(mine) >= room.max_submissions:
        raise Conflict(f"You can submit at most {room.max_submissions} options.")
    key = _effective_key(room, display)
    if key not in {s.key for s in room.submissions} and option_count(room) >= MAX_OPTIONS:
        raise Conflict(f"This room already has the maximum of {MAX_OPTIONS} options.")

    submission = Submission(participant_id=participant.id, text=display, key=key)
    room.submissions.append(submission)
    room.version += 1
    session.commit()
    return submission


def delete_submission(session: Session, code: str, token: str | None, submission_id: str) -> Room:
    room = load_room(session, code, lock=True)
    participant = authenticate(session, room, token)
    _require_lobby(room, "Removing options")
    submission = next(
        (
            s
            for s in room.submissions
            if s.id == submission_id and s.participant_id == participant.id
        ),
        None,
    )
    if submission is None:
        raise NotFound("Submission not found.")

    room.submissions.remove(submission)
    room.version += 1
    session.commit()
    return room


def _submissions_with_key(room: Room, key: str) -> list[Submission]:
    matches = [s for s in room.submissions if s.key == key]
    if not matches:
        raise NotFound(f"No option with key {key!r}.")
    return matches


def merge_contenders(
    session: Session, code: str, token: str | None, source_key: str, target_key: str
) -> Room:
    room = load_room(session, code, lock=True)
    require_host(room, authenticate(session, room, token))
    _require_lobby(room, "Merging options")
    if source_key == target_key:
        raise Invalid("Cannot merge an option into itself.")
    _submissions_with_key(room, target_key)

    for submission in _submissions_with_key(room, source_key):
        submission.key = target_key
    room.version += 1
    session.commit()
    return room


def remove_contender(session: Session, code: str, token: str | None, key: str) -> Room:
    room = load_room(session, code, lock=True)
    require_host(room, authenticate(session, room, token))
    _require_lobby(room, "Removing options")

    for submission in _submissions_with_key(room, key):
        room.submissions.remove(submission)
    room.version += 1
    session.commit()
    return room


def transfer_host(session: Session, code: str, token: str | None, participant_id: str) -> Room:
    room = load_room(session, code, lock=True)
    require_host(room, authenticate(session, room, token))
    if not any(p.id == participant_id for p in room.participants):
        raise NotFound("Participant not found in this room.")

    room.host_participant_id = participant_id
    room.version += 1
    session.commit()
    return room


def recover_host(session: Session, code: str, recovery_token: str) -> IssuedSession:
    room = load_room(session, code, lock=True)
    creator = next(
        (p for p in room.participants if p.recovery_hash == hash_token(recovery_token)), None
    )
    if creator is None:
        raise Unauthorized("Invalid host recovery token.")

    token = new_token()
    creator.token_hash = hash_token(token)
    room.host_participant_id = creator.id
    room.version += 1
    session.commit()
    return IssuedSession(room=room, participant=creator, token=token)


def record_presence_change(session: Session, room_id: str) -> Room:
    """Bump the version after someone connects or disconnects (presence is part of the snapshot)."""
    room = session.get(Room, room_id, with_for_update=True)
    if room is None:
        raise NotFound("Room not found.")
    room.version += 1
    session.commit()
    return room


def hand_off_host(
    session: Session, room_id: str, absent_host_id: str, connected_ids: set[str]
) -> Room | None:
    """Give the host role to the longest-present connected participant if the host is still away.

    Returns the room if the host changed, otherwise None.
    """
    room = session.get(Room, room_id, with_for_update=True)
    if (
        room is None
        or room.status is not RoomStatus.LOBBY
        or room.host_participant_id != absent_host_id
        or absent_host_id in connected_ids
    ):
        return None
    successor = next((p for p in room.participants if p.id in connected_ids), None)
    if successor is None:
        return None

    room.host_participant_id = successor.id
    room.version += 1
    session.commit()
    return room


def lobby_contenders(room: Room):
    return merge_submissions(
        [EngineSubmission(s.id, s.participant_id, s.text, key=s.key) for s in room.submissions]
    )


def option_count(room: Room) -> int:
    return len({s.key for s in room.submissions})


def _participant_out(
    room: Room, participant: Participant, connected_ids: set[str]
) -> schemas.ParticipantOut:
    return schemas.ParticipantOut(
        id=participant.id,
        nickname=participant.nickname,
        avatar=participant.avatar,
        is_host=participant.id == room.host_participant_id,
        connected=participant.id in connected_ids,
    )


def build_snapshot(room: Room, me: Participant, connected_ids: set[str]) -> schemas.RoomSnapshot:
    contenders = None
    if room.status is RoomStatus.LOBBY and me.id == room.host_participant_id:
        by_id = {s.id: s for s in room.submissions}
        contenders = [
            schemas.ContenderOut(
                key=c.key,
                display_text=c.display_text,
                submissions=[
                    schemas.AttributedSubmission(
                        id=sid, text=by_id[sid].text, participant_id=by_id[sid].participant_id
                    )
                    for sid in c.submission_ids
                ],
            )
            for c in lobby_contenders(room)
        ]

    return schemas.RoomSnapshot(
        code=room.code,
        title=room.title,
        description=room.description,
        status=room.status,
        version=room.version,
        settings=schemas.RoomSettings(
            max_participants=room.max_participants,
            max_submissions=room.max_submissions,
            vote_seconds=room.vote_seconds,
        ),
        host_participant_id=room.host_participant_id,
        me=_participant_out(room, me, connected_ids),
        participants=[_participant_out(room, p, connected_ids) for p in room.participants],
        option_count=option_count(room),
        my_submissions=[
            schemas.SubmissionOut(id=s.id, text=s.text)
            for s in room.submissions
            if s.participant_id == me.id
        ],
        contenders=contenders,
        tournament=build_tournament(room, me),
        server_time=datetime.now(UTC),
    )
