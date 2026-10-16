"""HTTP endpoints for rooms, identity and the lobby."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_session
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


@router.post("/{code}/join", status_code=status.HTTP_201_CREATED, operation_id="joinRoom")
def join_room(code: str, body: schemas.JoinRoomRequest, db: DbSession) -> schemas.SessionResponse:
    return schemas.SessionResponse(**_session_response(service.join_room(db, code, body.nickname)))


@router.get("/{code}", operation_id="getRoom")
def get_room(code: str, token: Token, db: DbSession) -> schemas.RoomSnapshot:
    room = service.load_room(db, code)
    return service.build_snapshot(room, service.authenticate(db, room, token))


@router.patch("/{code}", operation_id="updateRoom")
def update_room(
    code: str, body: schemas.UpdateRoomRequest, token: Token, db: DbSession
) -> schemas.RoomSettings:
    room = service.update_room(db, code, token, body)
    return schemas.RoomSettings(
        max_participants=room.max_participants,
        max_submissions=room.max_submissions,
        vote_seconds=room.vote_seconds,
    )


@router.post(
    "/{code}/submissions", status_code=status.HTTP_201_CREATED, operation_id="submitOption"
)
def submit_option(
    code: str, body: schemas.SubmitOptionRequest, token: Token, db: DbSession
) -> schemas.SubmissionOut:
    submission = service.submit_option(db, code, token, body.text)
    return schemas.SubmissionOut(id=submission.id, text=submission.text)


@router.delete(
    "/{code}/submissions/{submission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteSubmission",
)
def delete_submission(code: str, submission_id: str, token: Token, db: DbSession) -> Response:
    service.delete_submission(db, code, token, submission_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{code}/contenders/merge", operation_id="mergeContenders")
def merge_contenders(
    code: str, body: schemas.MergeContendersRequest, token: Token, db: DbSession
) -> None:
    service.merge_contenders(db, code, token, body.source_key, body.target_key)


@router.post("/{code}/contenders/remove", operation_id="removeContender")
def remove_contender(
    code: str, body: schemas.RemoveContenderRequest, token: Token, db: DbSession
) -> None:
    service.remove_contender(db, code, token, body.key)


@router.post("/{code}/host/transfer", operation_id="transferHost")
def transfer_host(
    code: str, body: schemas.TransferHostRequest, token: Token, db: DbSession
) -> None:
    service.transfer_host(db, code, token, body.participant_id)


@router.post("/{code}/host/recover", operation_id="recoverHost")
def recover_host(
    code: str, body: schemas.RecoverHostRequest, db: DbSession
) -> schemas.SessionResponse:
    return schemas.SessionResponse(
        **_session_response(service.recover_host(db, code, body.recovery_token))
    )
