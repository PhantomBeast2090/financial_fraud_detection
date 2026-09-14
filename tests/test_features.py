"""
tests/test_features.py — feature engineering contract (objective 1A + 1G).
"""
import math

import numpy as np
import pytest

from backend.ml_features import (
    CATEGORICAL_COLUMNS,
    DEFAULT_TRANSACTION,
    DERIVED_FEATURE_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    RAW_FEATURE_COLUMNS,
    build_feature_frame,
    normalize_transaction_payload,
)


def test_contract_has_17_features():
    assert len(MODEL_FEATURE_COLUMNS) == 17
    assert len(RAW_FEATURE_COLUMNS) == 11
    assert len(DERIVED_FEATURE_COLUMNS) == 6
    assert set(MODEL_FEATURE_COLUMNS) == set(RAW_FEATURE_COLUMNS) | set(DERIVED_FEATURE_COLUMNS)


def test_contract_matches_committed_metadata():
    import json

    from config.settings import settings

    metadata = json.loads(settings.METRICS_PATH.read_text())
    assert metadata["feature_columns"] == MODEL_FEATURE_COLUMNS


def test_build_frame_column_order_and_count():
    frame = build_feature_frame([dict(DEFAULT_TRANSACTION)])
    assert list(frame.columns) == MODEL_FEATURE_COLUMNS
    assert len(frame) == 1


def test_normalize_missing_values_use_defaults():
    out = normalize_transaction_payload({})
    for key, default in DEFAULT_TRANSACTION.items():
        assert out[key] == default, key


def test_normalize_none_payload_uses_defaults():
    out = normalize_transaction_payload(None)
    assert out["amount"] == DEFAULT_TRANSACTION["amount"]


@pytest.mark.parametrize("bad", ["abc", "", None, [], {}])
def test_normalize_invalid_numerics_fall_back(bad):
    out = normalize_transaction_payload({"amount": bad, "time_of_day": bad})
    assert out["amount"] == DEFAULT_TRANSACTION["amount"]
    assert out["time_of_day"] == DEFAULT_TRANSACTION["time_of_day"]


def test_bounds_clipping():
    out = normalize_transaction_payload({
        "amount": 9_999_999,
        "time_of_day": 99,
        "distance_from_home": -50,
        "device_trust_score": 500,
        "failed_attempts_24h": -3,
        "txn_velocity_1h": 0,
        "merchant_risk_score": -1,
    })
    assert out["amount"] == 500_000.0
    assert out["time_of_day"] == 23
    assert out["distance_from_home"] == 0.0
    assert out["device_trust_score"] == 100.0
    assert out["failed_attempts_24h"] == 0
    assert out["txn_velocity_1h"] == 1
    assert out["merchant_risk_score"] == 0.0


def test_build_frame_clips_out_of_range_rows():
    frame = build_feature_frame([{
        **DEFAULT_TRANSACTION,
        "amount": -5,
        "time_of_day": 99,
        "device_trust_score": 999,
    }])
    assert frame["amount"].iloc[0] == 1.0
    assert frame["time_of_day"].iloc[0] == 23
    assert frame["device_trust_score"].iloc[0] == 100.0


def test_derived_amount_log():
    frame = build_feature_frame([{**DEFAULT_TRANSACTION, "amount": 1000.0}])
    assert frame["amount_log"].iloc[0] == pytest.approx(math.log1p(1000.0))


@pytest.mark.parametrize(
    "hour,expected", [(0, 1), (5, 1), (6, 0), (12, 0), (22, 0), (23, 1)]
)
def test_derived_night_risk_boundaries(hour, expected):
    frame = build_feature_frame([{**DEFAULT_TRANSACTION, "time_of_day": hour}])
    assert frame["night_risk"].iloc[0] == expected


def test_derived_trust_gap():
    frame = build_feature_frame([{**DEFAULT_TRANSACTION, "device_trust_score": 30.0}])
    assert frame["trust_gap"].iloc[0] == pytest.approx(70.0)


def test_derived_velocity_pressure():
    frame = build_feature_frame([{
        **DEFAULT_TRANSACTION, "txn_velocity_1h": 4, "failed_attempts_24h": 2,
    }])
    assert frame["velocity_pressure"].iloc[0] == 4 * (1 + 2)


def test_derived_distance_amount_pressure():
    frame = build_feature_frame([{
        **DEFAULT_TRANSACTION, "amount": 1000.0, "distance_from_home": 100.0,
    }])
    expected = math.log1p(100.0) * math.log1p(1000.0)
    assert frame["distance_amount_pressure"].iloc[0] == pytest.approx(expected)


@pytest.mark.parametrize(
    "intl,card,expected",
    [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 1)],
)
def test_derived_cross_border_card_not_present(intl, card, expected):
    frame = build_feature_frame([{
        **DEFAULT_TRANSACTION, "is_international": intl, "card_present": card,
    }])
    assert frame["cross_border_card_not_present"].iloc[0] == expected


def test_categorical_unknown_values_pass_through_for_onehot_ignore():
    # Unknown categories must not crash the frame; the pipeline's
    # OneHotEncoder(handle_unknown="ignore") absorbs them at predict time.
    frame = build_feature_frame([{
        **DEFAULT_TRANSACTION, "location": "Atlantis", "transaction_type": "BARTER",
    }])
    assert frame["location"].iloc[0] == "Atlantis"
    assert frame["transaction_type"].iloc[0] == "BARTER"


def test_categorical_blank_and_none_fall_back():
    frame = build_feature_frame([
        {**DEFAULT_TRANSACTION, "location": "  ", "transaction_type": None},
    ])
    assert frame["location"].iloc[0] == DEFAULT_TRANSACTION["location"]
    assert frame["transaction_type"].iloc[0] == DEFAULT_TRANSACTION["transaction_type"]


def test_categorical_columns_declared():
    assert CATEGORICAL_COLUMNS == ["location", "transaction_type"]


def test_train_inference_contract_consistency():
    """Training and inference must build identical feature frames (1G)."""
    import inspect

    import backend.train_model as tm
    from backend import model as model_module

    assert tm.MODEL_FEATURE_COLUMNS == MODEL_FEATURE_COLUMNS
    assert tm.build_feature_frame is build_feature_frame
    assert model_module.build_feature_frame is build_feature_frame
    src = inspect.getsource(tm.main)
    assert "build_feature_frame" in src


def test_numeric_strings_coerced():
    frame = build_feature_frame([{**DEFAULT_TRANSACTION, "amount": "2500", "time_of_day": "14"}])
    assert frame["amount"].iloc[0] == pytest.approx(2500.0)
    assert frame["time_of_day"].iloc[0] == 14


def test_bool_parsing():
    assert normalize_transaction_payload({"is_international": True})["is_international"] == 1
    assert normalize_transaction_payload({"is_international": "yes"})["is_international"] == 1
    assert normalize_transaction_payload({"is_international": 0})["is_international"] == 0
    assert normalize_transaction_payload({"card_present": False})["card_present"] == 0


def test_frame_handles_nan_gracefully():
    frame = build_feature_frame([{**DEFAULT_TRANSACTION, "amount": np.nan, "location": np.nan}])
    assert frame["amount"].iloc[0] == DEFAULT_TRANSACTION["amount"]
    assert frame["location"].iloc[0] == DEFAULT_TRANSACTION["location"]
    assert not frame.isna().any().any()
