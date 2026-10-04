import os

# Point the app at the test database before anything imports the settings.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://localhost:5432/vibishan_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ENABLE_DEV_ENDPOINTS"] = "true"
os.environ.setdefault("JWT_SECRET", "test-secret")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import seed  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.main import app  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _fresh_seed(_migrate):
    """Every test starts from the exact seed state (spec §9)."""
    with get_sessionmaker()() as db, db.begin():
        seed.reset(db)


@pytest.fixture
def db():
    with get_sessionmaker()() as session:
        yield session


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
