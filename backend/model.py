from pathlib import Path

import joblib

try:
    from backend.ml_features import DEFAULT_TRANSACTION, build_feature_frame, normalize_transaction_payload
except ModuleNotFoundError:
    from ml_features import DEFAULT_TRANSACTION, build_feature_frame, normalize_transaction_payload

MODEL_PATH = Path(__file__).with_name("model.pkl")

print("Loading fraud detection artifact ...")
_raw = joblib.load(MODEL_PATH)

# The new train_model.py saves {"model": pipeline, "metadata": {...}}
# Older pkl files may be a bare sklearn pipeline/estimator.
if isinstance(_raw, dict) and "model" in _raw:
    model = _raw["model"]
    metadata = _raw.get("metadata", {})
else:
    model = _raw
    metadata = {}


def predict_fraud(transaction_payload):
    transaction = normalize_transaction_payload(transaction_payload)
    feature_frame = build_feature_frame([transaction])
    fraud_probability = float(model.predict_proba(feature_frame)[0][1])
    threshold = float(metadata.get("threshold", 0.5))

    predicted_label = "Fraud" if fraud_probability >= threshold else "Legitimate"
    risk_level = _risk_level(fraud_probability)

    return {
        "probability": fraud_probability,
        "threshold": threshold,
        "label": predicted_label,
        "risk_level": risk_level,
        "model_version": metadata.get("model_version", "FraudModel-v2"),
        "reasons": _derive_reasons(transaction, fraud_probability),
        "transaction": transaction,
    }


def get_model_metadata():
    return {
        "model_name": metadata.get("model_name", "Unknown"),
        "model_version": metadata.get("model_version", "FraudModel-v2"),
        "threshold": float(metadata.get("threshold", 0.5)),
        "training_rows": int(metadata.get("training_rows", 0)),
        "test_metrics": metadata.get("test_metrics", {}),
    }


def get_default_transaction():
    return dict(DEFAULT_TRANSACTION)


def _risk_level(probability):
    if probability >= 0.85:
        return "High"
    if probability >= 0.60:
        return "Medium"
    return "Low"


def _derive_reasons(transaction, probability):
    reasons = []

    if transaction["amount"] >= 30_000:
        reasons.append("Large transfer amount")
    if transaction["distance_from_home"] >= 150:
        reasons.append("Far from usual location")
    if transaction["device_trust_score"] <= 35:
        reasons.append("Low device trust")
    if transaction["failed_attempts_24h"] >= 3:
        reasons.append("Multiple failed attempts")
    if transaction["txn_velocity_1h"] >= 6:
        reasons.append("Unusual one-hour transaction burst")
    if transaction["merchant_risk_score"] >= 70:
        reasons.append("High-risk merchant profile")
    if transaction["is_international"]:
        reasons.append("Cross-border transaction")
    if not transaction["card_present"] and transaction["amount"] >= 18_000:
        reasons.append("Card-not-present high-value payment")
    if transaction["time_of_day"] <= 5 or transaction["time_of_day"] >= 23:
        reasons.append("Odd-hour activity")

    if not reasons:
        if probability < 0.35:
            reasons.append("Signals match trusted customer behavior")
        else:
            reasons.append("Mixed signals detected across behavior profile")

    return reasons[:3]
