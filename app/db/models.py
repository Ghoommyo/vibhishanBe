"""SQLAlchemy models for the normalized schema in spec §8.

The API assembles nested shapes (approvals, memberIds, closures, ...) from these tables.
"""

from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Text,
    func,
    text as sql_text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

TS = DateTime(timezone=True)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def _user_fk() -> ForeignKey:
    return ForeignKey("users.id", ondelete="CASCADE")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user','listener','moderator')", name="role"),
        Index("users_username_lower", func.lower(sql_text("username")), unique=True),
        Index("users_email_lower", func.lower(sql_text("email")), unique=True),
        Index("users_role", "role"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    username: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text, server_default="")
    phone: Mapped[str] = mapped_column(Text, server_default="")
    bio: Mapped[str] = mapped_column(Text, server_default="")
    expertise: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    notify_requests: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("true"))
    show_message_previews: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("true"))
    available: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("true"))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class ServiceRequest(Base):
    __tablename__ = "service_requests"
    __table_args__ = (
        CheckConstraint("kind IN ('listen','moderate')", name="kind"),
        CheckConstraint("status IN ('pending','accepted','rejected')", name="status"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    requester_id: Mapped[str] = mapped_column(Text, _user_fk())
    provider_id: Mapped[str] = mapped_column(Text, _user_fk())
    status: Mapped[str] = mapped_column(Text)
    room_id: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class RequestParticipant(Base):
    __tablename__ = "request_participants"

    request_id: Mapped[str] = mapped_column(
        Text, ForeignKey("service_requests.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(Text, _user_fk(), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)


class RequestApproval(Base):
    __tablename__ = "request_approvals"
    __table_args__ = (CheckConstraint("state IN ('pending','accepted','rejected')", name="state"),)

    request_id: Mapped[str] = mapped_column(
        Text, ForeignKey("service_requests.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(Text, _user_fk(), primary_key=True)
    state: Mapped[str] = mapped_column(Text)


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        CheckConstraint("kind IN ('listen','moderate')", name="kind"),
        CheckConstraint("status IN ('pending','active','closed','rejected')", name="status"),
        Index("rooms_provider", "provider_id", "status"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(
        Text, ForeignKey("service_requests.id", ondelete="CASCADE"), unique=True
    )
    requester_id: Mapped[str] = mapped_column(Text, _user_fk())
    provider_id: Mapped[str] = mapped_column(Text, _user_fk())
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


def _room_fk() -> ForeignKey:
    return ForeignKey("rooms.id", ondelete="CASCADE")


class RoomMember(Base):
    __tablename__ = "room_members"
    __table_args__ = (Index("room_members_user", "user_id"),)

    room_id: Mapped[str] = mapped_column(Text, _room_fk(), primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, _user_fk(), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)


class RoomMute(Base):
    __tablename__ = "room_mutes"

    room_id: Mapped[str] = mapped_column(Text, _room_fk(), primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, _user_fk(), primary_key=True)


class RoomClosure(Base):
    __tablename__ = "room_closures"

    room_id: Mapped[str] = mapped_column(Text, _room_fk(), primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, _user_fk(), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class RoomRating(Base):
    __tablename__ = "room_ratings"
    __table_args__ = (CheckConstraint("stars BETWEEN 1 AND 5", name="stars"),)

    room_id: Mapped[str] = mapped_column(Text, _room_fk(), primary_key=True)
    by_id: Mapped[str] = mapped_column(Text, _user_fk(), primary_key=True)
    stars: Mapped[int] = mapped_column(Integer)
    feedback: Mapped[str] = mapped_column(Text, server_default="")
    at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("messages_room_created", "room_id", "created_at"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    room_id: Mapped[str] = mapped_column(Text, _room_fk())
    sender_id: Mapped[str] = mapped_column(Text, _user_fk())
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class MessageStar(Base):
    __tablename__ = "message_stars"

    message_id: Mapped[str] = mapped_column(
        Text, ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(Text, _user_fk(), primary_key=True)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('request_sent','request_received','request_update')", name="kind"
        ),
        Index("notifications_user_created", "user_id", sql_text("created_at DESC")),
        Index("notifications_user_unread", "user_id", postgresql_where=sql_text("NOT read")),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, _user_fk())
    kind: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(
        Text, ForeignKey("service_requests.id", ondelete="CASCADE")
    )
    text: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("false"))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


ALL_TABLES = [t.name for t in Base.metadata.sorted_tables]
