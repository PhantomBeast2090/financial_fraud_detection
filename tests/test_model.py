"""
tests/test_model.py — model layer: loading, shapes, ranges, thresholds (1B).
"""
import joblib
import pytest

from backend.ml_features import DEFAULT_TRANSACTION
from backend.model import get_model_metadata, load_model_artifact, predict_fraud
from config.settings import settings


def test_artefact_loads_and_has_metadata():
    model, metadata = load_model_artifact()
    assert model is not None
    assert hasattr(model, "predict_proba")
    assert metadata["threshold"] == pytest.approx(0.78)
    assert metadata["model_name"] == "BalancedLogisticRegression"


def test_missing_artefact_raises(tmp_path):
    with pytest.raises(Exception):
        load_model_artifact(tmp_path / "does-not-exist.pkl")


def test_corrupt_artefact_raises(tmp_path):
    bad = tmp_path / "corrupt.pkl"
    bad.write_bytes(b"this is not a pickle")
    with pytest.raises(Exception):
        load_model_artifact(bad)


def test_bare_estimator_pickle_supported(tmp_path):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression

    pipe = Pipeline([("sc", StandardScaler()), ("clf", LogisticRegression())])
    path = tmp_path / "bare.pkl"
    joblib.dump(pipe, path)
    model, metadata = load_model_artifact(path)
    assert metadata == {}
    assert hasattr(model, "predict_proba")


def test_predict_returns_full_envelope():
    result = predict_fraud(dict(DEFAULT_TRANSACTION))
    for key in ("probability", "threshold", "label", "risk_level",
                "model_version", "reasons", "explanation", "transaction"):
        assert key in result, key


def test_probability_range_and_label_consistency():
    for payload in (dict(DEFAULT_TRANSACTION), {"amount": 99999}, {"amount": 10}):
        result = predict_fraud(payload)
        assert 0.0 <= result["probability"] <= 1.0
        expected = "Fraud" if result["probability"] >= result["threshold"] else "Legitimate"
        assert result["label"] == expected


def test_threshold_matches_committed_metadata():
    result = predict_fraud(dict(DEFAULT_TRANSACTION))
    assert result["threshold"] == pytest.approx(0.78)


def test_risky_payload_is_fraud_and_safe_is_legitimate():
    from tests.conftest import RISKY_TXN, SAFE_TXN

    risky = predict_fraud(dict(RISKY_TXN))
    safe = predict_fraud(dict(SAFE_TXN))
    assert risky["label"] == "Fraud" and risky["risk_level"] == "High"
    assert safe["label"] == "Legitimate" and safe["risk_level"] == "Low"
    assert risky["probability"] > safe["probability"]


def test_risk_level_boundaries():
    from backend.model import _risk_level

    assert _risk_level(0.85) == "High"
    assert _risk_level(0.849) == "Medium"
    assert _risk_level(0.60) == "Medium"
    assert _risk_level(0.599) == "Low"


def test_reasons_bounded_and_deterministic():
    from tests.conftest import RISKY_TXN

    first = predict_fraud(dict(RISKY_TXN))["reasons"]
    second = predict_fraud(dict(RISKY_TXN))["reasons"]
    assert first == second
    assert 1 <= len(first) <= 3


def test_explanation_envelope():
    from tests.conftest import RISKY_TXN

    result = predict_fraud(dict(RISKY_TXN))
    expl = result["explanation"]
    assert expl["label"] == result["label"]
    assert expl["probability"] == pytest.approx(result["probability"])
    assert expl["threshold"] == pytest.approx(result["threshold"])
    assert expl["risk_category"] == result["risk_level"]
    assert expl["factors_triggered"] == len(expl["factors"]) >= 1
    assert "disclaimer" in expl and expl["disclaimer"]


def test_metadata_accessor():
    meta = get_model_metadata()
    assert meta["threshold"] == pytest.approx(0.78)
    assert meta["model_name"] == "BalancedLogisticRegression"
    assert "test_metrics" in meta


def test_model_path_from_settings():
    assert settings.MODEL_PATH.name == "model.pkl"
    assert settings.MODEL_PATH.exists()
