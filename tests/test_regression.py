"""
tests/test_regression.py — contract guards: legacy isolation, canonical paths (1G/9).
"""
import sys


def test_canonical_feature_contract_used_everywhere():
    from backend import model as model_module
    from backend.ml_features import MODEL_FEATURE_COLUMNS
    from backend.train_model import MODEL_FEATURE_COLUMNS as TRAIN_COLS

    assert TRAIN_COLS == MODEL_FEATURE_COLUMNS
    assert model_module.build_feature_frame is not None


def test_legacy_modules_not_imported_by_app():
    import backend.main  # noqa: F401

    assert "backend.app" not in sys.modules, "Flask legacy must not load"
    assert "backend.db" not in sys.modules, "legacy db helper must not load"
    assert "app" not in sys.modules or "backend" in getattr(
        sys.modules.get("app", object()), "__name__", "backend")


def test_legacy_files_unreferenced_by_canonical_code():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in list((root / "backend").rglob("*.py")) + list((root / "config").rglob("*.py")):
        if path.name in ("app.py", "db.py"):
            continue
        text = path.read_text()
        for marker in ("from db import", "from model import",
                       "import backend.app", "import backend.db",
                       "from backend.app import", "from backend.db import"):
            if marker in text:
                offenders.append(f"{path.name}: {marker}")
    assert offenders == []


def test_predict_response_has_no_legacy_keys(seeded_client, user_token):
    from tests.conftest import SAFE_TXN, auth_headers

    body = seeded_client.post("/api/transactions/predict", json=SAFE_TXN,
                              headers=auth_headers(user_token)).json()
    # Legacy Flask returned {"transaction_id", "fraud_probability", "prediction"};
    # the canonical API returns label/status/explanation instead of `prediction`.
    assert "prediction" not in body
    assert "transaction_time" not in body
    assert set(body) >= {"transaction_id", "label", "risk_level", "status", "explanation"}


def test_threshold_single_source_of_truth():
    import json

    from backend.model import predict_fraud
    from config.settings import settings
    from tests.conftest import SAFE_TXN

    committed = json.loads(settings.METRICS_PATH.read_text())["threshold"]
    assert predict_fraud(dict(SAFE_TXN))["threshold"] == committed
    assert committed == 0.78


def test_risk_buckets_distinct_from_fraud_threshold():
    """Risk category (0.85/0.60 app buckets) is independent of the 0.78 model cut."""
    from backend.explain import risk_category

    assert risk_category(0.80) == "Medium"  # above fraud cut, below High bucket
    assert risk_category(0.78) == "Medium"
