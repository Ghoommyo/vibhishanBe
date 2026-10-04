import secrets
import string
from datetime import datetime, timezone

_ID_ALPHABET = string.ascii_lowercase + string.digits


def now() -> datetime:
    """Current time (tz-aware UTC), truncated to milliseconds so stored values
    round-trip exactly through the ms timestamps used on the wire (e.g. `?after=`)."""
    t = datetime.now(timezone.utc)
    return t.replace(microsecond=t.microsecond // 1000 * 1000)


def to_ms(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    return int(dt.timestamp() * 1000)


def from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def new_id(prefix: str) -> str:
    """Opaque id like `room_lx3k9a2b7f` (spec §4.2)."""
    return f"{prefix}_" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(10))


def display_name(user) -> str:
    """profile.name if non-empty, else username."""
    return user.name or user.username


def join_names(names: list[str]) -> str:
    """"A" / "A and B" / "A, B and C" (no Oxford comma)."""
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]
