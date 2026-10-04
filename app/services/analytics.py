"""Provider dashboard stats (spec §6.6 #26)."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utils import now, to_ms
from app.db.models import Room, RoomRating, User
from app.schemas.analytics import FeedbackItem, ProviderStats, WeeklyBucket
from app.services.users import load_users, public_user

WEEK = timedelta(days=7)


def provider_stats(db: Session, caller: User, tz_offset: int = 0) -> ProviderStats:
    mine = db.scalars(select(Room).where(Room.provider_id == caller.id)).all()
    closed = [r for r in mine if r.status == "closed"]
    ratings = db.scalars(
        select(RoomRating).join(Room, Room.id == RoomRating.room_id)
        .where(Room.provider_id == caller.id)
        .order_by(RoomRating.at.desc())
    ).all()

    distribution = [0] * 5
    for r in ratings:
        distribution[r.stars - 1] += 1

    current = now()
    weekly = []
    for i in range(8):
        end = current - (7 - i) * WEEK
        start = end - WEEK
        if i == 7:
            label = "Now"
        else:
            # Client-local date of start + 1ms; tzOffset follows JS getTimezoneOffset().
            local = start + timedelta(milliseconds=1) - timedelta(minutes=tz_offset)
            label = f"{local.day}/{local.month}"
        value = sum(1 for r in closed if start < r.closed_at <= end)
        weekly.append(WeeklyBucket(label=label, value=value, start=to_ms(start), end=to_ms(end)))

    with_text = [r for r in ratings if r.feedback.strip()]
    raters = load_users(db, [r.by_id for r in with_text])
    return ProviderStats(
        listening_done=sum(1 for r in closed if r.kind == "listen"),
        moderation_done=sum(1 for r in closed if r.kind == "moderate"),
        active_sessions=sum(1 for r in mine if r.status == "active"),
        average_rating=sum(r.stars for r in ratings) / len(ratings) if ratings else None,
        rating_count=len(ratings),
        rating_distribution=distribution,
        weekly=weekly,
        feedback=[
            FeedbackItem(by=public_user(raters[r.by_id]), stars=r.stars, text=r.feedback, at=to_ms(r.at))
            for r in with_text
        ],
    )
