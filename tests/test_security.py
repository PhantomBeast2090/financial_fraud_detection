"""
tests/test_security.py — hashing, JWT lifecycle, RBAC, secret handling (1F/8).
"""
from datetime import timedelta

import pytest

from backend.auth import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_roundtrip():
    hashed = hash_password("correct-horse-123")
    assert verify_password("correct-horse-123", hashed) is True
    assert verify_password("wrong", hashed) is False
    assert hashed != "correct-horse-123"


def test_real_bcrypt_rounds_still_work():
    """The suite patches gensalt for speed; real defaults must still verify."""
    import bcrypt

    from tests.conftest import _REAL_GENSALT

    hashed = bcrypt.hashpw(b"pw", _REAL_GENSALT()).decode()
    assert bcrypt.checkpw(b"pw", hashed.encode()) is True


def test_jwt_roundtrip():
    token = create_access_token({"sub": "admin", "role": "admin"})
    payload = decode_token(token)
    assert payload["sub"] == "admin"
    assert payload["role"] == "admin"


def test_expired_token_rejected():
    token = create_access_token({"sub": "admin"}, expires_delta=timedelta(seconds=-1))
    with pytest.raises(Exception) as exc:
        decode_token(token)
    assert getattr(exc.value, "status_code", 401) == 401


def test_tampered_token_rejected():
    token = create_access_token({"sub": "admin"})
    with pytest.raises(Exception):
        decode_token(token + "tamper")


def test_missing_sub_rejected_at_dependency(seeded_client):
    token = create_access_token({"role": "admin"})
    resp = seeded_client.get("/api/auth/me",
                             headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_inactive_user_rejected(seeded_client, db_session):
    from backend.models_db import User

    user = db_session.query(User).filter(User.username == "demo").one()
    user.is_active = False
    db_session.commit()
    token = create_access_token({"sub": "demo", "role": "user"})
    resp = seeded_client.get("/api/auth/me",
                             headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_admin_only_model_history(seeded_client, admin_token, user_token):
    from tests.conftest import auth_headers

    assert seeded_client.get(
        "/api/model/history",
        headers=auth_headers(user_token)).status_code == 403
    assert seeded_client.get(
        "/api/model/history",
        headers=auth_headers(admin_token)).status_code == 200


def test_admin_only_train(seeded_client, user_token):
    from tests.conftest import auth_headers

    assert seeded_client.post(
        "/api/model/train",
        headers=auth_headers(user_token)).status_code == 403


def test_secret_key_env_override(monkeypatch):
    import importlib

    settings_module = importlib.import_module("config.settings")

    monkeypatch.setenv("SECRET_KEY", "test-only-secret-value-0123456789")
    fresh = settings_module.Settings()
    assert fresh.SECRET_KEY == "test-only-secret-value-0123456789"
    assert fresh.uses_default_secret is False


def test_default_secret_detected():
    from config.settings import DEFAULT_SECRET_KEY, settings

    assert settings.uses_default_secret == (settings.SECRET_KEY == DEFAULT_SECRET_KEY)


def test_insecure_defaults_warn(monkeypatch):
    import importlib
    import warnings

    settings_module = importlib.import_module("config.settings")

    insecure = settings_module.Settings(
        DEBUG=False,
        SECRET_KEY=settings_module.DEFAULT_SECRET_KEY,
        ADMIN_PASSWORD="admin123",
        DEMO_PASSWORD="demo1234",
    )
    with pytest.warns(RuntimeWarning, match="INSECURE DEFAULTS"):
        insecure.warn_if_insecure_defaults()

    secure = settings_module.Settings(
        DEBUG=False,
        SECRET_KEY="a-very-long-unique-production-secret-xyz",
        ADMIN_PASSWORD="unique-admin-pw",
        DEMO_PASSWORD="unique-demo-pw",
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        secure.warn_if_insecure_defaults()  # must not warn


def test_demo_credentials_env_override(monkeypatch):
    import importlib

    settings_module = importlib.import_module("config.settings")

    monkeypatch.setenv("ADMIN_PASSWORD", "env-admin-pw")
    monkeypatch.setenv("SEED_DEFAULT_USERS", "false")
    fresh = settings_module.Settings()
    assert fresh.ADMIN_PASSWORD == "env-admin-pw"
    assert fresh.SEED_DEFAULT_USERS is False


def test_seeding_disabled_skips_db(monkeypatch):
    """SEED_DEFAULT_USERS=false must return before touching the database."""
    import backend.main as main_module

    monkeypatch.setattr(main_module.settings, "SEED_DEFAULT_USERS", False)
    assert main_module._seed_default_users() is None
