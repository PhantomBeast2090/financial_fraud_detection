"""
backend/explain.py
Lightweight, defensible explainability for FraudGuard AI.

What this IS:
- A structured, human-readable summary of *which fraud-relevant signals fired*
  for one transaction (rule-based factors with observed values), plus the
  model's probability, the operating decision threshold, and the resulting
  application risk category.
- Optionally, the top globally-important features from permutation importance
  (computed offline by backend/evaluate.py on validation data), attached as
  context — NOT as a per-transaction causal claim.

What this is NOT:
- NOT causal attribution ("X caused the fraud score").
- NOT SHAP/LIME counterfactuals. Per-transaction contributions from the linear
  candidate cannot be transferred to the calibrated-tree candidates, so we
  deliberately report (a) transparent triggered factors and (b) global
  permutation importance, each labelled as such.

The factor rules mirror the same domain thresholds used in
backend/model._derive_reasons and dataset/generate_data.py risk logic, so the
UI reasons list and the explanation never contradict each other.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

EXPLANATION_DISCLAIMER = (
    "Heuristic triage aid: lists fraud-relevant signals observed on this "
    "transaction and the model's score vs the operating threshold. "
    "It does not prove fraud and does not attribute causality."
)


def _factor(key: str, label: str, fires: Callable[[dict], bool], detail: Callable[[dict], str]) -> dict:
    return {"key": key, "label": label, "fires": fires, "detail": detail}


RISK_FACTOR_RULES: List[dict] = [
    _factor(
        "large_amount", "Large transfer amount",
        lambda t: t["amount"] >= 30_000,
        lambda t: f"amount ₹{t['amount']:,.2f} ≥ ₹30,000",
    ),
    _factor(
        "far_from_home", "Far from usual location",
        lambda t: t["distance_from_home"] >= 150,
        lambda t: f"{t['distance_from_home']:,.1f} km from home ≥ 150 km",
    ),
    _factor(
        "low_device_trust", "Low device trust",
        lambda t: t["device_trust_score"] <= 35,
        lambda t: f"device trust {t['device_trust_score']:.0f}/100 ≤ 35",
    ),
    _factor(
        "failed_attempts", "Multiple failed attempts",
        lambda t: t["failed_attempts_24h"] >= 3,
        lambda t: f"{t['failed_attempts_24h']} failed attempts in 24h ≥ 3",
    ),
    _factor(
        "velocity_burst", "Unusual one-hour transaction burst",
        lambda t: t["txn_velocity_1h"] >= 6,
        lambda t: f"{t['txn_velocity_1h']} transactions/hour ≥ 6",
    ),
    _factor(
        "risky_merchant", "High-risk merchant profile",
        lambda t: t["merchant_risk_score"] >= 70,
        lambda t: f"merchant risk {t['merchant_risk_score']:.0f}/100 ≥ 70",
    ),
    _factor(
        "cross_border", "Cross-border transaction",
        lambda t: bool(t["is_international"]),
        lambda t: "is_international = 1",
    ),
    _factor(
        "cnp_high_value", "Card-not-present high-value payment",
        lambda t: (not t["card_present"]) and t["amount"] >= 18_000,
        lambda t: f"card_not_present with amount ₹{t['amount']:,.2f} ≥ ₹18,000",
    ),
    _factor(
        "odd_hour", "Odd-hour activity",
        lambda t: t["time_of_day"] <= 5 or t["time_of_day"] >= 23,
        lambda t: f"hour {t['time_of_day']:02d}:00 in 23:00–05:00 window",
    ),
]


def risk_category(probability: float, high: float = 0.85, medium: float = 0.60) -> str:
    """Application risk bucket. Distinct from the model's fraud threshold."""
    if probability >= high:
        return "High"
    if probability >= medium:
        return "Medium"
    return "Low"


def triggered_factors(transaction: Dict[str, Any]) -> List[Dict[str, str]]:
    """Return the structured factors whose rule fired for this transaction."""
    out = []
    for rule in RISK_FACTOR_RULES:
        try:
            if rule["fires"](transaction):
                out.append({"factor": rule["label"], "detail": rule["detail"](transaction)})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def explain_transaction(
    transaction: Dict[str, Any],
    probability: float,
    threshold: float,
    *,
    high: float = 0.85,
    medium: float = 0.60,
    global_top_features: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build the structured explanation payload for one scored transaction."""
    probability = float(probability)
    threshold = float(threshold)
    factors = triggered_factors(transaction)
    return {
        "probability": probability,
        "threshold": threshold,
        "label": "Fraud" if probability >= threshold else "Legitimate",
        "risk_category": risk_category(probability, high, medium),
        "factors_triggered": len(factors),
        "factors": factors,
        "global_top_features": global_top_features or [],
        "disclaimer": EXPLANATION_DISCLAIMER,
    }
