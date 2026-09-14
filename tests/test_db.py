"""
tests/test_db.py — persistence: tables, transactions, predictions, alerts (1E).
"""
import json

from backend.database import Base
from backend.models_db import FraudAlert, ModelRun, Transaction, User


def test_tables_created(db_engine):
    assert set(Base.metadata.tables) >= {"users", "transactions", "fraud_alerts", "model_runs"}


def test_user_persistence(db_session):
    from backend.auth import hash_password

    db_session.add(User(username="bob", email="bob@example.com",
                        hashed_password=hash_password("pw12345"), role="user"))
    db_session.commit()
    fetched = db_session.query(User).filter(User.username == "bob").one()
    assert fetched.email == "bob@example.com"
    assert fetched.is_active in (True, 1)


def _txn(**overrides):
    base = {
        "transaction_id": "txn-1",
        "account_id": 42,
        "amount": 5000.0,
        "location": "Mumbai",
        "transaction_type": "UPI",
        "time_of_day": 10,
        "distance_from_home": 3.0,
        "fraud_probability": 0.12,
        "predicted_label": "Legitimate",
        "risk_level": "Low",
        "model_version": "test-v1",
        "alert_reasons": json.dumps(["ok"]),
        "status": "APPROVED",
    }
    base.update(overrides)
    return Transaction(**base)


def test_transaction_persistence(db_session):
    db_session.add(_txn())
    db_session.commit()
    fetched = db_session.query(Transaction).filter(
        Transaction.transaction_id == "txn-1").one()
    assert fetched.amount == 5000.0
    assert fetched.predicted_label == "Legitimate"
    assert fetched.status == "APPROVED"


def test_prediction_fields_roundtrip(db_session):
    db_session.add(_txn(transaction_id="txn-2", fraud_probability=0.991,
                        predicted_label="Fraud", risk_level="High", status="BLOCKED"))
    db_session.commit()
    fetched = db_session.query(Transaction).filter(
        Transaction.transaction_id == "txn-2").one()
    assert fetched.fraud_probability == 0.991
    assert fetched.predicted_label == "Fraud"


def test_alert_persistence_and_resolution(db_session):
    from datetime import datetime, timezone

    db_session.add(_txn(transaction_id="txn-3", status="BLOCKED"))
    db_session.add(FraudAlert(transaction_id="txn-3", risk_level="High",
                              reason="Large transfer amount"))
    db_session.commit()
    alert = db_session.query(FraudAlert).filter(
        FraudAlert.transaction_id == "txn-3").one()
    assert alert.is_resolved in (False, 0)
    alert.is_resolved = True
    alert.resolved_by = "admin"
    alert.resolved_at = datetime.now(timezone.utc)
    db_session.commit()
    assert db_session.query(FraudAlert).filter(FraudAlert.is_resolved.is_(True)).count() == 1


def test_review_status_transitions(db_session):
    db_session.add(_txn(transaction_id="txn-4", status="BLOCKED"))
    db_session.commit()
    txn = db_session.query(Transaction).filter(
        Transaction.transaction_id == "txn-4").one()
    txn.status = "APPROVED"  # approve path
    db_session.commit()
    assert txn.status == "APPROVED"
    txn.status = "REVIEW"  # reject path stores REVIEW
    db_session.commit()
    assert txn.status == "REVIEW"


def test_cascade_delete_removes_alerts(db_session):
    db_session.add(_txn(transaction_id="txn-5", status="BLOCKED"))
    db_session.add(FraudAlert(transaction_id="txn-5", risk_level="High", reason="x"))
    db_session.commit()
    txn = db_session.query(Transaction).filter(
        Transaction.transaction_id == "txn-5").one()
    db_session.delete(txn)
    db_session.commit()
    assert db_session.query(FraudAlert).filter(
        FraudAlert.transaction_id == "txn-5").count() == 0


def test_model_run_persistence(db_session):
    db_session.add(ModelRun(model_name="M", model_version="v1", accuracy=0.9,
                            threshold=0.5, training_rows=100,
                            metrics_json="{}", trained_by="admin"))
    db_session.commit()
    runs = db_session.query(ModelRun).all()
    assert len(runs) == 1 and runs[0].model_name == "M"


def test_query_filter_by_label(db_session):
    db_session.add(_txn(transaction_id="a", predicted_label="Fraud"))
    db_session.add(_txn(transaction_id="b", predicted_label="Legitimate"))
    db_session.commit()
    fraud = db_session.query(Transaction).filter(
        Transaction.predicted_label == "Fraud").all()
    assert [t.transaction_id for t in fraud] == ["a"]
