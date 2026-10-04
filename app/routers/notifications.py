from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.requests import NotificationItem, UnreadCount
from app.services import notifications as svc

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationItem])
def list_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.list_notifications(db, user)


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return UnreadCount(count=svc.unread_count(db, user))


@router.post("/read-all", status_code=204)
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    svc.mark_all_read(db, user)
    return Response(status_code=204)
