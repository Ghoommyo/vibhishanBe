from fastapi import APIRouter
from sqlalchemy import text

from app.core.errors import error_response
from app.db.session import get_engine

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return error_response(503, "unavailable", "Database unreachable.")
    return {"status": "ok"}
