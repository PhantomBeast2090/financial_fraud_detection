"""
backend/evaluate.py
Reproducible offline evaluation of the SHIPPED FraudGuard AI artefact.

What it does:
- Loads dataset/transactions.csv and rebuilds the exact 17-feature frame.
- Recreates the SAME stratified splits as training (seed 42): 20% held-out
  test, then 20% of the remainder as validation (64/16/20 overall).
- Loads the committed backend/model.pkl pipeline WITHOUT retraining and
  scores the held-out test set at the artefact's operating threshold.
- Recomputes threshold selection on VALIDATION ONLY (no test leakage) to
  verify the shipped threshold is consistent with the repo's utility rule.
- Sweeps thresholds on validation (0.30-0.90) for the report.
- Computes permutation importance (global, validation subsample, seed 42).
- Writes reports/model_evaluation.json (machine-readable) and regenerates
  docs/model-evaluation.md (human-readable) from the measured numbers.

Usage:
    python -m backend.evaluate                  # writes reports/ + docs/
    python -m backend.evaluate --output-dir /tmp/eval-check --no-docs
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.ml_features import MODEL_FEATURE_COLUMNS  # noqa: E402
from backend.train_model import (  # noqa: E402
    RANDOM_STATE,
    TARGET_COLUMN,
    build_feature_frame,
    candidate_models,
    choose_threshold,
)
from config.settings import settings  # noqa: E402

EVALUATION_SEED = RANDOM_STATE
TEST_SIZE = 0.20
VALIDATION_SIZE = 0.20  # fraction of the non-test remainder
SWEEP_THRESHOLDS = [round(t, 2) for t in np.arange(0.30, 0.91, 0.05)]

REPORTS_DIR = ROOT_DIR / "reports"
DOCS_REPORT = ROOT_DIR / "docs" / "model-evaluation.md"


# ── data ─────────────────────────────────────────────────────────────────────
def load_dataset() -> Tuple[pd.DataFrame, pd.Series]:
    """Load CSV and return (feature_frame, labels) using the canonical builder."""
    df = pd.read_csv(settings.DATA_PATH)
    if TARGET_COLUMN not in df.columns:
        raise ValueError(f"Expected '{TARGET_COLUMN}' column in {settings.DATA_PATH}")
    X = build_feature_frame(df.to_dict(orient="records"))
    y = df[TARGET_COLUMN].astype(int)
    return X, y


def make_splits(
    X: pd.DataFrame, y: pd.Series, seed: int = EVALUATION_SEED
) -> Dict[str, Any]:
    """Stratified 64/16/20 train/validation/test split (same as training)."""
    X_train_full, X_test, y_train_full, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=seed, stratify=y
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_full, y_train_full,
        test_size=VALIDATION_SIZE, random_state=seed, stratify=y_train_full,
    )
    return {
        "X_train": X_train, "y_train": y_train,
        "X_validation": X_val, "y_validation": y_val,
        "X_test": X_test, "y_test": y_test,
    }


def load_artefact() -> Tuple[Any, Dict[str, Any]]:
    """Load the shipped pipeline + metadata without retraining."""
    from backend.model import load_model_artifact

    model, metadata = load_model_artifact(settings.MODEL_PATH)
    if not metadata:
        raise ValueError(f"{settings.MODEL_PATH} has no metadata; retrain first.")
    return model, metadata


# ── metrics ──────────────────────────────────────────────────────────────────
def evaluate_at_threshold(
    y_true: pd.Series, probabilities: np.ndarray, threshold: float
) -> Dict[str, Any]:
    """Full fraud-metric sheet at one operating threshold."""
    y_true_arr = np.asarray(y_true).astype(int)
    probs = np.asarray(probabilities, dtype=float)
    preds = (probs >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true_arr, preds, labels=[0, 1]).ravel()
    return {
        "threshold": float(threshold),
        "n": int(len(y_true_arr)),
        "prevalence": float(y_true_arr.mean()),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "accuracy": float(accuracy_score(y_true_arr, preds)),
        "precision": float(precision_score(y_true_arr, preds, zero_division=0)),
        "recall": float(recall_score(y_true_arr, preds, zero_division=0)),
        "f1": float(f1_score(y_true_arr, preds, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true_arr, probs)),
        "pr_auc_average_precision": float(average_precision_score(y_true_arr, probs)),
        "false_positive_count": int(fp),
        "false_negative_count": int(fn),
        "false_positive_rate": float(fp / max(tn + fp, 1)),
        "false_negative_rate": float(fn / max(fn + tp, 1)),
    }


def threshold_sweep(
    y_true: pd.Series, probabilities: np.ndarray, thresholds: List[float] = SWEEP_THRESHOLDS
) -> List[Dict[str, float]]:
    """Precision/recall/F1 across thresholds. Run on VALIDATION, not test."""
    rows = []
    for t in thresholds:
        m = evaluate_at_threshold(y_true, probabilities, t)
        rows.append({
            "threshold": m["threshold"],
            "precision": m["precision"],
            "recall": m["recall"],
            "f1": m["f1"],
            "accuracy": m["accuracy"],
        })
    return rows


def compute_permutation_importance(
    model: Any,
    X: pd.DataFrame,
    y: pd.Series,
    n_sample: int = 800,
    n_repeats: int = 5,
    seed: int = EVALUATION_SEED,
) -> List[Dict[str, Any]]:
    """Global permutation importance (mean drop in average precision)."""
    rng = np.random.default_rng(seed)
    idx = np.arange(len(X))
    if len(idx) > n_sample:
        idx = rng.choice(idx, size=n_sample, replace=False)
    Xs, ys = X.iloc[idx], y.iloc[idx]
    result = permutation_importance(
        model, Xs, ys,
        n_repeats=n_repeats, random_state=seed,
        scoring="average_precision", n_jobs=1,
    )
    importances = sorted(
        (
            {"feature": col, "mean": float(m), "std": float(s)}
            for col, m, s in zip(MODEL_FEATURE_COLUMNS, result.importances_mean, result.importances_std)
        ),
        key=lambda r: r["mean"],
        reverse=True,
    )
    return importances


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def candidate_summary() -> List[Dict[str, Any]]:
    """Names + hyperparameters of the training candidate pool (no fitting)."""
    out = []
    for name, pipe in candidate_models().items():
        clf = pipe.named_steps["classifier"]
        params = {k: _jsonable(v) for k, v in clf.get_params().items()}
        out.append({
            "name": name,
            "classifier": type(clf).__name__,
            "params": params,
        })
    return out


def library_versions() -> Dict[str, str]:
    import sklearn

    return {
        "python": platform.python_version(),
        "scikit-learn": sklearn.__version__,
        "pandas": pd.__version__,
        "numpy": np.__version__,
    }


# ── report ───────────────────────────────────────────────────────────────────
def run_evaluation(n_sample: int = 800, n_repeats: int = 5) -> Dict[str, Any]:
    """Execute the full reproducible evaluation; returns the report dict."""
    X, y = load_dataset()
    splits = make_splits(X, y)
    model, metadata = load_artefact()

    operating_threshold = float(metadata.get("threshold", 0.5))
    val_probs = model.predict_proba(splits["X_validation"])[:, 1]
    test_probs = model.predict_proba(splits["X_test"])[:, 1]

    # Threshold selection uses VALIDATION only — the test set never influences it.
    validation_threshold = choose_threshold(
        np.asarray(splits["y_validation"]), np.asarray(val_probs)
    )
    validation_metrics = evaluate_at_threshold(
        splits["y_validation"], val_probs, validation_threshold
    )
    test_metrics = evaluate_at_threshold(
        splits["y_test"], test_probs, operating_threshold
    )
    sweep = threshold_sweep(splits["y_validation"], val_probs)
    importances = compute_permutation_importance(
        model, splits["X_validation"], splits["y_validation"],
        n_sample=n_sample, n_repeats=n_repeats,
    )

    data_path = settings.DATA_PATH
    try:
        data_path_display = str(data_path.relative_to(ROOT_DIR))
    except ValueError:
        data_path_display = str(data_path)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": EVALUATION_SEED,
        "dataset": {
            "path": data_path_display,
            "rows": int(len(y)),
            "fraud_rate": float(np.asarray(y).mean()),
        },
        "splits": {
            "strategy": "stratified 64/16/20 train/validation/test (seed 42)",
            "n_train": int(len(splits["y_train"])),
            "n_validation": int(len(splits["y_validation"])),
            "n_test": int(len(splits["y_test"])),
        },
        "features": list(MODEL_FEATURE_COLUMNS),
        "candidates": candidate_summary(),
        "artefact": {
            "model_name": metadata.get("model_name"),
            "model_version": metadata.get("model_version"),
            "trained_at": metadata.get("trained_at"),
            "training_rows": metadata.get("training_rows"),
        },
        "operating_threshold": operating_threshold,
        "validation_recomputed_threshold": float(validation_threshold),
        "threshold_consistent": bool(
            abs(float(validation_threshold) - operating_threshold) < 1e-9
        ),
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "threshold_sweep_validation": sweep,
        "permutation_importance": {
            "method": "sklearn permutation_importance, scoring=average_precision",
            "n_sample": int(min(n_sample, len(splits["y_validation"]))),
            "n_repeats": int(n_repeats),
            "seed": EVALUATION_SEED,
            "importances": importances,
        },
        "library_versions": library_versions(),
        "notes": [
            "Threshold selection used validation data only; test set is held out.",
            "Operating threshold is the artefact's stored threshold, not re-fit on test.",
            "Dataset is synthetic (see dataset/generate_data.py); metrics do not imply production performance.",
        ],
    }


def render_markdown(report: Dict[str, Any]) -> str:
    """Human-readable report generated from measured numbers only."""
    t = report["test_metrics"]
    v = report["validation_metrics"]
    cm = t["confusion_matrix"]
    lines = [
        "# Model Evaluation",
        "",
        f"_Generated {report['generated_at']} by `python -m backend.evaluate`. "
        "Numbers below are measured from the committed artefact — not targets._",
        "",
        "## Setup",
        "",
        f"- Seed: `{report['seed']}`",
        f"- Dataset: `{report['dataset']['path']}` — {report['dataset']['rows']} rows, "
        f"fraud rate {report['dataset']['fraud_rate']:.4f}",
        f"- Splits: {report['splits']['strategy']} → "
        f"train {report['splits']['n_train']}, validation {report['splits']['n_validation']}, "
        f"test {report['splits']['n_test']}",
        f"- Artefact: {report['artefact']['model_name']} "
        f"({report['artefact']['model_version']}, trained {report['artefact']['trained_at']})",
        f"- Operating threshold: `{report['operating_threshold']}` "
        f"(validation recomputation: `{report['validation_recomputed_threshold']}`, "
        f"consistent: {report['threshold_consistent']})",
        f"- Libraries: {report['library_versions']}",
        "",
        "## Held-out test metrics (operating threshold)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Prevalence | {t['prevalence']:.4f} |",
        f"| Accuracy | {t['accuracy']:.4f} |",
        f"| Precision | {t['precision']:.4f} |",
        f"| Recall | {t['recall']:.4f} |",
        f"| F1 | {t['f1']:.4f} |",
        f"| ROC-AUC | {t['roc_auc']:.4f} |",
        f"| PR-AUC (avg precision) | {t['pr_auc_average_precision']:.4f} |",
        f"| False positives | {t['false_positive_count']} (FPR {t['false_positive_rate']:.4f}) |",
        f"| False negatives | {t['false_negative_count']} (FNR {t['false_negative_rate']:.4f}) |",
        "",
        "### Confusion matrix (test)",
        "",
        "|  | Pred legit | Pred fraud |",
        "|---|---|---|",
        f"| Actual legit | {cm['tn']} | {cm['fp']} |",
        f"| Actual fraud | {cm['fn']} | {cm['tp']} |",
        "",
        "## Validation metrics (selection threshold)",
        "",
        f"- threshold {v['threshold']}: accuracy {v['accuracy']:.4f}, "
        f"precision {v['precision']:.4f}, recall {v['recall']:.4f}, F1 {v['f1']:.4f}",
        "",
        "## Threshold sweep (validation only)",
        "",
        "| Threshold | Precision | Recall | F1 | Accuracy |",
        "|---|---|---|---|---|",
    ]
    for row in report["threshold_sweep_validation"]:
        lines.append(
            f"| {row['threshold']:.2f} | {row['precision']:.4f} | "
            f"{row['recall']:.4f} | {row['f1']:.4f} | {row['accuracy']:.4f} |"
        )
    lines += [
        "",
        "## Global permutation importance (validation subsample)",
        "",
        f"_Method: {report['permutation_importance']['method']}; "
        f"n={report['permutation_importance']['n_sample']}, "
        f"repeats={report['permutation_importance']['n_repeats']}, "
        f"seed={report['permutation_importance']['seed']}. "
        "Association only — not causal. Derived features correlate with their "
        "parents (e.g. amount_log with amount), so single-column shuffling can "
        "overstate a parent's standalone importance._",
        "",
        "| Feature | Mean ΔAP | Std |",
        "|---|---|---|",
    ]
    for imp in report["permutation_importance"]["importances"]:
        lines.append(f"| {imp['feature']} | {imp['mean']:.4f} | {imp['std']:.4f} |")
    lines += [
        "",
        "## Terminology",
        "",
        "- **Model probability**: calibrated fraud likelihood P(fraud|x) ∈ [0,1].",
        "- **Operating threshold**: artefact threshold mapping probability → label.",
        "- **Risk category** (High ≥0.85, Medium ≥0.60, else Low): application triage "
        "bucket, independent of the fraud threshold.",
        "- **Validation vs test**: candidates/thresholds chosen on validation; "
        "final numbers reported on the held-out test split.",
        "",
        "## Limitations",
        "",
        "- Synthetic data: patterns are generator-assumed; expect a gap on real data.",
        "- The committed CSV (15k rows, 7 raw columns) predates the current "
        "generator; missing raw features fall back to defaults during training "
        "(see docs/reproducibility.md).",
        "- Single seed (42); no cross-seed variance reported.",
        "",
    ]
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reproducible FraudGuard AI evaluation")
    parser.add_argument("--output-dir", default=str(REPORTS_DIR))
    parser.add_argument("--docs", default=str(DOCS_REPORT))
    parser.add_argument("--no-docs", action="store_true")
    parser.add_argument("--importance-sample", type=int, default=800)
    parser.add_argument("--importance-repeats", type=int, default=5)
    args = parser.parse_args(argv)

    report = run_evaluation(n_sample=args.importance_sample, n_repeats=args.importance_repeats)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "model_evaluation.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {json_path}")

    if not args.no_docs:
        docs_path = Path(args.docs)
        docs_path.parent.mkdir(parents=True, exist_ok=True)
        docs_path.write_text(render_markdown(report), encoding="utf-8")
        print(f"Wrote {docs_path}")

    t = report["test_metrics"]
    print(
        f"Test @ {report['operating_threshold']}: acc={t['accuracy']:.4f} "
        f"prec={t['precision']:.4f} rec={t['recall']:.4f} f1={t['f1']:.4f} "
        f"roc={t['roc_auc']:.4f} ap={t['pr_auc_average_precision']:.4f} "
        f"fp={t['false_positive_count']} fn={t['false_negative_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
