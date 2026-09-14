"""
backend/routers/analytics_router.py
Dashboard stats, charts data, and CSV export endpoints.
"""
import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models_db import FraudAlert, ModelRun, Transaction, User
from backend.schemas import DashboardStats

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("/dashboard", response_model=DashboardStats)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregate KPIs + chart data for the main dashboard."""
    total_txns = db.query(Transaction).count()
    total_fraud = db.query(Transaction).filter(Transaction.predicted_label == "Fraud").count()
    total_legit = total_txns - total_fraud
    total_alerts = db.query(FraudAlert).count()
    high_risk = db.query(FraudAlert).filter(FraudAlert.risk_level == "High").count()

    # Total monetary value approved vs blocked
    amount_approved = db.query(func.sum(Transaction.amount)).filter(
        Transaction.status == "APPROVED"
    ).scalar() or 0.0
    amount_blocked = db.query(func.sum(Transaction.amount)).filter(
        Transaction.status == "BLOCKED"
    ).scalar() or 0.0

    # Recent 20 transactions
    recent = (
        db.query(Transaction)
        .order_by(Transaction.created_at.desc())
        .limit(20)
        .all()
    )

    # Fraud by transaction type
    by_type = (
        db.query(Transaction.transaction_type, func.count().label("count"))
        .filter(Transaction.predicted_label == "Fraud")
        .group_by(Transaction.transaction_type)
        .all()
    )

    # Fraud by location
    by_location = (
        db.query(Transaction.location, func.count().label("count"))
        .filter(Transaction.predicted_label == "Fraud")
        .group_by(Transaction.location)
        .all()
    )

    # Hourly trend (last 24h – all transactions, fraud overlay)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    hourly_rows = (
        db.query(
            func.strftime("%H", Transaction.created_at).label("hour"),
            Transaction.predicted_label,
            func.count().label("count"),
        )
        .filter(Transaction.created_at >= cutoff)
        .group_by("hour", Transaction.predicted_label)
        .all()
    )

    hourly_map: dict = defaultdict(lambda: {"hour": None, "total": 0, "fraud": 0})
    for hr, label, cnt in hourly_rows:
        key = int(hr) if hr else 0
        hourly_map[key]["hour"] = key
        hourly_map[key]["total"] += cnt
        if label == "Fraud":
            hourly_map[key]["fraud"] += cnt
    hourly_trend = sorted(hourly_map.values(), key=lambda x: x["hour"])

    # Daily amounts – last 7 days
    daily_rows = (
        db.query(
            func.strftime("%Y-%m-%d", Transaction.created_at).label("day"),
            func.sum(Transaction.amount).label("total"),
            func.sum(Transaction.fraud_probability).label("risk_sum"),
        )
        .filter(Transaction.created_at >= datetime.now(timezone.utc) - timedelta(days=7))
        .group_by("day")
        .order_by("day")
        .all()
    )
    daily_amounts = [
        {"day": row.day, "total": round(row.total or 0, 2), "risk_sum": round(row.risk_sum or 0, 2)}
        for row in daily_rows
    ]

    return DashboardStats(
        total_transactions=total_txns,
        total_fraud=total_fraud,
        total_legitimate=total_legit,
        fraud_rate=round(total_fraud / total_txns * 100, 2) if total_txns else 0.0,
        total_alerts=total_alerts,
        high_risk_alerts=high_risk,
        amount_approved=round(float(amount_approved), 2),
        amount_blocked=round(float(amount_blocked), 2),
        recent_transactions=[
            {
                "id": t.id,
                "transaction_id": t.transaction_id,
                "amount": t.amount,
                "location": t.location,
                "transaction_type": t.transaction_type,
                "fraud_probability": round(t.fraud_probability or 0, 4),
                "label": t.predicted_label,
                "risk_level": t.risk_level,
                "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in recent
        ],
        fraud_by_type=[{"type": r[0], "count": r[1]} for r in by_type],
        fraud_by_location=[{"location": r[0], "count": r[1]} for r in by_location],
        hourly_trend=hourly_trend,
        daily_amounts=daily_amounts,
    )


@router.get("/alerts")
def get_alerts(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return latest fraud alerts."""
    alerts = (
        db.query(FraudAlert)
        .order_by(FraudAlert.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": a.id,
            "transaction_id": a.transaction_id,
            "risk_level": a.risk_level,
            "reason": a.reason,
            "is_resolved": a.is_resolved,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark an alert as resolved (admin only)."""
    from fastapi import HTTPException
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    alert = db.query(FraudAlert).filter(FraudAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_resolved = True
    alert.resolved_by = current_user.username
    alert.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"success": True, "message": "Alert resolved"}


@router.get("/model-metrics")
def get_model_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the most recent model training run metrics."""
    latest = db.query(ModelRun).order_by(ModelRun.trained_at.desc()).first()
    if not latest:
        # Fall back to on-disk metrics
        import json
        from config.settings import settings
        if settings.METRICS_PATH.exists():
            raw = json.loads(settings.METRICS_PATH.read_text())
            tm = raw.get("test_metrics", {})
            return {
                "model_name": raw.get("model_name", "Unknown"),
                "model_version": raw.get("model_version", "v2"),
                "accuracy": tm.get("accuracy"),
                "precision": tm.get("precision"),
                "recall": tm.get("recall"),
                "f1_score": tm.get("f1"),
                "roc_auc": tm.get("roc_auc"),
                "threshold": raw.get("threshold"),
                "training_rows": raw.get("training_rows"),
                "trained_at": raw.get("trained_at"),
                "leaderboard": raw.get("validation_leaderboard"),
            }
        return {"error": "No model trained yet"}

    import json
    leaderboard = None
    if latest.metrics_json:
        try:
            full = json.loads(latest.metrics_json)
            leaderboard = full.get("validation_leaderboard")
        except Exception:
            pass

    return {
        "model_name": latest.model_name,
        "model_version": latest.model_version,
        "accuracy": latest.accuracy,
        "precision": latest.precision,
        "recall": latest.recall,
        "f1_score": latest.f1_score,
        "roc_auc": latest.roc_auc,
        "threshold": latest.threshold,
        "training_rows": latest.training_rows,
        "trained_at": latest.trained_at.isoformat() if latest.trained_at else None,
        "leaderboard": leaderboard,
    }


@router.get("/export/csv")
def export_transactions_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stream all transactions as a downloadable CSV report."""
    rows = db.query(Transaction).order_by(Transaction.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "transaction_id", "account_id", "amount", "location", "transaction_type",
        "time_of_day", "distance_from_home", "device_trust_score",
        "failed_attempts_24h", "txn_velocity_1h", "merchant_risk_score",
        "is_international", "card_present",
        "fraud_probability", "predicted_label", "risk_level", "status", "created_at"
    ])
    for t in rows:
        writer.writerow([
            t.transaction_id, t.account_id, t.amount, t.location, t.transaction_type,
            t.time_of_day, t.distance_from_home, t.device_trust_score,
            t.failed_attempts_24h, t.txn_velocity_1h, t.merchant_risk_score,
            t.is_international, t.card_present,
            round(t.fraud_probability or 0, 4), t.predicted_label, t.risk_level,
            t.status, t.created_at
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=fraud_report.csv"},
    )
