import os

# Point the app at the test database before anything imports the settings.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://localhost:5432/vibishan_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ENABLE_DEV_ENDPOINTS"] = "true"
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-bytes-long")

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


SEED_ROLES = {
    "alice": "user", "bob": "user", "carol": "user",
    "lisa": "listener", "leo": "listener", "maya": "moderator", "max": "moderator",
}


@pytest.fixture
def auth(client):
    """auth("alice") -> Authorization headers for a seed user (cached per test)."""
    cache: dict[str, dict] = {}

    def _auth(username: str) -> dict:
        if username not in cache:
            r = client.post("/api/v1/auth/login", json={
                "username": username, "password": "password123", "role": SEED_ROLES[username],
            })
            assert r.status_code == 200, r.text
            cache[username] = {"Authorization": f"Bearer {r.json()['token']}"}
        return cache[username]

    return _auth
