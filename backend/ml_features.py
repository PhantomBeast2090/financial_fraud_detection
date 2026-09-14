import numpy as np
import pandas as pd

LOCATION_OPTIONS = [
    "Chennai",
    "Mumbai",
    "Delhi",
    "Bangalore",
    "Hyderabad",
    "Pune",
]

TRANSACTION_TYPE_OPTIONS = [
    "Online",
    "ATM",
    "POS",
    "UPI",
    "NEFT",
    "IMPS",
]

DEFAULT_TRANSACTION = {
    "account_id": 1,
    "amount": 2500.0,
    "location": "Chennai",
    "transaction_type": "Online",
    "time_of_day": 14,
    "distance_from_home": 12.0,
    "device_trust_score": 78.0,
    "failed_attempts_24h": 0,
    "txn_velocity_1h": 2,
    "merchant_risk_score": 24.0,
    "is_international": 0,
    "card_present": 0,
}

RAW_FEATURE_COLUMNS = [
    "amount",
    "location",
    "transaction_type",
    "time_of_day",
    "distance_from_home",
    "device_trust_score",
    "failed_attempts_24h",
    "txn_velocity_1h",
    "merchant_risk_score",
    "is_international",
    "card_present",
]

DERIVED_FEATURE_COLUMNS = [
    "amount_log",
    "night_risk",
    "distance_amount_pressure",
    "trust_gap",
    "velocity_pressure",
    "cross_border_card_not_present",
]

CATEGORICAL_COLUMNS = ["location", "transaction_type"]

MODEL_FEATURE_COLUMNS = RAW_FEATURE_COLUMNS + DERIVED_FEATURE_COLUMNS


def normalize_transaction_payload(payload):
    payload = payload or {}
    normalized = {
        "account_id": _safe_int(payload.get("account_id"), DEFAULT_TRANSACTION["account_id"], 1, 10_000_000),
        "amount": _safe_float(payload.get("amount"), DEFAULT_TRANSACTION["amount"], 1.0, 500_000.0),
        "location": _safe_text(payload.get("location"), DEFAULT_TRANSACTION["location"]),
        "transaction_type": _safe_text(
            payload.get("transaction_type"),
            DEFAULT_TRANSACTION["transaction_type"],
        ),
        "time_of_day": _safe_int(payload.get("time_of_day"), DEFAULT_TRANSACTION["time_of_day"], 0, 23),
        "distance_from_home": _safe_float(
            payload.get("distance_from_home"),
            DEFAULT_TRANSACTION["distance_from_home"],
            0.0,
            5_000.0,
        ),
        "device_trust_score": _safe_float(
            payload.get("device_trust_score"),
            DEFAULT_TRANSACTION["device_trust_score"],
            0.0,
            100.0,
        ),
        "failed_attempts_24h": _safe_int(
            payload.get("failed_attempts_24h"),
            DEFAULT_TRANSACTION["failed_attempts_24h"],
            0,
            20,
        ),
        "txn_velocity_1h": _safe_int(
            payload.get("txn_velocity_1h"),
            DEFAULT_TRANSACTION["txn_velocity_1h"],
            1,
            25,
        ),
        "merchant_risk_score": _safe_float(
            payload.get("merchant_risk_score"),
            DEFAULT_TRANSACTION["merchant_risk_score"],
            0.0,
            100.0,
        ),
        "is_international": _safe_bool(payload.get("is_international"), DEFAULT_TRANSACTION["is_international"]),
        "card_present": _safe_bool(payload.get("card_present"), DEFAULT_TRANSACTION["card_present"]),
    }
    return normalized


def build_feature_frame(records):
    df = pd.DataFrame(records).copy()

    for column in RAW_FEATURE_COLUMNS:
        if column not in df.columns:
            df[column] = DEFAULT_TRANSACTION[column]

    for column in CATEGORICAL_COLUMNS:
        df[column] = (
            df[column]
            .fillna(DEFAULT_TRANSACTION[column])
            .astype(str)
            .str.strip()
            .replace("", DEFAULT_TRANSACTION[column])
        )

    integer_columns = ["time_of_day", "failed_attempts_24h", "txn_velocity_1h", "is_international", "card_present"]
    float_columns = [
        "amount",
        "distance_from_home",
        "device_trust_score",
        "merchant_risk_score",
    ]

    for column in integer_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(DEFAULT_TRANSACTION[column]).round().astype(int)

    for column in float_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(DEFAULT_TRANSACTION[column]).astype(float)

    df["time_of_day"] = df["time_of_day"].clip(0, 23)
    df["failed_attempts_24h"] = df["failed_attempts_24h"].clip(0, 20)
    df["txn_velocity_1h"] = df["txn_velocity_1h"].clip(1, 25)
    df["amount"] = df["amount"].clip(1.0, 500_000.0)
    df["distance_from_home"] = df["distance_from_home"].clip(0.0, 5_000.0)
    df["device_trust_score"] = df["device_trust_score"].clip(0.0, 100.0)
    df["merchant_risk_score"] = df["merchant_risk_score"].clip(0.0, 100.0)
    df["is_international"] = df["is_international"].clip(0, 1)
    df["card_present"] = df["card_present"].clip(0, 1)

    df["amount_log"] = np.log1p(df["amount"])
    df["night_risk"] = ((df["time_of_day"] <= 5) | (df["time_of_day"] >= 23)).astype(int)
    df["distance_amount_pressure"] = np.log1p(df["distance_from_home"]) * np.log1p(df["amount"])
    df["trust_gap"] = 100.0 - df["device_trust_score"]
    df["velocity_pressure"] = df["txn_velocity_1h"] * (1 + df["failed_attempts_24h"])
    df["cross_border_card_not_present"] = df["is_international"] * (1 - df["card_present"])

    return df[MODEL_FEATURE_COLUMNS]


def _safe_float(value, default, minimum, maximum):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _safe_int(value, default, minimum, maximum):
    try:
        value = int(float(value))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _safe_bool(value, default):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value > 0)
    if isinstance(value, str):
        return int(value.strip().lower() in {"1", "true", "yes", "on"})
    return int(default)


def _safe_text(value, default):
    if value is None:
        return default
    s = str(value).strip()
    return s if s else default
