from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.rooms import (
    ClosureBody,
    MessageOut,
    MessageWithSender,
    MuteBody,
    RateBody,
    RoomDetail,
    RoomListItem,
    RoomOut,
    RoomSummary,
    SendMessageBody,
)
from app.services import rooms as svc

router = APIRouter(tags=["rooms"])


@router.get("/rooms", response_model=list[RoomListItem])
def list_rooms(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.list_rooms(db, user)


@router.get("/rooms/{room_id}", response_model=RoomDetail)
def get_room(room_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.room_detail(db, user, room_id)


@router.get("/rooms/{room_id}/messages", response_model=list[MessageWithSender])
def list_messages(
    room_id: str,
    after: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.list_messages(db, user, room_id, after)


@router.post("/rooms/{room_id}/messages", response_model=MessageOut, status_code=201)
def send_message(
    room_id: str,
    body: SendMessageBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.send_message(db, user, room_id, body.text)


@router.post("/messages/{message_id}/star", response_model=MessageOut)
def toggle_star(
    message_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return svc.toggle_star(db, user, message_id)


@router.post("/rooms/{room_id}/closure", response_model=RoomOut)
def submit_closure(
    room_id: str,
    body: ClosureBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.submit_closure(db, user, room_id, body.text)


@router.put("/rooms/{room_id}/members/{user_id}/mute", response_model=RoomOut)
def set_muted(
    room_id: str,
    user_id: str,
    body: MuteBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.set_muted(db, user, room_id, user_id, body.muted)


@router.post("/rooms/{room_id}/ratings", response_model=RoomOut, status_code=201)
def rate(
    room_id: str,
    body: RateBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.rate(db, user, room_id, body.stars, body.feedback)


@router.get("/rooms/{room_id}/summary", response_model=RoomSummary)
def summary(room_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.summary(db, user, room_id)
