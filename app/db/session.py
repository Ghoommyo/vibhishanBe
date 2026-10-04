from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    # NullPool: serverless instances must not hold connections between requests;
    # pooling is done by the provider's pooled endpoint (spec §3.3).
    return create_engine(get_settings().database_url, poolclass=NullPool)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=True, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """One transaction per request: commit on success, roll back on any error."""
    db = get_sessionmaker()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
