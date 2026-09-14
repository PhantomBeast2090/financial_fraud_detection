"""
backend/routers/simulate_router.py
Real-time transaction simulation — generates random synthetic transactions,
runs ML fraud analysis, and streams them via Server-Sent Events (SSE).
"""
import asyncio
import json
import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from backend.auth import get_current_user
from backend.database import SessionLocal
from backend.model import predict_fraud
from backend.models_db import FraudAlert, Transaction, User
from backend.rate_limit import limiter
from backend.ml_features import LOCATION_OPTIONS, TRANSACTION_TYPE_OPTIONS
from config.settings import settings

router = APIRouter(prefix="/api/simulate", tags=["Simulator"])

# ── Simulator state ────────────────────────────────────────────────────────────
_sim_running = False

LOCATION_OPTIONS_LIST = list(LOCATION_OPTIONS)
TXN_TYPES = list(TRANSACTION_TYPE_OPTIONS)


def _random_transaction() -> dict:
    """Generate a plausible synthetic transaction with occasional fraud patterns."""
    rng = random.Random()

    mode = rng.choices(["regular", "travel", "risky"], weights=[70, 15, 15])[0]
    txn_type = rng.choice(TXN_TYPES)
    location = rng.choice(LOCATION_OPTIONS_LIST)

    if mode == "regular":
        amount = round(rng.lognormvariate(7.5, 0.7), 2)
        time_of_day = int(rng.gauss(14, 4)) % 24
        distance = round(abs(rng.gauss(15, 20)), 2)
        device_trust = round(min(100, max(0, rng.gauss(82, 10))), 2)
        failed = rng.choices([0, 1, 2], weights=[74, 20, 6])[0]
        velocity = rng.choices([1, 2, 3, 4], weights=[40, 32, 20, 8])[0]
        merchant_risk = round(min(100, max(0, rng.gauss(24, 14))), 2)
        is_intl = 1 if rng.random() < 0.015 else 0
        card_present = 1 if txn_type in {"ATM", "POS"} else 0
    elif mode == "travel":
        amount = round(rng.lognormvariate(8.0, 0.8) * rng.uniform(1.1, 1.9), 2)
        time_of_day = int(rng.gauss(16, 6)) % 24
        distance = round(abs(rng.gauss(200, 120)), 2)
        device_trust = round(min(100, max(0, rng.gauss(68, 16))), 2)
        failed = rng.choices([0, 1, 2, 3], weights=[48, 26, 17, 9])[0]
        velocity = rng.choices([1, 2, 3, 4, 5], weights=[24, 24, 24, 18, 10])[0]
        merchant_risk = round(min(100, max(0, rng.gauss(42, 18))), 2)
        is_intl = 1 if rng.random() < 0.22 else 0
        card_present = 1 if rng.random() < 0.5 else 0
    else:  # risky
        amount = round(rng.lognormvariate(9.0, 1.0) * rng.uniform(1.6, 4.4), 2)
        time_of_day = rng.choice([0, 1, 2, 3, 4, 22, 23])
        distance = round(abs(rng.gauss(400, 200)), 2)
        device_trust = round(min(100, max(0, rng.gauss(34, 18))), 2)
        failed = rng.choices([1, 2, 3, 4, 5, 6], weights=[10, 14, 20, 24, 18, 14])[0]
        velocity = rng.choices([3, 4, 5, 6, 7, 8], weights=[10, 14, 20, 22, 20, 14])[0]
        merchant_risk = round(min(100, max(0, rng.gauss(74, 17))), 2)
        is_intl = 1 if rng.random() < 0.48 else 0
        card_present = 0

    amount = min(max(round(amount, 2), 80.0), 250_000.0)
    distance = min(max(round(distance, 2), 0.0), 2500.0)

    return {
        "account_id": rng.randint(1, 1400),
        "amount": amount,
        "location": location,
        "transaction_type": txn_type,
        "time_of_day": max(0, min(23, time_of_day)),
        "distance_from_home": distance,
        "device_trust_score": device_trust,
        "failed_attempts_24h": min(failed, 20),
        "txn_velocity_1h": min(max(velocity, 1), 25),
        "merchant_risk_score": merchant_risk,
        "is_international": is_intl,
        "card_present": card_present,
    }


def _process_and_store(payload: dict) -> dict:
    """Run ML prediction and persist to DB. Returns the enriched record."""
    result = predict_fraud(payload)
    txn_id = str(uuid.uuid4())
    status_val = "BLOCKED" if result["label"] == "Fraud" else "APPROVED"

    with SessionLocal() as db:
        txn = Transaction(
            transaction_id=txn_id,
            account_id=payload["account_id"],
            amount=payload["amount"],
            location=payload["location"],
            transaction_type=payload["transaction_type"],
            time_of_day=payload["time_of_day"],
            distance_from_home=payload["distance_from_home"],
            device_trust_score=payload["device_trust_score"],
            failed_attempts_24h=payload["failed_attempts_24h"],
            txn_velocity_1h=payload["txn_velocity_1h"],
            merchant_risk_score=payload["merchant_risk_score"],
            is_international=payload["is_international"],
            card_present=payload["card_present"],
            fraud_probability=result["probability"],
            predicted_label=result["label"],
            risk_level=result["risk_level"],
            model_version=result["model_version"],
            alert_reasons=json.dumps(result["reasons"]),
            status=status_val,
        )
        db.add(txn)
        db.flush()

        if result["label"] == "Fraud" or result["risk_level"] != "Low":
            db.add(FraudAlert(
                transaction_id=txn_id,
                risk_level=result["risk_level"],
                reason="; ".join(result["reasons"]),
            ))
        db.commit()

    return {
        "transaction_id": txn_id,
        "account_id": payload["account_id"],
        "amount": payload["amount"],
        "location": payload["location"],
        "transaction_type": payload["transaction_type"],
        "time_of_day": payload["time_of_day"],
        "fraud_probability": round(result["probability"], 4),
        "label": result["label"],
        "risk_level": result["risk_level"],
        "reasons": result["reasons"],
        "explanation": result.get("explanation"),
        "status": status_val,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/one")
@limiter.limit(settings.RATE_LIMIT_PREDICT)
def simulate_one(request: Request, current_user: User = Depends(get_current_user)):
    """Generate, analyse, and store one random transaction immediately."""
    payload = _random_transaction()
    return _process_and_store(payload)


@router.get("/stream")
async def stream_transactions(token: str = ""):
    """
    Server-Sent Events stream. Authenticates via ?token= query param
    (EventSource API does not support custom headers).
    Emits a new random transaction every 3 seconds.
    """
    # Validate token manually
    from backend.auth import decode_token
    from backend.database import SessionLocal
    from backend.models_db import User as UserModel
    try:
        payload = decode_token(token)
        username = payload.get("sub")
        with SessionLocal() as db:
            user = db.query(UserModel).filter(UserModel.username == username).first()
            if not user or not user.is_active:
                raise ValueError("Invalid user")
    except Exception:
        from fastapi.responses import Response
        return Response("Unauthorized", status_code=401)
    async def event_generator():
        # send a keep-alive comment immediately so the browser opens the stream
        yield ": keep-alive\n\n"
        loop = asyncio.get_event_loop()
        while True:
            try:
                payload = _random_transaction()
                # Run blocking DB/ML work in thread pool so we don't block the event loop
                record = await loop.run_in_executor(None, _process_and_store, payload)
                data = json.dumps(record)
                yield f"data: {data}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
