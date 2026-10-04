from typing import Literal

from app.schemas.common import CamelModel

Role = Literal["user", "listener", "moderator"]
ProviderRole = Literal["listener", "moderator"]


class Profile(CamelModel):
    name: str
    phone: str
    bio: str
    expertise: list[str]


class UserSettings(CamelModel):
    notify_requests: bool
    show_message_previews: bool
    available: bool


class PublicUser(CamelModel):
    id: str
    username: str
    email: str
    role: Role
    profile: Profile
    settings: UserSettings
    created_at: int


class RatingSummary(CamelModel):
    average: float | None
    count: int


class ProviderSummary(PublicUser):
    rating: RatingSummary


class AuthResponse(CamelModel):
    token: str
    user: PublicUser


class SignupBody(CamelModel):
    username: str
    email: str
    password: str
    role: str


class LoginBody(CamelModel):
    username: str
    password: str
    role: str


class ProfilePatch(CamelModel):
    name: str | None = None
    phone: str | None = None
    bio: str | None = None
    expertise: list[str] | None = None
    email: str | None = None


class SettingsPatch(CamelModel):
    notify_requests: bool | None = None
    show_message_previews: bool | None = None
    available: bool | None = None
