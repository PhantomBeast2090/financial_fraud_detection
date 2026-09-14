import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    classification_report,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, RobustScaler

try:
    from backend.ml_features import CATEGORICAL_COLUMNS, MODEL_FEATURE_COLUMNS, build_feature_frame
except ModuleNotFoundError:  # allow `python backend/train_model.py` (script mode)
    from ml_features import CATEGORICAL_COLUMNS, MODEL_FEATURE_COLUMNS, build_feature_frame

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT_DIR / "dataset" / "transactions.csv"
MODEL_PATH = ROOT_DIR / "backend" / "model.pkl"
METRICS_PATH = ROOT_DIR / "backend" / "model_metrics.json"

TARGET_COLUMN = "is_fraud"
RANDOM_STATE = 42


def make_preprocessor():
    numeric_columns = [column for column in MODEL_FEATURE_COLUMNS if column not in CATEGORICAL_COLUMNS]
    return ColumnTransformer(
        transformers=[
            ("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_COLUMNS),
            ("numeric", RobustScaler(), numeric_columns),
        ]
    )


def candidate_models():
    return {
        "CalibratedExtraTrees": Pipeline(
            [
                ("preprocessor", make_preprocessor()),
                (
                    "classifier",
                    CalibratedClassifierCV(
                        estimator=ExtraTreesClassifier(
                            n_estimators=420,
                            min_samples_leaf=2,
                            class_weight="balanced_subsample",
                            random_state=RANDOM_STATE,
                            n_jobs=-1,
                        ),
                        cv=3,
                        method="sigmoid",
                    ),
                ),
            ]
        ),
        "CalibratedRandomForest": Pipeline(
            [
                ("preprocessor", make_preprocessor()),
                (
                    "classifier",
                    CalibratedClassifierCV(
                        estimator=RandomForestClassifier(
                            n_estimators=300,
                            max_depth=12,
                            min_samples_leaf=2,
                            class_weight="balanced_subsample",
                            random_state=RANDOM_STATE,
                            n_jobs=-1,
                        ),
                        cv=3,
                        method="sigmoid",
                    ),
                ),
            ]
        ),
        "BalancedLogisticRegression": Pipeline(
            [
                ("preprocessor", make_preprocessor()),
                (
                    "classifier",
                    LogisticRegression(
                        max_iter=2_000,
                        class_weight="balanced",
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        ),
    }


def choose_threshold(y_true, probabilities):
    precision, recall, thresholds = precision_recall_curve(y_true, probabilities)
    if len(thresholds) == 0:
        return 0.5

    f1_scores = (2 * precision[:-1] * recall[:-1]) / np.maximum(precision[:-1] + recall[:-1], 1e-9)
    utility = (0.65 * f1_scores) + (0.20 * precision[:-1]) + (0.15 * recall[:-1])
    best_index = int(np.argmax(utility))
    threshold = float(thresholds[best_index])
    return float(np.clip(threshold, 0.35, 0.78))


def score_predictions(y_true, probabilities, threshold):
    predictions = (probabilities >= threshold).astype(int)
    return {
        "average_precision": float(average_precision_score(y_true, probabilities)),
        "roc_auc": float(roc_auc_score(y_true, probabilities)),
        "accuracy": float(accuracy_score(y_true, predictions)),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "recall": float(recall_score(y_true, predictions, zero_division=0)),
        "f1": float(f1_score(y_true, predictions, zero_division=0)),
        "threshold": float(threshold),
    }


def select_best_model(X_train, y_train, X_validation, y_validation):
    leaderboard = []
    selected_model = None
    selected_name = None
    selected_threshold = None
    best_score = -1.0

    for name, model in candidate_models().items():
        model.fit(X_train, y_train)
        probabilities = model.predict_proba(X_validation)[:, 1]
        threshold = choose_threshold(y_validation, probabilities)
        metrics = score_predictions(y_validation, probabilities, threshold)
        composite_score = (
            (0.45 * metrics["average_precision"])
            + (0.25 * metrics["recall"])
            + (0.20 * metrics["precision"])
            + (0.10 * metrics["f1"])
        )
        leaderboard.append({"name": name, "metrics": metrics, "score": float(composite_score)})

        if composite_score > best_score:
            best_score = composite_score
            selected_model = model
            selected_name = name
            selected_threshold = threshold

    leaderboard.sort(key=lambda row: row["score"], reverse=True)
    return selected_name, selected_model, selected_threshold, leaderboard


def main():
    print(f"Loading dataset from {DATA_PATH} ...")
    df = pd.read_csv(DATA_PATH)
    if TARGET_COLUMN not in df.columns:
        raise ValueError(f"Expected '{TARGET_COLUMN}' column in {DATA_PATH}")

    X = build_feature_frame(df.to_dict(orient="records"))
    y = df[TARGET_COLUMN].astype(int)

    X_train_full, X_test, y_train_full, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=RANDOM_STATE,
        stratify=y,
    )
    X_train, X_validation, y_train, y_validation = train_test_split(
        X_train_full,
        y_train_full,
        test_size=0.20,
        random_state=RANDOM_STATE,
        stratify=y_train_full,
    )

    print("Benchmarking candidate models on validation data ...")
    best_name, _, threshold, leaderboard = select_best_model(
        X_train,
        y_train,
        X_validation,
        y_validation,
    )

    print("Validation leaderboard:")
    for row in leaderboard:
        metrics = row["metrics"]
        print(
            f"  {row['name']}: AP={metrics['average_precision']:.4f} "
            f"Recall={metrics['recall']:.4f} Precision={metrics['precision']:.4f} "
            f"F1={metrics['f1']:.4f} Threshold={metrics['threshold']:.3f}"
        )

    final_model = candidate_models()[best_name]
    final_model.fit(X_train_full, y_train_full)

    test_probabilities = final_model.predict_proba(X_test)[:, 1]
    test_metrics = score_predictions(y_test, test_probabilities, threshold)
    test_predictions = (test_probabilities >= threshold).astype(int)

    metadata = {
        "model_name": best_name,
        "model_version": f"{best_name}-v2",
        "trained_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "threshold": float(threshold),
        "training_rows": int(len(df)),
        "feature_columns": MODEL_FEATURE_COLUMNS,
        "dataset": {
            "path": str(DATA_PATH),
            "rows": int(len(df)),
            "fraud_rate": float(y.mean()),
        },
        "validation_leaderboard": leaderboard,
        "test_metrics": test_metrics,
    }

    artifact = {
        "model": final_model,
        "metadata": metadata,
    }

    print("\nSelected model:", best_name)
    print("Test metrics:")
    print(json.dumps(test_metrics, indent=2))
    print("\nClassification report:")
    print(classification_report(y_test, test_predictions, digits=4))

    joblib.dump(artifact, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nSaved trained artifact to {MODEL_PATH}")
    print(f"Saved model metadata to {METRICS_PATH}")


if __name__ == "__main__":
    main()
