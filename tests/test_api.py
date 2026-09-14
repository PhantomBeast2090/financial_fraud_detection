"""
tests/test_api.py — FastAPI surface: system, auth, predict, analytics,
simulation, review, model endpoints, validation + status codes (1D).
"""
from unittest.mock import patch

import pytest

from tests.conftest import RISKY_TXN, SAFE_TXN, auth_headers


def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "docs" in resp.json()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "FraudGuard AI"


def test_register_and_login_roundtrip(client):
    reg = client.post("/api/auth/register", json={
        "username": "alice", "email": "alice@example.com", "password": "secret123",
    })
    assert reg.status_code == 201, reg.text
    login = client.post("/api/auth/login",
                        json={"username": "alice", "password": "secret123"})
    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"


def test_register_duplicate_username_rejected(seeded_client):
    resp = seeded_client.post("/api/auth/register", json={
        "username": "admin", "email": "other@example.com", "password": "secret123",
    })
    assert resp.status_code == 400


def test_login_wrong_password_rejected(seeded_client):
    resp = seeded_client.post("/api/auth/login",
                              json={"username": "admin", "password": "nope"})
    assert resp.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_profile(seeded_client, admin_token):
    resp = seeded_client.get("/api/auth/me", headers=auth_headers(admin_token))
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


def test_protected_endpoints_require_auth(client):
    assert client.get("/api/transactions/").status_code in (401, 403)
    assert client.get("/api/analytics/dashboard").status_code in (401, 403)
    assert client.get("/api/review/queue").status_code in (401, 403)


def test_predict_safe_transaction(seeded_client, user_token):
    resp = seeded_client.post("/api/transactions/predict", json=SAFE_TXN,
                              headers=auth_headers(user_token))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["label"] == "Legitimate"
    assert body["status"] == "APPROVED"
    assert body["explanation"]["label"] == "Legitimate"
    assert body["explanation"]["factors_triggered"] == 0


def test_predict_risky_transaction_blocked(seeded_client, user_token):
    resp = seeded_client.post("/api/transactions/predict", json=RISKY_TXN,
                              headers=auth_headers(user_token))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["label"] == "Fraud"
    assert body["status"] == "BLOCKED"
    assert body["risk_level"] == "High"
    assert len(body["reasons"]) >= 1
    assert body["explanation"]["factors_triggered"] >= 1


def test_predict_validation_errors(seeded_client, user_token):
    headers = auth_headers(user_token)
    # Unknown location rejected by schema validator.
    bad = dict(SAFE_TXN, location="Atlantis")
    assert seeded_client.post("/api/transactions/predict", json=bad,
                              headers=headers).status_code == 422
    # Non-positive amount rejected.
    bad = dict(SAFE_TXN, amount=-5)
    assert seeded_client.post("/api/transactions/predict", json=bad,
                              headers=headers).status_code == 422
    # Missing required amount rejected.
    bad = dict(SAFE_TXN)
    del bad["amount"]
    assert seeded_client.post("/api/transactions/predict", json=bad,
                              headers=headers).status_code == 422


def test_predict_persists_and_lists(seeded_client, user_token):
    headers = auth_headers(user_token)
    created = seeded_client.post("/api/transactions/predict", json=SAFE_TXN,
                                 headers=headers).json()
    listed = seeded_client.get("/api/transactions/", headers=headers)
    assert listed.status_code == 200
    assert any(t["transaction_id"] == created["transaction_id"] for t in listed.json())
    single = seeded_client.get(
        f"/api/transactions/{created['transaction_id']}", headers=headers)
    assert single.status_code == 200
    assert seeded_client.get("/api/transactions/does-not-exist",
                             headers=headers).status_code == 404


def test_delete_transaction_admin_only(seeded_client, admin_token, user_token):
    txn_id = seeded_client.post(
        "/api/transactions/predict", json=SAFE_TXN,
        headers=auth_headers(user_token)).json()["transaction_id"]
    forbidden = seeded_client.delete(f"/api/transactions/{txn_id}",
                                     headers=auth_headers(user_token))
    assert forbidden.status_code == 403
    ok = seeded_client.delete(f"/api/transactions/{txn_id}",
                              headers=auth_headers(admin_token))
    assert ok.status_code == 204
    assert seeded_client.get(f"/api/transactions/{txn_id}",
                             headers=auth_headers(admin_token)).status_code == 404


def test_dashboard_aggregation(seeded_client, user_token):
    headers = auth_headers(user_token)
    seeded_client.post("/api/transactions/predict", json=SAFE_TXN, headers=headers)
    seeded_client.post("/api/transactions/predict", json=RISKY_TXN, headers=headers)
    resp = seeded_client.get("/api/analytics/dashboard", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_transactions"] == 2
    assert body["total_fraud"] == 1
    assert body["total_legitimate"] == 1
    assert body["fraud_rate"] == 50.0
    assert len(body["recent_transactions"]) == 2


def test_alerts_list_and_resolve(seeded_client, admin_token, user_token):
    user_h, admin_h = auth_headers(user_token), auth_headers(admin_token)
    seeded_client.post("/api/transactions/predict", json=RISKY_TXN, headers=user_h)
    alerts = seeded_client.get("/api/analytics/alerts", headers=user_h).json()
    assert len(alerts) == 1
    alert_id = alerts[0]["transaction_id"]
    # Non-admin cannot resolve.
    assert seeded_client.post(
        f"/api/analytics/alerts/{alerts[0]['id']}/resolve",
        headers=user_h).status_code == 403
    ok = seeded_client.post(f"/api/analytics/alerts/{alerts[0]['id']}/resolve",
                            headers=admin_h)
    assert ok.status_code == 200
    assert seeded_client.post("/api/analytics/alerts/99999/resolve",
                              headers=admin_h).status_code == 404
    assert alert_id


def test_model_metrics_fallback_to_disk(seeded_client, user_token):
    resp = seeded_client.get("/api/analytics/model-metrics",
                             headers=auth_headers(user_token))
    assert resp.status_code == 200
    assert resp.json()["model_name"] == "BalancedLogisticRegression"


def test_export_csv(seeded_client, user_token):
    headers = auth_headers(user_token)
    seeded_client.post("/api/transactions/predict", json=SAFE_TXN, headers=headers)
    resp = seeded_client.get("/api/analytics/export/csv", headers=headers)
    assert resp.status_code == 200
    assert "transaction_id" in resp.text.splitlines()[0]


def test_simulate_one_persists(seeded_client, user_token, db_engine):
    import importlib
    from sqlalchemy.orm import sessionmaker

    sim = importlib.import_module("backend.routers.simulate_router")
    factory = sessionmaker(bind=db_engine)  # redirect simulator writes to test DB
    with patch.object(sim, "SessionLocal", factory):
        resp = seeded_client.post("/api/simulate/one",
                                  headers=auth_headers(user_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["label"] in ("Fraud", "Legitimate")
    assert "explanation" in body


def test_review_queue_approve_flow(seeded_client, admin_token, user_token):
    headers = auth_headers(user_token)
    txn_id = seeded_client.post("/api/transactions/predict", json=RISKY_TXN,
                                headers=headers).json()["transaction_id"]
    queue = seeded_client.get("/api/review/queue", headers=headers).json()
    assert any(t["transaction_id"] == txn_id for t in queue)
    approved = seeded_client.post(f"/api/review/{txn_id}/approve", headers=headers)
    assert approved.status_code == 200
    assert approved.json()["new_status"] == "APPROVED"
    queue_after = seeded_client.get("/api/review/queue", headers=headers).json()
    assert not any(t["transaction_id"] == txn_id for t in queue_after)


def test_review_reject_flow(seeded_client, user_token):
    headers = auth_headers(user_token)
    txn_id = seeded_client.post("/api/transactions/predict", json=RISKY_TXN,
                                headers=headers).json()["transaction_id"]
    rejected = seeded_client.post(f"/api/review/{txn_id}/reject", headers=headers)
    assert rejected.status_code == 200
    assert rejected.json()["new_status"] == "REJECTED"


def test_review_requires_blocked_status(seeded_client, user_token):
    headers = auth_headers(user_token)
    txn_id = seeded_client.post("/api/transactions/predict", json=SAFE_TXN,
                                headers=headers).json()["transaction_id"]
    resp = seeded_client.post(f"/api/review/{txn_id}/approve", headers=headers)
    assert resp.status_code == 400
    assert seeded_client.post("/api/review/nope/approve",
                              headers=headers).status_code == 404


def test_model_info_and_status(seeded_client, user_token):
    headers = auth_headers(user_token)
    info = seeded_client.get("/api/model/info", headers=headers)
    assert info.status_code == 200
    assert info.json()["threshold"] == pytest.approx(0.78)
    status = seeded_client.get("/api/model/status", headers=headers)
    assert status.status_code == 200
    assert "running" in status.json()


def test_model_history_admin_only(seeded_client, admin_token, user_token):
    assert seeded_client.get(
        "/api/model/history",
        headers=auth_headers(user_token)).status_code in (401, 403)
    resp = seeded_client.get("/api/model/history",
                             headers=auth_headers(admin_token))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_train_trigger_admin_only_no_side_effects(seeded_client, user_token):
    # Unauthenticated / non-admin never reach the background task.
    assert seeded_client.post("/api/model/train").status_code in (401, 403)
    assert seeded_client.post(
        "/api/model/train",
        headers=auth_headers(user_token)).status_code in (401, 403)


def test_train_trigger_admin_starts_background(seeded_client, admin_token):
    import importlib

    mr = importlib.import_module("backend.routers.model_router")

    with patch.object(mr, "_run_training") as mocked:
        resp = seeded_client.post("/api/model/train",
                                  headers=auth_headers(admin_token))
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True
        # TestClient executes BackgroundTasks inline: the mock ran INSTEAD of
        # the real subprocess training, so no model.pkl overwrite occurs.
        mocked.assert_called_once()
        assert mocked.call_args.args[1] == "admin"
    # Second call while flagged running -> 409 (flag restored afterwards).
    mr._training_status["running"] = True
    try:
        conflict = seeded_client.post("/api/model/train",
                                      headers=auth_headers(admin_token))
        assert conflict.status_code == 409
    finally:
        mr._training_status["running"] = False


def test_rate_limit_config_wired():
    from backend.rate_limit import limiter
    from backend.main import app
    from config.settings import settings

    assert app.state.limiter is limiter
    assert settings.RATE_LIMIT_PREDICT == "60/minute"
    assert settings.RATE_LIMIT_TRAIN == "3/hour"
    # Per-route limits are applied via the shared instance (no second limiter).
    import importlib

    import backend.rate_limit as rl

    transaction_mod = importlib.import_module("backend.routers.transaction_router")
    model_mod = importlib.import_module("backend.routers.model_router")
    simulate_mod = importlib.import_module("backend.routers.simulate_router")
    assert transaction_mod.limiter is rl.limiter
    assert model_mod.limiter is rl.limiter
    assert simulate_mod.limiter is rl.limiter
