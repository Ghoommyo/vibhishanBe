from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.users import (
    ProfilePatch,
    ProviderRole,
    ProviderSummary,
    PublicUser,
    SettingsPatch,
)
from app.services import users as svc

router = APIRouter(tags=["users"])


# Static /users/* paths must be declared before /users/{user_id}.
@router.get("/users/me", response_model=ProviderSummary)
def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.me(db, user)


@router.patch("/users/me/profile", response_model=PublicUser)
def patch_profile(
    body: ProfilePatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return svc.update_profile(db, user, body)


@router.patch("/users/me/settings", response_model=PublicUser)
def patch_settings(
    body: SettingsPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return svc.update_settings(db, user, body)


@router.get("/users/search", response_model=list[PublicUser])
def search_users(
    q: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return svc.search_users(db, user, q)


@router.get("/users/{user_id}", response_model=PublicUser)
def get_user(user_id: str, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.public_user(svc.get_user(db, user_id))


@router.get("/providers", response_model=list[ProviderSummary])
def list_providers(
    role: ProviderRole = Query(...),
    q: str | None = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.list_providers(db, role, q)
