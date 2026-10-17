"""HTTP endpoints for running the tournament."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Room
from app.realtime.hub import hub
from app.rooms import schemas
from app.rooms.routes import Token
from app.tournament import service, timers
from app.tournament.service import Event

router = APIRouter(prefix="/rooms", tags=["tournament"])

DbSession = Annotated[Session, Depends(get_session)]


def publish_events(background: BackgroundTasks, room: Room, events: list[Event]) -> None:
    """Broadcast events in order once the response has been sent, then re-arm the deadline."""
    for type, version, data in events:
        background.add_task(hub.publish, room.id, type, version, data)
    background.add_task(timers.sync_deadline, room.id)


@router.post("/{code}/start", operation_id="startTournament")
def start_tournament(
    code: str, token: Token, db: DbSession, background: BackgroundTasks
) -> schemas.StartTournamentResponse:
    room, events = service.start_tournament(db, code, token)
    publish_events(background, room, events)
    return schemas.StartTournamentResponse(status=room.status)


@router.post("/{code}/votes", operation_id="castVote")
def cast_vote(
    code: str,
    body: schemas.VoteRequest,
    token: Token,
    db: DbSession,
    background: BackgroundTasks,
) -> schemas.VoteResponse:
    room, events = service.cast_vote(
        db, code, token, body.matchup_id, body.contender_id, hub.connected_ids
    )
    publish_events(background, room, events)
    return schemas.VoteResponse(contender_id=body.contender_id)


@router.post("/{code}/matchups/{matchup_id}/close", operation_id="closeMatchup")
def close_matchup(
    code: str, matchup_id: str, token: Token, db: DbSession, background: BackgroundTasks
) -> schemas.CloseMatchupResponse:
    room, events = service.close_matchup(db, code, token, matchup_id)
    publish_events(background, room, events)
    status = next(m.status for m in room.matchups if m.id == matchup_id)
    return schemas.CloseMatchupResponse(status=status)
