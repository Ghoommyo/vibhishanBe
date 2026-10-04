"""Session requests: creation (spec §7.1) and the approval state machine (spec §7.2)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.utils import display_name, join_names, new_id, now
from app.db.models import (
    RequestApproval,
    RequestParticipant,
    Room,
    RoomMember,
    ServiceRequest,
    User,
)
from app.schemas.requests import ModerateBody, SentRequestsResult, ServiceRequestOut
from app.services.notifications import notify
from app.services.requests_common import serialize_request
from app.services.users import get_user, load_users


def _create_request_with_room(
    db: Session, kind: str, requester_id: str, provider_id: str, participant_ids: list[str],
    at: datetime,
) -> ServiceRequest:
    req = ServiceRequest(
        id=new_id("req"), kind=kind, requester_id=requester_id, provider_id=provider_id,
        status="pending", room_id=new_id("room"), created_at=at,
    )
    db.add(req)
    db.flush()
    db.add(Room(
        id=req.room_id, kind=kind, request_id=req.id, requester_id=requester_id,
        provider_id=provider_id, status="pending", created_at=at, closed_at=None,
    ))
    db.flush()
    db.add_all(
        RequestParticipant(request_id=req.id, user_id=uid, position=i)
        for i, uid in enumerate(participant_ids)
    )
    # The requester is NOT an approver.
    db.add_all(
        RequestApproval(request_id=req.id, user_id=uid, state="pending")
        for uid in [*participant_ids, provider_id]
    )
    db.add_all(
        RoomMember(room_id=req.room_id, user_id=uid, position=i)
        for i, uid in enumerate([requester_id, *participant_ids, provider_id])
    )
    db.flush()
    return req


def _dedupe(ids: list[str]) -> list[str]:
    return list(dict.fromkeys(ids))


def send_listen(db: Session, caller: User, provider_ids: list[str]) -> SentRequestsResult:
    provider_ids = _dedupe(provider_ids)
    if not provider_ids:
        raise ApiError("validation", "Select at least one listener.")
    # Validate everything before creating anything (all-or-nothing).
    providers = [get_user(db, pid) for pid in provider_ids]
    for p in providers:
        if p.role != "listener":
            raise ApiError("validation", f"{display_name(p)} is not a listener.")

    at = now()
    me = display_name(caller)
    for p in providers:
        req = _create_request_with_room(db, "listen", caller.id, p.id, [], at)
        notify(db, p.id, "request_received", req.id, f"{me} requested a listening session.", at)
        notify(db, caller.id, "request_sent", req.id,
               f"You sent a listening request to {display_name(p)}.", at)
    return SentRequestsResult(
        provider_names=[display_name(p) for p in providers], participant_names=[]
    )


def send_moderate(db: Session, caller: User, body: ModerateBody) -> SentRequestsResult:
    participant_ids = [pid for pid in _dedupe(body.participant_ids) if pid != caller.id]
    if not participant_ids:
        raise ApiError("validation", "Add at least one participant.")
    moderator = get_user(db, body.provider_id)
    if moderator.role != "moderator":
        raise ApiError("validation", f"{display_name(moderator)} is not a moderator.")
    participants = [get_user(db, pid) for pid in participant_ids]
    for p in participants:
        if p.role != "user":
            raise ApiError("validation", f"{display_name(p)} can't be added as a participant.")

    at = now()
    me, mod_name = display_name(caller), display_name(moderator)
    names = [display_name(p) for p in participants]
    req = _create_request_with_room(db, "moderate", caller.id, moderator.id, participant_ids, at)
    for p in participants:
        notify(db, p.id, "request_received", req.id,
               f"{me} invited you to a session moderated by {mod_name}.", at)
    notify(db, caller.id, "request_sent", req.id,
           f"You sent a moderation request to {mod_name} with {join_names(names)}.", at)
    # The moderator is only notified once every participant has accepted (§7.2).
    return SentRequestsResult(provider_names=[mod_name], participant_names=names)


def respond(db: Session, caller: User, request_id: str, accept: bool) -> ServiceRequestOut:
    req = db.scalar(
        select(ServiceRequest).where(ServiceRequest.id == request_id).with_for_update()
    )
    if req is None:
        raise ApiError("not_found", "Request not found.")
    if req.status != "pending":
        raise ApiError("closed", "This request has already been resolved.")

    approvals = {
        a.user_id: a for a in db.scalars(
            select(RequestApproval).where(RequestApproval.request_id == req.id)
        )
    }
    mine = approvals.get(caller.id)
    if mine is None or mine.state != "pending":
        raise ApiError("forbidden", "You have already responded.")

    participant_ids = db.scalars(
        select(RequestParticipant.user_id)
        .where(RequestParticipant.request_id == req.id)
        .order_by(RequestParticipant.position)
    ).all()
    is_provider = caller.id == req.provider_id
    if (
        is_provider and req.kind == "moderate"
        and any(approvals[p].state != "accepted" for p in participant_ids)
    ):
        raise ApiError("forbidden", "Waiting for all participants to accept first.")

    room = db.scalar(select(Room).where(Room.id == req.room_id).with_for_update())
    at = now()
    my_name = display_name(caller)
    others = [uid for uid in [req.requester_id, *participant_ids] if uid != caller.id]
    mine.state = "accepted" if accept else "rejected"

    if not accept:
        req.status = room.status = "rejected"
        for uid in others:
            notify(db, uid, "request_update", req.id, f"{my_name} declined the request.", at)
    elif is_provider:
        req.status = "accepted"
        room.status = "active"
        for uid in others:
            notify(db, uid, "request_update", req.id,
                   f"{my_name} accepted. The chatroom is now open.", at)
    else:
        notify(db, req.requester_id, "request_update", req.id,
               f"{my_name} accepted your invitation.", at)
        if all(approvals[p].state == "accepted" for p in participant_ids):
            users = load_users(db, [req.requester_id, *participant_ids])
            names = join_names([display_name(users[p]) for p in participant_ids])
            notify(db, req.provider_id, "request_received", req.id,
                   f"{display_name(users[req.requester_id])} requested a moderated session "
                   f"with {names}.", at)

    db.flush()
    return serialize_request(db, req)
