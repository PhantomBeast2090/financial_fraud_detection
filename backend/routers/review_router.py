"""
backend/routers/review_router.py
Bank-staff review queue: list flagged transactions, approve or reject them.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models_db import FraudAlert, Transaction, User

router = APIRouter(prefix="/api/review", tags=["Review Queue"])


@router.get("/queue")
def get_review_queue(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns all BLOCKED transactions that haven't been manually reviewed yet.
    Bank staff use this to decide whether to approve or permanently reject.
    """
    txns = (
        db.query(Transaction)
        .filter(Transaction.status == "BLOCKED")
        .order_by(desc(Transaction.created_at))
        .limit(limit)
        .all()
    )
    return [_txn_to_dict(t) for t in txns]


@router.post("/{transaction_id}/approve")
def approve_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Bank staff manually approves a flagged transaction.
    Status changes BLOCKED → APPROVED; alert is marked resolved.
    """
    txn = _get_blocked(transaction_id, db)
    txn.status = "APPROVED"
    _resolve_alerts(transaction_id, current_user.username, db)
    db.commit()
    return {
        "success": True,
        "message": f"Transaction {transaction_id} approved by {current_user.username}",
        "new_status": "APPROVED",
    }


@router.post("/{transaction_id}/reject")
def reject_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Bank staff permanently rejects / cancels a flagged transaction.
    Status changes BLOCKED → CANCELLED (stored as REVIEW with rejection note).
    """
    txn = _get_blocked(transaction_id, db)
    txn.status = "REVIEW"           # repurpose REVIEW as "manually rejected"
    _resolve_alerts(transaction_id, current_user.username, db)
    db.commit()
    return {
        "success": True,
        "message": f"Transaction {transaction_id} rejected by {current_user.username}",
        "new_status": "REJECTED",
    }


# ── helpers ───────────────────────────────────────────────────────────────────
def _get_blocked(transaction_id: str, db: Session) -> Transaction:
    txn = db.query(Transaction).filter(Transaction.transaction_id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.status not in ("BLOCKED",):
        raise HTTPException(status_code=400, detail=f"Transaction is already {txn.status}")
    return txn


def _resolve_alerts(transaction_id: str, username: str, db: Session):
    alerts = db.query(FraudAlert).filter(
        FraudAlert.transaction_id == transaction_id,
        FraudAlert.is_resolved.is_(False),
    ).all()
    for a in alerts:
        a.is_resolved = True
        a.resolved_by = username
        a.resolved_at = datetime.now(timezone.utc)


def _txn_to_dict(t: Transaction) -> dict:
    import json as _json
    try:
        reasons = _json.loads(t.alert_reasons or "[]")
    except Exception:
        reasons = []
    return {
        "id": t.id,
        "transaction_id": t.transaction_id,
        "account_id": t.account_id,
        "amount": t.amount,
        "location": t.location,
        "transaction_type": t.transaction_type,
        "time_of_day": t.time_of_day,
        "distance_from_home": t.distance_from_home,
        "device_trust_score": t.device_trust_score,
        "fraud_probability": round(t.fraud_probability or 0, 4),
        "predicted_label": t.predicted_label,
        "risk_level": t.risk_level,
        "reasons": reasons,
        "status": t.status,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
