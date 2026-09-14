from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.ml_features import LOCATION_OPTIONS, TRANSACTION_TYPE_OPTIONS

RNG = np.random.default_rng(42)
SAMPLE_COUNT = 3200

LOCATION_WEIGHTS = np.array([0.18, 0.18, 0.17, 0.19, 0.16, 0.12])
TYPE_WEIGHTS = np.array([0.28, 0.10, 0.21, 0.18, 0.12, 0.11])


def _choose(options, weights):
    return options[RNG.choice(len(options), p=weights)]


def _clip(value, low, high):
    return max(low, min(high, value))


def _sigmoid(value):
    return 1.0 / (1.0 + np.exp(-value))


def _base_type_profile(transaction_type):
    profiles = {
        "ATM": (8.0, 0.55),
        "POS": (7.6, 0.70),
        "Online": (7.8, 0.85),
        "UPI": (7.2, 0.75),
        "NEFT": (8.9, 0.65),
        "IMPS": (8.6, 0.72),
    }
    return profiles.get(transaction_type, (7.8, 0.75))


def _generate_transaction(index):
    mode = RNG.choice(["regular", "travel", "risky"], p=[0.72, 0.14, 0.14])
    account_id = int(RNG.integers(1, 1401))
    location = _choose(LOCATION_OPTIONS, LOCATION_WEIGHTS)
    transaction_type = _choose(TRANSACTION_TYPE_OPTIONS, TYPE_WEIGHTS)

    amount_mu, amount_sigma = _base_type_profile(transaction_type)
    amount = float(RNG.lognormal(mean=amount_mu, sigma=amount_sigma))

    if mode == "regular":
        time_of_day = int(np.round(RNG.normal(14, 4)))
        distance = float(RNG.gamma(2.2, 10.0))
        device_trust = float(RNG.normal(82, 11))
        failed_attempts = int(RNG.choice([0, 1, 2], p=[0.74, 0.20, 0.06]))
        velocity = int(RNG.choice([1, 2, 3, 4], p=[0.40, 0.32, 0.20, 0.08]))
        merchant_risk = float(RNG.normal(24, 14))
        is_international = int(RNG.random() < 0.015)
    elif mode == "travel":
        amount *= float(RNG.uniform(1.1, 1.9))
        time_of_day = int(np.round(RNG.normal(16, 6)))
        distance = float(RNG.gamma(4.5, 35.0))
        device_trust = float(RNG.normal(68, 16))
        failed_attempts = int(RNG.choice([0, 1, 2, 3], p=[0.48, 0.26, 0.17, 0.09]))
        velocity = int(RNG.choice([1, 2, 3, 4, 5], p=[0.24, 0.24, 0.24, 0.18, 0.10]))
        merchant_risk = float(RNG.normal(42, 18))
        is_international = int(RNG.random() < 0.22)
    else:
        amount *= float(RNG.uniform(1.6, 4.4))
        time_of_day = int(RNG.choice([0, 1, 2, 3, 4, 5, 22, 23]))
        distance = float(RNG.gamma(4.2, 60.0))
        device_trust = float(RNG.normal(34, 18))
        failed_attempts = int(RNG.choice([1, 2, 3, 4, 5, 6, 7, 8], p=[0.10, 0.12, 0.16, 0.20, 0.16, 0.12, 0.08, 0.06]))
        velocity = int(RNG.choice([2, 3, 4, 5, 6, 7, 8, 9, 10, 12], p=[0.05, 0.08, 0.10, 0.14, 0.16, 0.15, 0.12, 0.08, 0.07, 0.05]))
        merchant_risk = float(RNG.normal(74, 17))
        is_international = int(RNG.random() < 0.48)

    if transaction_type in {"ATM", "POS"}:
        card_present = int(RNG.random() < 0.92)
    else:
        card_present = int(RNG.random() < 0.08)

    if mode == "risky" and transaction_type in {"Online", "IMPS", "NEFT"}:
        card_present = 0

    if RNG.random() < 0.04:
        amount *= float(RNG.uniform(2.4, 4.8))
    if RNG.random() < 0.03:
        device_trust -= float(RNG.uniform(25, 45))
    if RNG.random() < 0.025:
        failed_attempts += int(RNG.integers(2, 6))
        velocity += int(RNG.integers(2, 5))

    amount = round(_clip(amount, 80.0, 250_000.0), 2)
    time_of_day = int(_clip(time_of_day, 0, 23))
    distance = round(_clip(distance, 0.0, 2_500.0), 2)
    device_trust = round(_clip(device_trust, 0.0, 100.0), 2)
    failed_attempts = int(_clip(failed_attempts, 0, 20))
    velocity = int(_clip(velocity, 1, 25))
    merchant_risk = round(_clip(merchant_risk, 0.0, 100.0), 2)

    risk_logit = -5.2
    risk_logit += 0.55 if amount >= 12_000 else 0.0
    risk_logit += 0.80 if amount >= 28_000 else 0.0
    risk_logit += 0.45 if amount >= 60_000 else 0.0
    risk_logit += 0.85 if time_of_day <= 5 or time_of_day >= 23 else 0.0
    risk_logit += 0.90 if distance >= 120 else 0.0
    risk_logit += 0.75 if distance >= 350 else 0.0
    risk_logit += 1.20 if device_trust <= 35 else 0.0
    risk_logit += 0.60 if device_trust <= 55 else 0.0
    risk_logit += 0.45 * min(failed_attempts, 6)
    risk_logit += 0.22 * max(0, velocity - 2)
    risk_logit += 0.018 * max(0.0, merchant_risk - 40.0)
    risk_logit += 1.10 if is_international else 0.0
    risk_logit += 0.70 if not card_present and amount >= 18_000 else 0.0
    risk_logit += 1.30 if is_international and device_trust <= 40 else 0.0
    risk_logit += 1.00 if failed_attempts >= 4 and velocity >= 6 else 0.0
    risk_logit += 0.75 if transaction_type in {"IMPS", "NEFT"} and amount >= 20_000 else 0.0
    risk_logit += 0.40 if location in {"Delhi", "Mumbai"} else 0.0
    risk_logit -= 0.85 if card_present and device_trust >= 85 and distance <= 8 and merchant_risk <= 18 else 0.0
    risk_logit += float(RNG.normal(0, 0.55))

    fraud_probability = _sigmoid(risk_logit)
    is_fraud = int(RNG.random() < fraud_probability)

    if RNG.random() < 0.018:
        is_fraud = 1 - is_fraud

    return {
        "account_id": account_id,
        "amount": amount,
        "location": location,
        "transaction_type": transaction_type,
        "time_of_day": time_of_day,
        "distance_from_home": distance,
        "device_trust_score": device_trust,
        "failed_attempts_24h": failed_attempts,
        "txn_velocity_1h": velocity,
        "merchant_risk_score": merchant_risk,
        "is_international": is_international,
        "card_present": card_present,
        "is_fraud": is_fraud,
        "seed_id": index + 1,
    }


records = [_generate_transaction(index) for index in range(SAMPLE_COUNT)]
df = pd.DataFrame(records)

output_path = Path(__file__).with_name("transactions.csv")
df.to_csv(output_path, index=False)

fraud_rate = (df["is_fraud"].mean() * 100.0)
print(f"Generated {len(df)} synthetic transactions at {output_path}")
print(f"Fraud cases: {df['is_fraud'].sum()} ({fraud_rate:.2f}% of dataset)")
