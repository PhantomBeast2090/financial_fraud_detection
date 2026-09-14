"""
tests/test_explain.py — explainability contract (objective 5).
"""
import pytest

from backend.explain import (
    EXPLANATION_DISCLAIMER,
    RISK_FACTOR_RULES,
    explain_transaction,
    risk_category,
    triggered_factors,
)
from backend.ml_features import DEFAULT_TRANSACTION
from tests.conftest import RISKY_TXN, SAFE_TXN


def test_risk_category_thresholds():
    assert risk_category(0.85) == "High"
    assert risk_category(0.60) == "Medium"
    assert risk_category(0.10) == "Low"


def test_safe_transaction_no_factors():
    factors = triggered_factors(dict(SAFE_TXN))
    assert factors == []


def test_risky_transaction_expected_factors():
    factors = {f["factor"] for f in triggered_factors(dict(RISKY_TXN))}
    assert {
        "Large transfer amount",
        "Far from usual location",
        "Low device trust",
        "Multiple failed attempts",
        "Unusual one-hour transaction burst",
        "High-risk merchant profile",
        "Cross-border transaction",
        "Card-not-present high-value payment",
        "Odd-hour activity",
    } <= factors


def test_factor_details_carry_observed_values():
    factors = triggered_factors(dict(RISKY_TXN))
    large = next(f for f in factors if f["factor"] == "Large transfer amount")
    assert "60,000" in large["detail"]


def test_explain_transaction_envelope():
    txn = dict(RISKY_TXN)
    expl = explain_transaction(txn, 0.91, 0.78)
    assert expl["probability"] == pytest.approx(0.91)
    assert expl["threshold"] == pytest.approx(0.78)
    assert expl["label"] == "Fraud"
    assert expl["risk_category"] == "High"
    assert expl["factors_triggered"] == len(expl["factors"])
    assert expl["disclaimer"] == EXPLANATION_DISCLAIMER


def test_explain_below_threshold_is_legitimate():
    expl = explain_transaction(dict(SAFE_TXN), 0.04, 0.78)
    assert expl["label"] == "Legitimate"
    assert expl["risk_category"] == "Low"


def test_explain_matches_model_reasons():
    """Explanation factors and UI reasons must never contradict (same rules)."""
    from backend.model import predict_fraud

    result = predict_fraud(dict(RISKY_TXN))
    factor_labels = {f["factor"] for f in result["explanation"]["factors"]}
    for reason in result["reasons"]:
        if reason not in ("Signals match trusted customer behavior",
                          "Mixed signals detected across behavior profile"):
            assert reason in factor_labels, reason


def test_default_transaction_explains_cleanly():
    expl = explain_transaction(dict(DEFAULT_TRANSACTION), 0.05, 0.78)
    assert expl["label"] == "Legitimate"
    assert expl["factors"] == []


def test_rule_count_stable():
    assert len(RISK_FACTOR_RULES) == 9
