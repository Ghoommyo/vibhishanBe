import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import create_token, hash_password, verify_password
from app.core.utils import new_id, now, to_ms
from app.db.models import Room, RoomRating, User
from app.schemas.users import (
    AuthResponse,
    LoginBody,
    Profile,
    ProfilePatch,
    ProviderSummary,
    PublicUser,
    RatingSummary,
    SettingsPatch,
    SignupBody,
    UserSettings,
)

ROLES = ("user", "listener", "moderator")
ROLE_LABELS = {"user": "User", "listener": "Listener", "moderator": "Moderator"}
EMAIL_RE = re.compile(r"^\S+@\S+\.\S+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,30}$")


# ---------- serialization ----------

def public_user(u: User) -> PublicUser:
    return PublicUser(
        id=u.id,
        username=u.username,
        email=u.email,
        role=u.role,
        profile=Profile(name=u.name, phone=u.phone, bio=u.bio, expertise=list(u.expertise or [])),
        settings=UserSettings(
            notify_requests=u.notify_requests,
            show_message_previews=u.show_message_previews,
            available=u.available,
        ),
        created_at=to_ms(u.created_at),
    )


def rating_summaries(db: Session, provider_ids: list[str]) -> dict[str, RatingSummary]:
    """Rating summary (spec §7.8) for many providers in one grouped query."""
    result = {pid: RatingSummary(average=None, count=0) for pid in provider_ids}
    if not provider_ids:
        return result
    rows = db.execute(
        select(Room.provider_id, func.avg(RoomRating.stars), func.count(RoomRating.stars))
        .join(RoomRating, RoomRating.room_id == Room.id)
        .where(Room.provider_id.in_(provider_ids))
        .group_by(Room.provider_id)
    ).all()
    for pid, avg, count in rows:
        result[pid] = RatingSummary(average=float(avg), count=count)
    return result


def provider_summary(u: User, rating: RatingSummary) -> ProviderSummary:
    return ProviderSummary(**public_user(u).model_dump(), rating=rating)


def load_users(db: Session, ids) -> dict[str, User]:
    ids = list(set(ids))
    if not ids:
        return {}
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))}


# ---------- lookups ----------

def _by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.username) == username.lower()))


def _by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


def get_user(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise ApiError("not_found", "User not found.")
    return user


def _normalize_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ApiError("invalid_email", "Enter a valid email.")
    return email


# ---------- auth ----------

def signup(db: Session, body: SignupBody) -> AuthResponse:
    username = body.username.strip()
    if not USERNAME_RE.match(username):
        raise ApiError(
            "validation", "Username must be 3-30 characters: letters, digits, _ or ."
        )
    email = _normalize_email(body.email)
    if len(body.password) < 8:
        raise ApiError("validation", "Password must be at least 8 characters.")
    if body.role not in ROLES:
        raise ApiError("validation", "Choose a valid account type.")
    if _by_username(db, username):
        raise ApiError("username_taken", "That username is already taken.")
    if _by_email(db, email):
        raise ApiError("email_taken", "An account with that email already exists.")

    user = User(
        id=new_id("u"),
        username=username,
        email=email,
        password_hash=hash_password(body.password),
        role=body.role,
        name=username,
        phone="",
        bio="",
        expertise=[],
        notify_requests=True,
        show_message_previews=True,
        available=True,
        created_at=now(),
    )
    db.add(user)
    db.flush()
    return AuthResponse(token=create_token(user.id), user=public_user(user))


def login(db: Session, body: LoginBody) -> AuthResponse:
    user = _by_username(db, body.username.strip())
    if user is None or not verify_password(body.password, user.password_hash):
        raise ApiError("invalid_credentials", "Incorrect username or password.")
    if user.role != body.role:
        raise ApiError("wrong_role", f"This account is registered as a {ROLE_LABELS[user.role]}.")
    return AuthResponse(token=create_token(user.id), user=public_user(user))


# ---------- profile / settings ----------

def me(db: Session, user: User) -> ProviderSummary:
    return provider_summary(user, rating_summaries(db, [user.id])[user.id])


def update_profile(db: Session, user: User, patch: ProfilePatch) -> PublicUser:
    changes = patch.model_dump(exclude_unset=True)
    if changes.get("email") is not None:
        email = _normalize_email(changes["email"])
        other = _by_email(db, email)
        if other is not None and other.id != user.id:
            raise ApiError("email_taken", "An account with that email already exists.")
        user.email = email
    for field in ("name", "phone", "bio", "expertise"):
        if changes.get(field) is not None:
            setattr(user, field, changes[field])
    db.flush()
    return public_user(user)


def update_settings(db: Session, user: User, patch: SettingsPatch) -> PublicUser:
    for field, value in patch.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(user, field, value)
    db.flush()
    return public_user(user)


# ---------- search ----------

def _matches(q: str | None):
    q = (q or "").strip().lower()
    if not q:
        return None
    return or_(
        func.lower(User.username).contains(q, autoescape=True),
        func.lower(User.name).contains(q, autoescape=True),
    )


def list_providers(db: Session, role: str, q: str | None) -> list[ProviderSummary]:
    stmt = select(User).where(User.role == role, User.available.is_(True))
    if (cond := _matches(q)) is not None:
        stmt = stmt.where(cond)
    users = db.scalars(stmt.order_by(User.name, User.username)).all()
    ratings = rating_summaries(db, [u.id for u in users])
    return [provider_summary(u, ratings[u.id]) for u in users]


def search_users(db: Session, caller: User, q: str | None) -> list[PublicUser]:
    stmt = select(User).where(User.role == "user", User.id != caller.id)
    if (cond := _matches(q)) is not None:
        stmt = stmt.where(cond)
    return [public_user(u) for u in db.scalars(stmt.order_by(User.name, User.username))]
