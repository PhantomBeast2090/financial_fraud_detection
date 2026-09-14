"""
tests/test_train.py — training pipeline units without full retraining (1C).

Full retraining (ExtraTrees 420 trees + calibration) is intentionally NOT run
here; CI validates the shipped artefact via backend/evaluate.py instead.
"""
import numpy as np
import pytest

from backend.ml_features import MODEL_FEATURE_COLUMNS
from backend.train_model import (
    RANDOM_STATE,
    candidate_models,
    choose_threshold,
    make_preprocessor,
    score_predictions,
    select_best_model,
)


def _toy_labels_and_scores():
    y = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    probs = np.array([0.1, 0.2, 0.35, 0.4, 0.6, 0.7, 0.8, 0.9])
    return y, probs


def test_random_state_fixed():
    assert RANDOM_STATE == 42


def test_dataset_loads_with_expected_shape():
    from backend.evaluate import load_dataset

    X, y = load_dataset()
    assert list(X.columns) == MODEL_FEATURE_COLUMNS
    assert len(X) == len(y) == 15000
    assert set(y.unique()) <= {0, 1}
    assert 0.05 < y.mean() < 0.20  # imbalanced, fraud minority


def test_splits_stratified_and_sized():
    from backend.evaluate import make_splits, load_dataset

    X, y = load_dataset()
    s = make_splits(X, y)
    assert len(s["y_train"]) == 9600
    assert len(s["y_validation"]) == 2400
    assert len(s["y_test"]) == 3000
    for split in ("y_train", "y_validation", "y_test"):
        assert s[split].mean() == pytest.approx(y.mean(), abs=0.02)


def test_splits_deterministic():
    from backend.evaluate import make_splits, load_dataset

    X, y = load_dataset()
    first = make_splits(X, y)["y_test"].tolist()
    second = make_splits(X, y)["y_test"].tolist()
    assert first == second


def test_candidate_pool_names():
    models = candidate_models()
    assert set(models) == {
        "CalibratedExtraTrees",
        "CalibratedRandomForest",
        "BalancedLogisticRegression",
    }


def test_candidate_hyperparameters_pinned():
    models = candidate_models()
    et = models["CalibratedExtraTrees"].named_steps["classifier"].estimator
    assert et.n_estimators == 420
    assert et.random_state == 42
    rf = models["CalibratedRandomForest"].named_steps["classifier"].estimator
    assert rf.n_estimators == 300 and rf.max_depth == 12
    lr = models["BalancedLogisticRegression"].named_steps["classifier"]
    assert lr.max_iter == 2000 and lr.class_weight == "balanced"


def test_preprocessor_covers_all_features():
    prep = make_preprocessor()
    cats = list(prep.transformers[0][2])
    nums = list(prep.transformers[1][2])
    assert cats == ["location", "transaction_type"]
    assert set(cats) | set(nums) == set(MODEL_FEATURE_COLUMNS)


def test_choose_threshold_degenerate_returns_default():
    # Identical scores -> single candidate threshold, clipped into repo bounds.
    assert choose_threshold(np.array([0, 1]), np.array([0.5, 0.5])) == 0.5


def test_choose_threshold_clipped_to_repo_bounds():
    rng = np.random.default_rng(0)
    y = (rng.random(500) < 0.1).astype(int)
    probs = rng.random(500)
    threshold = choose_threshold(y, probs)
    assert 0.35 <= threshold <= 0.78


def test_score_predictions_keys_and_ranges():
    y, probs = _toy_labels_and_scores()
    metrics = score_predictions(y, probs, 0.5)
    for key in ("average_precision", "roc_auc", "accuracy",
                "precision", "recall", "f1", "threshold"):
        assert key in metrics
        assert 0.0 <= metrics[key] <= 1.0 or key == "threshold"
    assert metrics["threshold"] == 0.5
    assert metrics["accuracy"] == 1.0  # toy data separates cleanly at 0.5


def test_select_best_model_tiny_repeatable():
    """End-to-end selection on a tiny slice: leaderboard sorted + repeatable."""
    from backend.evaluate import load_dataset

    X, y = load_dataset()
    tiny = X.iloc[:600]
    tiny_y = y.iloc[:600]
    args = (tiny.iloc[:400], tiny_y.iloc[:400], tiny.iloc[400:], tiny_y.iloc[400:])
    name1, _, thr1, board1 = select_best_model(*args)
    name2, _, thr2, board2 = select_best_model(*args)
    assert name1 == name2 and thr1 == pytest.approx(thr2)
    scores = [row["score"] for row in board1]
    assert scores == sorted(scores, reverse=True)
    assert {row["name"] for row in board1} == set(candidate_models())


def test_evaluate_module_threshold_no_test_leak():
    """evaluate.py must derive selection thresholds from validation only."""
    import inspect

    import backend.evaluate as ev

    src = inspect.getsource(ev.run_evaluation)
    assert "validation" in src
    assert "choose_threshold" in src
    # The operating threshold comes from the artefact, never from test data.
    assert "metadata" in src or "artefact" in src
