"""
backend/schemas.py
Pydantic v2 request/response schemas used by FastAPI routes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Auth ──────────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=6)
    role: str = Field(default="user", pattern="^(admin|user)$")


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Transactions ──────────────────────────────────────────────────────────────
class TransactionIn(BaseModel):
    account_id: int = Field(default=1, ge=1)
    amount: float = Field(..., gt=0, le=500_000)
    location: str = Field(default="Chennai")
    transaction_type: str = Field(default="Online")
    time_of_day: int = Field(default=14, ge=0, le=23)
    distance_from_home: float = Field(default=0.0, ge=0.0)
    device_trust_score: float = Field(default=75.0, ge=0.0, le=100.0)
    failed_attempts_24h: int = Field(default=0, ge=0, le=20)
    txn_velocity_1h: int = Field(default=1, ge=1, le=25)
    merchant_risk_score: float = Field(default=25.0, ge=0.0, le=100.0)
    is_international: int = Field(default=0, ge=0, le=1)
    card_present: int = Field(default=1, ge=0, le=1)

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: str) -> str:
        allowed = {"Chennai", "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Pune"}
        if v not in allowed:
            raise ValueError(f"location must be one of {allowed}")
        return v

    @field_validator("transaction_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"Online", "ATM", "POS", "UPI", "NEFT", "IMPS"}
        if v not in allowed:
            raise ValueError(f"transaction_type must be one of {allowed}")
        return v


class PredictionOut(BaseModel):
    transaction_id: str
    fraud_probability: float
    label: str
    risk_level: str
    model_version: str
    reasons: List[str]
    status: str


class TransactionOut(BaseModel):
    id: int
    transaction_id: str
    account_id: int
    amount: float
    location: str
    transaction_type: str
    time_of_day: int
    distance_from_home: float
    device_trust_score: float
    failed_attempts_24h: int
    txn_velocity_1h: int
    merchant_risk_score: float
    is_international: int
    card_present: int
    fraud_probability: Optional[float]
    predicted_label: Optional[str]
    risk_level: Optional[str]
    model_version: Optional[str]
    alert_reasons: Optional[str]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Analytics ─────────────────────────────────────────────────────────────────
class DashboardStats(BaseModel):
    total_transactions: int
    total_fraud: int
    total_legitimate: int
    fraud_rate: float
    total_alerts: int
    high_risk_alerts: int
    amount_approved: float = 0.0
    amount_blocked: float = 0.0
    recent_transactions: List[dict]
    fraud_by_type: List[dict]
    fraud_by_location: List[dict]
    hourly_trend: List[dict]
    daily_amounts: List[dict]


class ModelMetrics(BaseModel):
    model_name: str
    model_version: str
    accuracy: Optional[float]
    precision: Optional[float]
    recall: Optional[float]
    f1_score: Optional[float]
    roc_auc: Optional[float]
    threshold: Optional[float]
    training_rows: Optional[int]
    trained_at: Optional[datetime]
    leaderboard: Optional[List[Any]] = None


class TrainResponse(BaseModel):
    success: bool
    message: str
    model_name: str
    model_version: str
    test_metrics: dict


class AlertOut(BaseModel):
    id: int
    transaction_id: str
    risk_level: str
    reason: str
    is_resolved: bool
    created_at: datetime

    model_config = {"from_attributes": True}
