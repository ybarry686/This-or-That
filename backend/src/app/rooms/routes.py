"""HTTP endpoints for rooms, identity and the lobby."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Room
from app.realtime.hub import hub
from app.rooms import schemas, service

router = APIRouter(prefix="/rooms", tags=["rooms"])

DbSession = Annotated[Session, Depends(get_session)]
_bearer = HTTPBearer(auto_error=False)


def _token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str | None:
    return credentials.credentials if credentials else None


Token = Annotated[str | None, Depends(_token)]


def _session_response(issued: service.IssuedSession) -> dict:
    return {
        "code": issued.room.code,
        "participant_id": issued.participant.id,
        "nickname": issued.participant.nickname,
        "token": issued.token,
    }


@router.post("", status_code=status.HTTP_201_CREATED, operation_id="createRoom")
def create_room(body: schemas.CreateRoomRequest, db: DbSession) -> schemas.CreateRoomResponse:
    issued, recovery_token = service.create_room(db, body)
    return schemas.CreateRoomResponse(
        **_session_response(issued), host_recovery_token=recovery_token
    )


def _publish(background: BackgroundTasks, room: Room, type: str, data: dict | None = None) -> None:
    """Broadcast an event for a committed change once the response has been sent."""
    background.add_task(hub.publish, room.id, type, room.version, data)


def _publish_options(background: BackgroundTasks, room: Room) -> None:
    # Only the count is broadcast: option texts stay hidden from guests during the lobby.
    _publish(background, room, "submissions_changed", {"option_count": service.option_count(room)})


@router.post("/{code}/join", status_code=status.HTTP_201_CREATED, operation_id="joinRoom")
def join_room(
    code: str, body: schemas.JoinRoomRequest, db: DbSession, background: BackgroundTasks
) -> schemas.SessionResponse:
    issued = service.join_room(db, code, body.nickname)
    _publish(
        background, issued.room, "participant_joined", {"participant_id": issued.participant.id}
    )
    return schemas.SessionResponse(**_session_response(issued))


@router.get("/{code}", operation_id="getRoom")
def get_room(code: str, token: Token, db: DbSession) -> schemas.RoomSnapshot:
    room = service.load_room(db, code)
    me = service.authenticate(db, room, token)
    return service.build_snapshot(room, me, hub.connected_ids(room.id))


@router.patch("/{code}", operation_id="updateRoom")
def update_room(
    code: str,
    body: schemas.UpdateRoomRequest,
    token: Token,
    db: DbSession,
    background: BackgroundTasks,
) -> schemas.RoomSettings:
    room = service.update_room(db, code, token, body)
    _publish(background, room, "settings_changed")
    return schemas.RoomSettings(
        max_participants=room.max_participants,
        max_submissions=room.max_submissions,
        vote_seconds=room.vote_seconds,
    )


@router.post(
    "/{code}/submissions", status_code=status.HTTP_201_CREATED, operation_id="submitOption"
)
def submit_option(
    code: str,
    body: schemas.SubmitOptionRequest,
    token: Token,
    db: DbSession,
    background: BackgroundTasks,
) -> schemas.SubmissionOut:
    submission = service.submit_option(db, code, token, body.text)
    _publish_options(background, submission.room)
    return schemas.SubmissionOut(id=submission.id, text=submission.text)


@router.delete(
    "/{code}/submissions/{submission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteSubmission",
)
def delete_submission(
    code: str, submission_id: str, token: Token, db: DbSession, background: BackgroundTasks
) -> Response:
    room = service.delete_submission(db, code, token, submission_id)
    _publish_options(background, room)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{code}/contenders/merge", operation_id="mergeContenders")
def merge_contenders(
    code: str,
    body: schemas.MergeContendersRequest,
    token: Token,
    db: DbSession,
    background: BackgroundTasks,
) -> None:
    room = service.merge_contenders(db, code, token, body.source_key, body.target_key)
    _publish_options(background, room)


@router.post("/{code}/contenders/remove", operation_id="removeContender")
def remove_contender(
    code: str,
    body: schemas.RemoveContenderRequest,
    token: Token,
    db: DbSession,
    background: BackgroundTasks,
) -> None:
    room = service.remove_contender(db, code, token, body.key)
    _publish_options(background, room)


def _publish_host(background: BackgroundTasks, room: Room) -> None:
    _publish(background, room, "host_changed", {"host_participant_id": room.host_participant_id})


@router.post("/{code}/host/transfer", operation_id="transferHost")
def transfer_host(
    code: str,
    body: schemas.TransferHostRequest,
    token: Token,
    db: DbSession,
    background: BackgroundTasks,
) -> None:
    room = service.transfer_host(db, code, token, body.participant_id)
    _publish_host(background, room)


@router.post("/{code}/host/recover", operation_id="recoverHost")
def recover_host(
    code: str, body: schemas.RecoverHostRequest, db: DbSession, background: BackgroundTasks
) -> schemas.SessionResponse:
    issued = service.recover_host(db, code, body.recovery_token)
    _publish_host(background, issued.room)
    return schemas.SessionResponse(**_session_response(issued))


@router.get("/{code}/results", operation_id="getResults")
def get_results(code: str, db: DbSession) -> schemas.ResultsOut:
    return service.get_results(db, code)


@router.post("/{code}/rematch", status_code=status.HTTP_201_CREATED, operation_id="createRematch")
def create_rematch(
    code: str, token: Token, db: DbSession, background: BackgroundTasks
) -> schemas.CreateRoomResponse:
    room, issued, recovery_token = service.create_rematch(db, code, token)
    _publish(background, room, "rematch_created", {"code": issued.room.code})
    return schemas.CreateRoomResponse(
        **_session_response(issued), host_recovery_token=recovery_token
    )
