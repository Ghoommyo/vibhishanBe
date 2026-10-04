from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.users import AuthResponse, LoginBody, PublicUser, SignupBody
from app.services import users as svc

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse, status_code=201)
def signup(body: SignupBody, db: Session = Depends(get_db)):
    return svc.signup(db, body)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginBody, db: Session = Depends(get_db)):
    return svc.login(db, body)


@router.get("/me", response_model=PublicUser)
def me(user: User = Depends(get_current_user)):
    return svc.public_user(user)


@router.post("/logout", status_code=204)
def logout(_: User = Depends(get_current_user)) -> Response:
    return Response(status_code=204)
