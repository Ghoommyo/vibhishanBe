from typing import Any, Literal

from app.schemas.common import CamelModel
from app.schemas.requests import RequestKind
from app.schemas.users import PublicUser

RoomStatus = Literal["pending", "active", "closed", "rejected"]
RoomRole = Literal["member", "listener", "moderator"]


class Closure(CamelModel):
    user_id: str
    text: str
    at: int


class Rating(CamelModel):
    by_id: str
    stars: int
    feedback: str
    at: int


class RoomOut(CamelModel):
    id: str
    kind: RequestKind
    request_id: str
    requester_id: str
    provider_id: str
    member_ids: list[str]
    status: RoomStatus
    muted_ids: list[str]
    closures: dict[str, Closure]
    ratings: list[Rating]
    created_at: int
    closed_at: int | None


class MessageOut(CamelModel):
    id: str
    room_id: str
    sender_id: str
    text: str
    starred_by: list[str]
    created_at: int


class MessageWithSender(MessageOut):
    sender: PublicUser


class RoomListItem(CamelModel):
    room: RoomOut
    provider: PublicUser
    others: list[PublicUser]
    last_message: MessageOut | None
    last_activity: int


class RoomDetail(CamelModel):
    room: RoomOut
    members: list[PublicUser]
    my_role: RoomRole
    can_send: bool
    send_blocked_reason: str | None
    has_submitted: bool
    needs_rating: bool


class SummaryComment(CamelModel):
    user: PublicUser
    text: str
    at: int


class SummaryNote(CamelModel):
    user: PublicUser
    text: str


class RoomSummary(CamelModel):
    room: RoomOut
    provider: PublicUser
    starred: list[MessageWithSender]
    comments: list[SummaryComment]
    observation: SummaryNote | None
    verdict: SummaryNote | None


class SendMessageBody(CamelModel):
    text: str


class ClosureBody(CamelModel):
    text: str = ""


class MuteBody(CamelModel):
    muted: bool


class RateBody(CamelModel):
    # Validated by hand so any bad value yields the spec's message (§6.4 #21).
    stars: Any = None
    feedback: str = ""
