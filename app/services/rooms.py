"""Chatrooms: access, permissions (spec §7.3–7.6), messages, closures, mutes, ratings, summary."""

from collections import defaultdict
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.utils import from_ms, new_id, now, to_ms
from app.db.models import (
    Message,
    MessageStar,
    Room,
    RoomClosure,
    RoomMember,
    RoomMute,
    RoomRating,
    User,
)
from app.schemas.rooms import (
    Closure,
    MessageOut,
    MessageWithSender,
    Rating,
    RoomDetail,
    RoomListItem,
    RoomOut,
    RoomSummary,
    SummaryComment,
    SummaryNote,
)
from app.services.users import load_users, public_user

ROOM_NOT_FOUND = ("not_found", "Chatroom not found.")


# ---------- loading / assembling ----------

def load_room_for_member(db: Session, room_id: str, caller: User, lock: bool = False) -> Room:
    """Missing room and non-member both look like 404 (spec §6.4 access rule)."""
    stmt = select(Room).where(Room.id == room_id)
    if lock:
        stmt = stmt.with_for_update()
    room = db.scalar(stmt)
    if room is None or db.get(RoomMember, (room.id, caller.id)) is None:
        raise ApiError(*ROOM_NOT_FOUND)
    return room


def build_rooms(db: Session, rooms) -> dict[str, RoomOut]:
    rooms = list(rooms)
    ids = [r.id for r in rooms]
    if not ids:
        return {}
    members: dict[str, list[str]] = defaultdict(list)
    for rm in db.scalars(
        select(RoomMember).where(RoomMember.room_id.in_(ids))
        .order_by(RoomMember.room_id, RoomMember.position)
    ):
        members[rm.room_id].append(rm.user_id)
    mutes: dict[str, list[str]] = defaultdict(list)
    for mu in db.scalars(select(RoomMute).where(RoomMute.room_id.in_(ids)).order_by(RoomMute.user_id)):
        mutes[mu.room_id].append(mu.user_id)
    closures: dict[str, dict[str, Closure]] = defaultdict(dict)
    for c in db.scalars(select(RoomClosure).where(RoomClosure.room_id.in_(ids)).order_by(RoomClosure.at)):
        closures[c.room_id][c.user_id] = Closure(user_id=c.user_id, text=c.text, at=to_ms(c.at))
    ratings: dict[str, list[Rating]] = defaultdict(list)
    for rt in db.scalars(select(RoomRating).where(RoomRating.room_id.in_(ids)).order_by(RoomRating.at)):
        ratings[rt.room_id].append(
            Rating(by_id=rt.by_id, stars=rt.stars, feedback=rt.feedback, at=to_ms(rt.at))
        )
    return {
        r.id: RoomOut(
            id=r.id, kind=r.kind, request_id=r.request_id, requester_id=r.requester_id,
            provider_id=r.provider_id, member_ids=members[r.id], status=r.status,
            muted_ids=mutes[r.id], closures=closures[r.id], ratings=ratings[r.id],
            created_at=to_ms(r.created_at), closed_at=to_ms(r.closed_at),
        )
        for r in rooms
    }


def build_room(db: Session, room: Room) -> RoomOut:
    return build_rooms(db, [room])[room.id]


def build_messages(db: Session, msgs) -> list[MessageOut]:
    msgs = list(msgs)
    stars: dict[str, list[str]] = defaultdict(list)
    if msgs:
        for s in db.scalars(
            select(MessageStar).where(MessageStar.message_id.in_([x.id for x in msgs]))
            .order_by(MessageStar.user_id)
        ):
            stars[s.message_id].append(s.user_id)
    return [
        MessageOut(
            id=x.id, room_id=x.room_id, sender_id=x.sender_id, text=x.text,
            starred_by=stars[x.id], created_at=to_ms(x.created_at),
        )
        for x in msgs
    ]


def _with_senders(db: Session, messages: list[MessageOut]) -> list[MessageWithSender]:
    users = load_users(db, [x.sender_id for x in messages])
    return [
        MessageWithSender(**x.model_dump(), sender=public_user(users[x.sender_id]))
        for x in messages
    ]


# ---------- permissions ----------

def room_role(room: RoomOut | Room, user_id: str) -> str:
    if user_id != room.provider_id:
        return "member"
    return "listener" if room.kind == "listen" else "moderator"


def send_blocked_reason(room: RoomOut, user_id: str) -> str | None:
    if room.status == "pending":
        return "Waiting for everyone to approve."
    if room.status == "rejected":
        return "This request was declined."
    if room.status == "closed":
        return "This chat is closed."
    if user_id in room.closures:
        return "You have submitted and left this chat."
    if user_id in room.muted_ids:
        return "You have been muted by the moderator."
    return None


# ---------- endpoints ----------

def list_rooms(db: Session, caller: User) -> list[RoomListItem]:
    rooms = db.scalars(
        select(Room).join(RoomMember, RoomMember.room_id == Room.id)
        .where(RoomMember.user_id == caller.id)
    ).all()
    built = build_rooms(db, rooms)
    last_msgs = db.scalars(
        select(Message)
        .where(Message.room_id.in_(list(built)))
        .ext(distinct_on(Message.room_id))
        .order_by(Message.room_id, Message.created_at.desc(), Message.id.desc())
    ).all() if built else []
    last_by_room = {x.room_id: x for x in build_messages(db, last_msgs)}
    users = load_users(db, {uid for r in built.values() for uid in r.member_ids})

    items = []
    for room in built.values():
        last = last_by_room.get(room.id)
        items.append(RoomListItem(
            room=room,
            provider=public_user(users[room.provider_id]),
            others=[public_user(users[u]) for u in room.member_ids if u != caller.id],
            last_message=last,
            last_activity=max(room.created_at, last.created_at if last else 0, room.closed_at or 0),
        ))
    items.sort(key=lambda i: i.last_activity, reverse=True)
    return items


def room_detail(db: Session, caller: User, room_id: str) -> RoomDetail:
    room = build_room(db, load_room_for_member(db, room_id, caller))
    users = load_users(db, room.member_ids)
    role = room_role(room, caller.id)
    reason = send_blocked_reason(room, caller.id)
    return RoomDetail(
        room=room,
        members=[public_user(users[u]) for u in room.member_ids],
        my_role=role,
        can_send=reason is None,
        send_blocked_reason=reason,
        has_submitted=caller.id in room.closures,
        needs_rating=(
            room.status == "closed" and role == "member"
            and all(r.by_id != caller.id for r in room.ratings)
        ),
    )


def list_messages(
    db: Session, caller: User, room_id: str, after: int | None
) -> list[MessageWithSender]:
    room = load_room_for_member(db, room_id, caller)
    stmt = select(Message).where(Message.room_id == room.id)
    if after is not None:
        stmt = stmt.where(Message.created_at > from_ms(after))
    msgs = db.scalars(stmt.order_by(Message.created_at, Message.id)).all()
    return _with_senders(db, build_messages(db, msgs))


def send_message(db: Session, caller: User, room_id: str, text: str) -> MessageOut:
    room = load_room_for_member(db, room_id, caller)
    text = text.strip()
    if not text:
        raise ApiError("validation", "Message is empty.")
    reason = send_blocked_reason(build_room(db, room), caller.id)
    if reason is not None:
        raise ApiError("forbidden", reason)
    msg = Message(id=new_id("msg"), room_id=room.id, sender_id=caller.id, text=text, created_at=now())
    db.add(msg)
    db.flush()
    return build_messages(db, [msg])[0]


def toggle_star(db: Session, caller: User, message_id: str) -> MessageOut:
    msg = db.get(Message, message_id)
    if msg is None:
        raise ApiError("not_found", "Message not found.")
    load_room_for_member(db, msg.room_id, caller)
    star = db.get(MessageStar, (msg.id, caller.id))
    if star is None:
        db.add(MessageStar(message_id=msg.id, user_id=caller.id))
    else:
        db.delete(star)
    db.flush()
    return build_messages(db, [msg])[0]


def submit_closure(db: Session, caller: User, room_id: str, text: str) -> RoomOut:
    room = load_room_for_member(db, room_id, caller, lock=True)
    if room.status != "active":
        raise ApiError("forbidden", "This chat is not open.")
    if db.get(RoomClosure, (room.id, caller.id)) is not None:
        raise ApiError("forbidden", "You have already submitted.")
    at = now()
    db.add(RoomClosure(room_id=room.id, user_id=caller.id, text=text.strip(), at=at))
    db.flush()

    # Closing rule (§7.5): the moderator's verdict closes the room at once; a listen
    # room closes when every member has submitted. Member closures never close a
    # moderated room.
    built = build_room(db, room)
    if room_role(room, caller.id) == "moderator" or (
        room.kind == "listen" and all(u in built.closures for u in built.member_ids)
    ):
        room.status = "closed"
        room.closed_at = at
        db.flush()
    return build_room(db, room)


def set_muted(db: Session, caller: User, room_id: str, user_id: str, muted: bool) -> RoomOut:
    room = load_room_for_member(db, room_id, caller, lock=True)
    if room_role(room, caller.id) != "moderator":
        raise ApiError("forbidden", "Only the moderator can mute.")
    if user_id == caller.id or db.get(RoomMember, (room.id, user_id)) is None:
        raise ApiError("validation", "Cannot mute this member.")
    existing = db.get(RoomMute, (room.id, user_id))
    if muted and existing is None:
        db.add(RoomMute(room_id=room.id, user_id=user_id))
    elif not muted and existing is not None:
        db.execute(delete(RoomMute).where(RoomMute.room_id == room.id, RoomMute.user_id == user_id))
    db.flush()
    return build_room(db, room)


def rate(db: Session, caller: User, room_id: str, stars: Any, feedback: str) -> RoomOut:
    # Checked before loading the room (spec §6.4 #21).
    if not isinstance(stars, int) or isinstance(stars, bool) or not 1 <= stars <= 5:
        raise ApiError("validation", "Choose between 1 and 5 stars.")
    room = load_room_for_member(db, room_id, caller, lock=True)
    if room.status != "closed":
        raise ApiError("forbidden", "You can rate once the chat is closed.")
    if room_role(room, caller.id) != "member":
        raise ApiError("forbidden", "Providers do not rate themselves.")
    if db.get(RoomRating, (room.id, caller.id)) is not None:
        raise ApiError("forbidden", "You have already rated.")
    db.add(RoomRating(room_id=room.id, by_id=caller.id, stars=stars, feedback=feedback.strip(), at=now()))
    db.flush()
    return build_room(db, room)


def summary(db: Session, caller: User, room_id: str) -> RoomSummary:
    room = build_room(db, load_room_for_member(db, room_id, caller))
    users = load_users(db, room.member_ids)
    starred_ids = select(MessageStar.message_id).distinct()
    msgs = db.scalars(
        select(Message)
        .where(Message.room_id == room.id, Message.id.in_(starred_ids))
        .order_by(Message.created_at, Message.id)
    ).all()

    comments = sorted(
        (c for uid, c in room.closures.items() if uid != room.provider_id), key=lambda c: c.at
    )
    provider_closure = room.closures.get(room.provider_id)
    note = (
        SummaryNote(user=public_user(users[room.provider_id]), text=provider_closure.text)
        if provider_closure else None
    )
    return RoomSummary(
        room=room,
        provider=public_user(users[room.provider_id]),
        starred=_with_senders(db, build_messages(db, msgs)),
        comments=[
            SummaryComment(user=public_user(users[c.user_id]), text=c.text, at=c.at)
            for c in comments
        ],
        observation=note if room.kind == "listen" else None,
        verdict=note if room.kind == "moderate" else None,
    )
