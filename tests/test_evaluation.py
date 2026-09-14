"""
tests/test_evaluation.py — evaluation module: metrics math + determinism (4/6).
"""
import numpy as np
import pytest

from backend.evaluate import (
    SWEEP_THRESHOLDS,
    evaluate_at_threshold,
    load_artefact,
    load_dataset,
    make_splits,
    threshold_sweep,
)


def test_artefact_threshold_is_operating_point():
    _, metadata = load_artefact()
    assert metadata["threshold"] == pytest.approx(0.78)


def test_test_metrics_reproduce_committed_numbers():
    """Held-out metrics must match backend/model_metrics.json (no invention)."""
    import json

    from config.settings import settings

    committed = json.loads(settings.METRICS_PATH.read_text())["test_metrics"]
    X, y = load_dataset()
    splits = make_splits(X, y)
    model, metadata = load_artefact()
    probs = model.predict_proba(splits["X_test"])[:, 1]
    measured = evaluate_at_threshold(
        splits["y_test"], probs, float(metadata["threshold"]))
    for key in ("accuracy", "precision", "recall", "f1", "roc_auc"):
        assert measured[key] == pytest.approx(committed[key], abs=1e-9), key
    assert measured["pr_auc_average_precision"] == pytest.approx(
        committed["average_precision"], abs=1e-9)


def test_confusion_matrix_arithmetic():
    y = np.array([0, 0, 0, 1, 1])
    probs = np.array([0.1, 0.8, 0.2, 0.9, 0.3])
    m = evaluate_at_threshold(y, probs, 0.5)
    assert m["confusion_matrix"] == {"tn": 2, "fp": 1, "fn": 1, "tp": 1}
    assert m["false_positive_count"] == 1
    assert m["false_negative_count"] == 1
    assert m["false_positive_rate"] == pytest.approx(1 / 3)
    assert m["false_negative_rate"] == pytest.approx(1 / 2)
    assert m["prevalence"] == pytest.approx(0.4)


def test_sweep_covers_range_monotone_recall():
    y = np.array([0] * 50 + [1] * 50)
    rng = np.random.default_rng(42)
    probs = np.concatenate([rng.uniform(0, 0.6, 50), rng.uniform(0.4, 1.0, 50)])
    sweep = threshold_sweep(y, probs)
    assert [r["threshold"] for r in sweep] == SWEEP_THRESHOLDS
    recalls = [r["recall"] for r in sweep]
    assert recalls == sorted(recalls, reverse=True)  # higher bar -> fewer caught


def test_run_evaluation_structure(tmp_path):
    from backend.evaluate import run_evaluation

    report = run_evaluation(n_sample=100, n_repeats=2)
    for key in ("seed", "dataset", "splits", "features", "candidates",
                "artefact", "operating_threshold", "validation_metrics",
                "test_metrics", "threshold_sweep_validation",
                "permutation_importance", "library_versions"):
        assert key in report, key
    assert report["seed"] == 42
    assert report["dataset"]["rows"] == 15000
    assert len(report["features"]) == 17
    assert len(report["permutation_importance"]["importances"]) == 17
    top = report["permutation_importance"]["importances"][0]
    assert {"feature", "mean", "std"} <= set(top)


def test_cli_writes_json_to_custom_dir(tmp_path):
    from backend.evaluate import main

    out = tmp_path / "eval"
    rc = main(["--output-dir", str(out), "--no-docs",
               "--importance-sample", "60", "--importance-repeats", "2"])
    assert rc == 0
    import json

    report = json.loads((out / "model_evaluation.json").read_text())
    assert report["dataset"]["rows"] == 15000
