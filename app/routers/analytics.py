from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.analytics import ProviderStats
from app.services import analytics as svc

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/provider", response_model=ProviderStats)
def provider_stats(
    tzOffset: int = 0,  # noqa: N803 - query param name is part of the API contract
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.provider_stats(db, user, tzOffset)
