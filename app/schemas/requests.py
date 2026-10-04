from typing import Literal

from app.schemas.common import CamelModel
from app.schemas.users import PublicUser

RequestKind = Literal["listen", "moderate"]
ApprovalState = Literal["pending", "accepted", "rejected"]
NotificationKind = Literal["request_sent", "request_received", "request_update"]


class ServiceRequestOut(CamelModel):
    id: str
    kind: RequestKind
    requester_id: str
    provider_id: str
    participant_ids: list[str]
    approvals: dict[str, ApprovalState]
    status: ApprovalState
    room_id: str
    created_at: int


class SentRequestsResult(CamelModel):
    provider_names: list[str]
    participant_names: list[str]


class ListenBody(CamelModel):
    provider_ids: list[str]


class ModerateBody(CamelModel):
    provider_id: str
    participant_ids: list[str]


class RespondBody(CamelModel):
    accept: bool


class NotificationItem(CamelModel):
    id: str
    user_id: str
    kind: NotificationKind
    request_id: str
    text: str
    read: bool
    created_at: int
    request: ServiceRequestOut
    requester: PublicUser
    provider: PublicUser
    participants: list[PublicUser]
    actionable: bool


class UnreadCount(CamelModel):
    count: int
