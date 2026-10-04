from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.utils import new_id, now, to_ms
from app.db.models import Notification, ServiceRequest, User
from app.schemas.requests import NotificationItem
from app.services.requests_common import serialize_requests
from app.services.users import load_users, public_user


def notify(
    db: Session, user_id: str, kind: str, request_id: str, text: str, at: datetime | None = None
) -> None:
    """Spec §7.7: request updates arrive pre-read for users who turned them off."""
    read = False
    if kind == "request_update":
        recipient = db.get(User, user_id)
        read = recipient is not None and not recipient.notify_requests
    db.add(Notification(
        id=new_id("ntf"), user_id=user_id, kind=kind, request_id=request_id, text=text,
        read=read, created_at=at or now(),
    ))


def list_notifications(db: Session, caller: User) -> list[NotificationItem]:
    notes = db.scalars(
        select(Notification)
        .where(Notification.user_id == caller.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    ).all()
    reqs = db.scalars(
        select(ServiceRequest).where(ServiceRequest.id.in_({n.request_id for n in notes}))
    ).all()
    requests = serialize_requests(db, reqs)
    user_ids = {caller.id}
    for r in requests.values():
        user_ids.update([r.requester_id, r.provider_id, *r.participant_ids])
    users = {uid: public_user(u) for uid, u in load_users(db, user_ids).items()}

    items = []
    for n in notes:
        req = requests.get(n.request_id)
        if req is None:  # request no longer exists
            continue
        items.append(NotificationItem(
            id=n.id, user_id=n.user_id, kind=n.kind, request_id=n.request_id, text=n.text,
            read=n.read, created_at=to_ms(n.created_at), request=req,
            requester=users[req.requester_id], provider=users[req.provider_id],
            participants=[users[p] for p in req.participant_ids],
            actionable=(
                n.kind == "request_received"
                and req.status == "pending"
                and req.approvals.get(caller.id) == "pending"
            ),
        ))
    return items


def unread_count(db: Session, caller: User) -> int:
    return db.scalar(
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == caller.id, Notification.read.is_(False))
    )


def mark_all_read(db: Session, caller: User) -> None:
    db.execute(
        update(Notification)
        .where(Notification.user_id == caller.id, Notification.read.is_(False))
        .values(read=True)
    )
