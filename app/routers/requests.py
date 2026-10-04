from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.requests import (
    ListenBody,
    ModerateBody,
    RespondBody,
    SentRequestsResult,
    ServiceRequestOut,
)
from app.services import requests as svc

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("/listen", response_model=SentRequestsResult, status_code=201)
def send_listen(
    body: ListenBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return svc.send_listen(db, user, body.provider_ids)


@router.post("/moderate", response_model=SentRequestsResult, status_code=201)
def send_moderate(
    body: ModerateBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return svc.send_moderate(db, user, body)


@router.post("/{request_id}/respond", response_model=ServiceRequestOut)
def respond(
    request_id: str,
    body: RespondBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.respond(db, user, request_id, body.accept)
