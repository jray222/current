import os
import sys
import tempfile
from pathlib import Path

import pytest

# Isolated database + settings, applied before the app is imported.
_tmp = tempfile.mkdtemp(prefix="current-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp, 'test.db').as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-key-" + "x" * 48
os.environ["ALLOW_REGISTRATION"] = "True"
os.environ["ANTHROPIC_API_KEY"] = ""
# Background jobs (collecting pictures) wait in a list until a test drains them.
os.environ["JOB_QUEUE"] = "manual"
os.environ["IMAGES_DIR"] = str(Path(_tmp, "images"))
# Collection never runs by itself in tests (and never reaches the network: see fake_sources).
os.environ["AUTO_COLLECT"] = "False"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.rate_limit import auth_rate_limiter  # noqa: E402

PASSWORD = "Correct-Horse-Battery-9"


@pytest.fixture(scope="session")
def schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def fresh_db(schema):
    # Emptying the tables is much faster than re-creating them for every test.
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    auth_rate_limiter.reset()
    from app.services import keys, lockout
    lockout.reset()
    keys.reset_state()
    yield


def _client() -> TestClient:
    return TestClient(app)


def authed(client: TestClient, token: str) -> TestClient:
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture
def make_user():
    """Registers a new user (and household); returns an authenticated client and its user JSON."""
    def _make(username: str, household_name: str | None = None):
        client = _client()
        res = client.post(
            "/api/v1/auth/register",
            json={"username": username, "password": PASSWORD, "household_name": household_name},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        return authed(client, body["access_token"]), body["user"]
    return _make


@pytest.fixture
def anon_client():
    return _client()


FIXTURES = Path(__file__).resolve().parent / "fixtures"
