"""Seed data (spec §9). Run with `python -m app.seed` to reset the DB to the demo state."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.core.utils import now as utc_now
from app.db import models as m

DAY = timedelta(days=1)
SEED_PASSWORD = "password123"

# (id, username, role, name, bio, expertise)
USERS = [
    ("u_alice", "alice", "user", "Alice Sharma", "Product designer who likes long walks.", []),
    ("u_bob", "bob", "user", "Bob Mehta", "Runner, reader, occasional over-thinker.", []),
    ("u_carol", "carol", "user", "Carol Dsouza", "Grad student juggling deadlines.", []),
    ("u_lisa", "lisa", "listener", "Lisa Kapoor", "Patient ear, 5 years of peer support.",
     ["Stress", "Career", "Relationships"]),
    ("u_leo", "leo", "listener", "Leo Fernandes", "Here to listen without judgement.",
     ["Loneliness", "Studies"]),
    ("u_maya", "maya", "moderator", "Maya Iyer", "Certified mediator for group conversations.",
     ["Conflict resolution", "Family"]),
    ("u_max", "max", "moderator", "Max Rao", "Keeps discussions fair and on track.",
     ["Roommates", "Workplace"]),
]


@dataclass
class SeedSession:
    kind: str
    requester: str
    provider: str
    days_ago: float
    status: str  # room status: closed | active | pending
    participants: list[str] = field(default_factory=list)
    # (sender, text, starred)
    lines: list[tuple[str, str, bool]] = field(default_factory=list)
    closures: list[tuple[str, str]] = field(default_factory=list)
    ratings: list[tuple[str, int, str]] = field(default_factory=list)


SESSIONS = [
    SeedSession(
        "listen", "u_alice", "u_lisa", 50, "closed",
        lines=[
            ("u_alice", "Work has been overwhelming lately.", False),
            ("u_lisa", "That sounds exhausting. What feels heaviest right now?", False),
            ("u_alice", "Mostly the feeling that I can never catch up.", True),
            ("u_lisa", "Would it help to list what is actually due this week?", False),
            ("u_alice", "Yes, writing it down makes it smaller.", True),
        ],
        closures=[
            ("u_alice", "Felt lighter after talking it through."),
            ("u_lisa", "Alice benefits from breaking work into weekly lists."),
        ],
        ratings=[("u_alice", 5, "Lisa was calm and really listened.")],
    ),
    SeedSession(
        "listen", "u_bob", "u_lisa", 36, "closed",
        lines=[
            ("u_bob", "Thinking about switching careers.", False),
            ("u_lisa", "What is drawing you to the change?", False),
            ("u_bob", "I want work that feels meaningful.", True),
        ],
        closures=[
            ("u_bob", "Good space to think out loud."),
            ("u_lisa", "Bob is clear on values, unsure on timing."),
        ],
        ratings=[("u_bob", 4, "Helpful questions, felt heard.")],
    ),
    SeedSession(
        "listen", "u_carol", "u_leo", 22, "closed",
        lines=[
            ("u_carol", "Thesis deadline is next month and I feel stuck.", True),
            ("u_leo", "Stuck on writing, or on the research itself?", False),
            ("u_carol", "Writing. I keep rewriting the intro.", True),
        ],
        closures=[
            ("u_carol", "Will draft the rest before polishing the intro."),
            ("u_leo", "Perfectionism on the intro is the blocker."),
        ],
        ratings=[("u_carol", 4, "Leo gave me a practical next step.")],
    ),
    SeedSession(
        "listen", "u_alice", "u_lisa", 9, "closed",
        lines=[
            ("u_alice", "Checking in, the weekly list is working!", True),
            ("u_lisa", "That is great to hear. Anything new on your mind?", False),
        ],
        closures=[("u_alice", "Progress feels real."), ("u_lisa", "Habits are sticking.")],
        ratings=[("u_alice", 5, "Always a good conversation.")],
    ),
    SeedSession(
        "moderate", "u_alice", "u_maya", 29, "closed", participants=["u_bob"],
        lines=[
            ("u_maya", "Welcome both. Alice, would you like to start?", False),
            ("u_alice", "We disagreed about splitting the project credit.", True),
            ("u_bob", "I felt my part was overlooked in the review.", True),
            ("u_maya", "Can you each name one thing the other did well?", False),
            ("u_alice", "Bob handled all the testing, honestly.", True),
        ],
        closures=[
            ("u_alice", "I will credit Bob explicitly next time."),
            ("u_bob", "Glad we talked, feels fair now."),
            ("u_maya", "Both agree to list contributions in shared reviews going forward."),
        ],
        ratings=[("u_alice", 5, "Maya kept it fair."), ("u_bob", 4, "Good structure.")],
    ),
    SeedSession(
        "moderate", "u_carol", "u_max", 15, "closed", participants=["u_bob"],
        lines=[
            ("u_max", "Let us keep this about the shared flat chores.", False),
            ("u_carol", "Dishes pile up for days.", True),
            ("u_bob", "I can take dishes if you take bins.", True),
        ],
        closures=[
            ("u_carol", "Rota agreed."),
            ("u_max", "Weekly rota: Bob dishes, Carol bins, review in a month."),
        ],
        ratings=[("u_carol", 4, "Quick and practical."), ("u_bob", 3, "A bit rushed.")],
    ),
    SeedSession(
        "moderate", "u_bob", "u_maya", 4, "closed", participants=["u_carol"],
        lines=[
            ("u_maya", "Following up on the flat rota.", False),
            ("u_bob", "Mostly working, bins got missed twice.", True),
            ("u_carol", "Fair, I will set a reminder.", True),
        ],
        closures=[("u_bob", "Good follow up."), ("u_maya", "Rota stays, Carol adds reminders.")],
        ratings=[("u_bob", 5, "Maya follows up properly.")],
    ),
    SeedSession(
        "listen", "u_carol", "u_lisa", 1, "active",
        lines=[
            ("u_carol", "Hi Lisa, is now a good time?", False),
            ("u_lisa", "Of course, I am here. What is on your mind?", False),
        ],
    ),
    SeedSession("listen", "u_bob", "u_leo", 0.1, "pending"),
]


@lru_cache
def _seed_password_hash() -> str:
    # All seed users share one password; hash it once (argon2 is deliberately slow).
    return hash_password(SEED_PASSWORD)


def truncate_all(db: Session) -> None:
    tables = ", ".join(m.ALL_TABLES)
    db.execute(text(f"TRUNCATE {tables} CASCADE"))


def seed(db: Session, now: datetime | None = None) -> None:
    now = now or utc_now()
    pw = _seed_password_hash()

    db.add_all(
        m.User(
            id=uid, username=username, email=f"{username}@vibishan.app", password_hash=pw,
            role=role, name=name, phone=f"+91 98765 4321{i}", bio=bio, expertise=expertise,
            notify_requests=True, show_message_previews=True, available=True,
            created_at=now - 90 * DAY,
        )
        for i, (uid, username, role, name, bio, expertise) in enumerate(USERS)
    )
    db.flush()

    for n, s in enumerate(SESSIONS, start=1):
        req_id, room_id = f"req_seed{n}", f"room_seed{n}"
        created = now - s.days_ago * DAY
        req_status = "pending" if s.status == "pending" else "accepted"
        half_day = created + DAY / 2

        db.add(m.ServiceRequest(
            id=req_id, kind=s.kind, requester_id=s.requester, provider_id=s.provider,
            status=req_status, room_id=room_id, created_at=created,
        ))
        db.flush()
        db.add(m.Room(
            id=room_id, kind=s.kind, request_id=req_id, requester_id=s.requester,
            provider_id=s.provider, status=s.status, created_at=created,
            closed_at=half_day if s.status == "closed" else None,
        ))
        db.flush()

        db.add_all(
            m.RequestParticipant(request_id=req_id, user_id=uid, position=i)
            for i, uid in enumerate(s.participants)
        )
        db.add_all(
            m.RequestApproval(request_id=req_id, user_id=uid, state=req_status)
            for uid in [*s.participants, s.provider]
        )
        db.add_all(
            m.RoomMember(room_id=room_id, user_id=uid, position=i)
            for i, uid in enumerate([s.requester, *s.participants, s.provider])
        )
        for i, (sender, body, starred) in enumerate(s.lines):
            msg_id = f"msg_seed{n}_{i}"
            db.add(m.Message(
                id=msg_id, room_id=room_id, sender_id=sender, text=body,
                created_at=created + (i + 1) * timedelta(seconds=60),
            ))
            if starred:
                db.flush()
                db.add(m.MessageStar(message_id=msg_id, user_id=s.requester))
        db.add_all(
            m.RoomClosure(room_id=room_id, user_id=uid, text=body, at=half_day)
            for uid, body in s.closures
        )
        db.add_all(
            m.RoomRating(room_id=room_id, by_id=uid, stars=stars, feedback=fb, at=half_day)
            for uid, stars, fb in s.ratings
        )
        db.flush()

    seed9_created = now - SESSIONS[8].days_ago * DAY
    db.add_all([
        m.Notification(
            id="ntf_seed1", user_id="u_leo", kind="request_received", request_id="req_seed9",
            text="Bob Mehta requested a listening session.", read=False, created_at=seed9_created,
        ),
        m.Notification(
            id="ntf_seed2", user_id="u_bob", kind="request_sent", request_id="req_seed9",
            text="You sent a listening request to Leo Fernandes.", read=True,
            created_at=seed9_created,
        ),
    ])
    db.flush()


def reset(db: Session) -> None:
    truncate_all(db)
    seed(db)


if __name__ == "__main__":
    from app.db.session import get_sessionmaker

    with get_sessionmaker()() as session, session.begin():
        reset(session)
    print("Database reset to seed data.")
