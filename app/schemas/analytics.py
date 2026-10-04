from app.schemas.common import CamelModel
from app.schemas.users import PublicUser


class WeeklyBucket(CamelModel):
    label: str
    value: int
    start: int
    end: int


class FeedbackItem(CamelModel):
    by: PublicUser
    stars: int
    text: str
    at: int


class ProviderStats(CamelModel):
    listening_done: int
    moderation_done: int
    active_sessions: int
    average_rating: float | None
    rating_count: int
    rating_distribution: list[int]
    weekly: list[WeeklyBucket]
    feedback: list[FeedbackItem]
