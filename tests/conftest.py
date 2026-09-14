"""
tests/conftest.py
Shared pytest fixtures: isolated SQLite DB per test, FastAPI TestClient with
dependency overrides, fast bcrypt for speed, deterministic payloads.
"""
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import bcrypt as _bcrypt

from backend.auth import hash_password
from backend.database import Base, get_db
from backend.main import app
from backend.models_db import User

# ── Speed up bcrypt for the suite (real rounds verified in test_security) ────
_REAL_GENSALT = _bcrypt.gensalt


def _fast_gensalt(*args, **kwargs):
    kwargs.setdefault("rounds", 4)
    return _REAL_GENSALT(*args, **kwargs)


_bcrypt.gensalt = _fast_gensalt


@pytest.fixture()
def db_engine(tmp_path):
    """Fresh file-backed SQLite engine per test with all tables created."""
    url = f"sqlite:///{tmp_path}/test.db"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """Single ORM session bound to the per-test engine."""
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = factory()
    yield session
    session.close()


def _seed(session, username, password, email, role):
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        role=role,
    )
    session.add(user)
    session.commit()
    return user


@pytest.fixture()
def client(db_engine):
    """TestClient whose get_db dependency uses the per-test database.

    NOTE: TestClient is used WITHOUT a context manager so the app lifespan
    (which seeds the real database file) never runs during tests.
    """
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded_client(client, db_session):
    """Client with admin + regular user rows present in the test DB."""
    _seed(db_session, "admin", "admin123", "admin@fraudguard.ai", "admin")
    _seed(db_session, "demo", "demo1234", "demo@fraudguard.ai", "user")
    return client


def _login(client, username, password):
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture()
def admin_token(seeded_client):
    return _login(seeded_client, "admin", "admin123")


@pytest.fixture()
def user_token(seeded_client):
    return _login(seeded_client, "demo", "demo1234")


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ── Deterministic payloads (verified against the committed artefact) ─────────
SAFE_TXN = {
    "account_id": 1,
    "amount": 2500,
    "location": "Chennai",
    "transaction_type": "POS",
    "time_of_day": 14,
    "distance_from_home": 5,
    "device_trust_score": 90,
    "failed_attempts_24h": 0,
    "txn_velocity_1h": 1,
    "merchant_risk_score": 10,
    "is_international": 0,
    "card_present": 1,
}

RISKY_TXN = {
    "account_id": 7,
    "amount": 60000,
    "location": "Delhi",
    "transaction_type": "Online",
    "time_of_day": 2,
    "distance_from_home": 500,
    "device_trust_score": 10,
    "failed_attempts_24h": 8,
    "txn_velocity_1h": 12,
    "merchant_risk_score": 95,
    "is_international": 1,
    "card_present": 0,
}
