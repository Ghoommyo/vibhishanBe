from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app import seed
from app.db.session import get_db

router = APIRouter(prefix="/dev", tags=["dev"])


@router.post("/reset", status_code=204)
def reset_db(db: Session = Depends(get_db)) -> Response:
    seed.reset(db)
    return Response(status_code=204)
