"""
backend/routers/transaction_router.py
CRUD + prediction endpoints for transactions.
"""
import json
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.model import predict_fraud
from backend.models_db import FraudAlert, Transaction, User
from backend.schemas import PredictionOut, TransactionIn, TransactionOut

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])


@router.post("/predict", response_model=PredictionOut, status_code=201)
def create_and_predict(
    body: TransactionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Submit a transaction for ML fraud analysis.
    Persists the transaction + prediction + optional alert atomically.
    """
    payload = body.model_dump()
    result = predict_fraud(payload)

    txn_id = str(uuid.uuid4())
    status_val = "BLOCKED" if result["label"] == "Fraud" else "APPROVED"

    txn = Transaction(
        transaction_id=txn_id,
        account_id=body.account_id,
        amount=body.amount,
        location=body.location,
        transaction_type=body.transaction_type,
        time_of_day=body.time_of_day,
        distance_from_home=body.distance_from_home,
        device_trust_score=body.device_trust_score,
        failed_attempts_24h=body.failed_attempts_24h,
        txn_velocity_1h=body.txn_velocity_1h,
        merchant_risk_score=body.merchant_risk_score,
        is_international=body.is_international,
        card_present=body.card_present,
        fraud_probability=result["probability"],
        predicted_label=result["label"],
        risk_level=result["risk_level"],
        model_version=result["model_version"],
        alert_reasons=json.dumps(result["reasons"]),
        status=status_val,
    )
    db.add(txn)
    db.flush()

    # Create alert if fraud or medium+ risk
    if result["label"] == "Fraud" or result["risk_level"] != "Low":
        alert = FraudAlert(
            transaction_id=txn_id,
            risk_level=result["risk_level"],
            reason="; ".join(result["reasons"]),
        )
        db.add(alert)

    db.commit()

    return PredictionOut(
        transaction_id=txn_id,
        fraud_probability=round(result["probability"], 4),
        label=result["label"],
        risk_level=result["risk_level"],
        model_version=result["model_version"],
        reasons=result["reasons"],
        status=status_val,
    )


@router.get("/", response_model=List[TransactionOut])
def list_transactions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    label: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return paginated transaction history, optionally filtered by label."""
    q = db.query(Transaction)
    if label:
        q = q.filter(Transaction.predicted_label == label)
    return q.order_by(desc(Transaction.created_at)).offset(offset).limit(limit).all()


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a single transaction by its UUID."""
    txn = db.query(Transaction).filter(Transaction.transaction_id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a transaction (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    txn = db.query(Transaction).filter(Transaction.transaction_id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(txn)
    db.commit()
