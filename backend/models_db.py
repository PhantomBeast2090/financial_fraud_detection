
"""
backend/models_db.py
SQLAlchemy ORM models for the fraud-detection platform.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


# ── Users (auth) ─────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=False)
    hashed_password = Column(String(256), nullable=False)
    role = Column(String(16), nullable=False, default="user")  # "admin" | "user"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)

    __table_args__ = (CheckConstraint("role IN ('admin', 'user')", name="ck_user_role"),)


# ── Transactions ─────────────────────────────────────────────────────────────
class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String(36), unique=True, nullable=False, index=True)

    # Raw fields
    account_id = Column(Integer, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    location = Column(String(64), nullable=False)
    transaction_type = Column(String(16), nullable=False)
    time_of_day = Column(Integer, nullable=False)
    distance_from_home = Column(Float, nullable=False, default=0.0)
    device_trust_score = Column(Float, default=75.0)
    failed_attempts_24h = Column(Integer, default=0)
    txn_velocity_1h = Column(Integer, default=1)
    merchant_risk_score = Column(Float, default=25.0)
    is_international = Column(Integer, default=0)
    card_present = Column(Integer, default=1)

    # ML result
    fraud_probability = Column(Float, nullable=True)
    predicted_label = Column(String(16), nullable=True)  # "Fraud" | "Legitimate"
    risk_level = Column(String(8), nullable=True)         # "High" | "Medium" | "Low"
    model_version = Column(String(32), nullable=True)
    alert_reasons = Column(Text, nullable=True)           # JSON string

    # Status
    status = Column(String(16), default="APPROVED")       # "APPROVED" | "BLOCKED" | "REVIEW"
    created_at = Column(DateTime, default=_utcnow)

    # Relationships
    alerts = relationship("FraudAlert", back_populates="transaction", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_txn_amount_positive"),
        CheckConstraint("time_of_day BETWEEN 0 AND 23", name="ck_txn_time"),
        CheckConstraint("status IN ('APPROVED', 'BLOCKED', 'REVIEW')", name="ck_txn_status"),
    )


# ── Fraud Alerts ──────────────────────────────────────────────────────────────
class FraudAlert(Base):
    __tablename__ = "fraud_alerts"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String(36), ForeignKey("transactions.transaction_id"), nullable=False)
    risk_level = Column(String(8), nullable=False, default="Low")
    reason = Column(Text, nullable=False)
    is_resolved = Column(Boolean, default=False)
    resolved_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    resolved_at = Column(DateTime, nullable=True)

    transaction = relationship("Transaction", back_populates="alerts")

    __table_args__ = (CheckConstraint("risk_level IN ('Low', 'Medium', 'High')", name="ck_alert_risk"),)


# ── Model Registry ────────────────────────────────────────────────────────────
class ModelRun(Base):
    __tablename__ = "model_runs"

    id = Column(Integer, primary_key=True)
    model_name = Column(String(64), nullable=False)
    model_version = Column(String(32), nullable=False)
    accuracy = Column(Float, nullable=True)
    precision = Column(Float, nullable=True)
    recall = Column(Float, nullable=True)
    f1_score = Column(Float, nullable=True)
    roc_auc = Column(Float, nullable=True)
    threshold = Column(Float, nullable=True)
    training_rows = Column(Integer, nullable=True)
    metrics_json = Column(Text, nullable=True)   # full JSON blob
    trained_by = Column(String(64), nullable=True)
    trained_at = Column(DateTime, default=_utcnow)
