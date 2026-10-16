"""Request and response models for the rooms API."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.models import RoomStatus

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Nickname = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
MaxParticipants = Annotated[int, Field(ge=2, le=50)]
MaxSubmissions = Annotated[int, Field(ge=1, le=10)]
VoteSeconds = Annotated[int, Field(ge=10, le=120)]


class RoomSettings(BaseModel):
    max_participants: MaxParticipants = 20
    max_submissions: MaxSubmissions = 3
    vote_seconds: VoteSeconds = 30


class CreateRoomRequest(BaseModel):
    title: Title
    description: Description = ""
    nickname: Nickname
    settings: RoomSettings = RoomSettings()


class UpdateRoomRequest(BaseModel):
    title: Title | None = None
    description: Description | None = None
    max_participants: MaxParticipants | None = None
    max_submissions: MaxSubmissions | None = None
    vote_seconds: VoteSeconds | None = None


class JoinRoomRequest(BaseModel):
    nickname: Nickname


class SessionResponse(BaseModel):
    """Identity handed to a client: keep `token` (and the host's recovery token) secret."""

    code: str
    participant_id: str
    nickname: str
    token: str


class CreateRoomResponse(SessionResponse):
    host_recovery_token: str


class RecoverHostRequest(BaseModel):
    recovery_token: str


class TransferHostRequest(BaseModel):
    participant_id: str


class SubmitOptionRequest(BaseModel):
    text: str


class MergeContendersRequest(BaseModel):
    source_key: str
    target_key: str


class RemoveContenderRequest(BaseModel):
    key: str


class SubmissionOut(BaseModel):
    id: str
    text: str


class AttributedSubmission(BaseModel):
    id: str
    text: str
    participant_id: str


class ContenderOut(BaseModel):
    key: str
    display_text: str
    submissions: list[AttributedSubmission]


class ParticipantOut(BaseModel):
    id: str
    nickname: str
    avatar: int
    is_host: bool
    connected: bool


class RoomSnapshot(BaseModel):
    code: str
    title: str
    description: str
    status: RoomStatus
    version: int
    settings: RoomSettings
    host_participant_id: str | None
    me: ParticipantOut
    participants: list[ParticipantOut]
    option_count: int
    my_submissions: list[SubmissionOut]
    # Only the host sees every option during the lobby; null for everyone else.
    contenders: list[ContenderOut] | None
