# Model Evaluation

_Generated 2026-09-14T15:50:09+00:00 by `python -m backend.evaluate`. Numbers below are measured from the committed artefact — not targets._

## Setup

- Seed: `42`
- Dataset: `dataset/transactions.csv` — 15000 rows, fraud rate 0.1078
- Splits: stratified 64/16/20 train/validation/test (seed 42) → train 9600, validation 2400, test 3000
- Artefact: BalancedLogisticRegression (BalancedLogisticRegression-v2, trained 2026-05-06T15:04:00Z)
- Operating threshold: `0.78` (validation recomputation: `0.78`, consistent: True)
- Libraries: {'python': '3.14.3', 'scikit-learn': '1.8.0', 'pandas': '3.0.1', 'numpy': '2.4.3'}

## Held-out test metrics (operating threshold)

| Metric | Value |
|---|---|
| Prevalence | 0.1077 |
| Accuracy | 0.9873 |
| Precision | 0.9734 |
| Recall | 0.9071 |
| F1 | 0.9391 |
| ROC-AUC | 0.9534 |
| PR-AUC (avg precision) | 0.9183 |
| False positives | 8 (FPR 0.0030) |
| False negatives | 30 (FNR 0.0929) |

### Confusion matrix (test)

|  | Pred legit | Pred fraud |
|---|---|---|
| Actual legit | 2669 | 8 |
| Actual fraud | 30 | 293 |

## Validation metrics (selection threshold)

- threshold 0.78: accuracy 0.9904, precision 0.9836, recall 0.9266, F1 0.9543

## Threshold sweep (validation only)

| Threshold | Precision | Recall | F1 | Accuracy |
|---|---|---|---|---|
| 0.30 | 0.9339 | 0.9266 | 0.9302 | 0.9850 |
| 0.35 | 0.9486 | 0.9266 | 0.9375 | 0.9867 |
| 0.40 | 0.9756 | 0.9266 | 0.9505 | 0.9896 |
| 0.45 | 0.9836 | 0.9266 | 0.9543 | 0.9904 |
| 0.50 | 0.9836 | 0.9266 | 0.9543 | 0.9904 |
| 0.55 | 0.9836 | 0.9266 | 0.9543 | 0.9904 |
| 0.60 | 0.9836 | 0.9266 | 0.9543 | 0.9904 |
| 0.65 | 0.9836 | 0.9266 | 0.9543 | 0.9904 |
| 0.70 | 0.9836 | 0.9266 | 0.9543 | 0.9904 |
| 0.75 | 0.9836 | 0.9266 | 0.9543 | 0.9904 |
| 0.80 | 0.9836 | 0.9266 | 0.9543 | 0.9904 |
| 0.85 | 0.9836 | 0.9266 | 0.9543 | 0.9904 |
| 0.90 | 0.9835 | 0.9228 | 0.9522 | 0.9900 |

## Global permutation importance (validation subsample)

_Method: sklearn permutation_importance, scoring=average_precision; n=800, repeats=5, seed=42. Association only — not causal. Derived features correlate with their parents (e.g. amount_log with amount), so single-column shuffling can overstate a parent's standalone importance._

| Feature | Mean ΔAP | Std |
|---|---|---|
| amount | 0.8062 | 0.0059 |
| distance_amount_pressure | 0.0021 | 0.0041 |
| device_trust_score | 0.0000 | 0.0000 |
| failed_attempts_24h | 0.0000 | 0.0000 |
| txn_velocity_1h | 0.0000 | 0.0000 |
| merchant_risk_score | 0.0000 | 0.0000 |
| is_international | 0.0000 | 0.0000 |
| card_present | 0.0000 | 0.0000 |
| trust_gap | 0.0000 | 0.0000 |
| velocity_pressure | 0.0000 | 0.0000 |
| cross_border_card_not_present | 0.0000 | 0.0000 |
| night_risk | -0.0002 | 0.0063 |
| transaction_type | -0.0006 | 0.0009 |
| location | -0.0013 | 0.0012 |
| distance_from_home | -0.0013 | 0.0016 |
| amount_log | -0.0038 | 0.0028 |
| time_of_day | -0.0100 | 0.0041 |

## Terminology

- **Model probability**: calibrated fraud likelihood P(fraud|x) ∈ [0,1].
- **Operating threshold**: artefact threshold mapping probability → label.
- **Risk category** (High ≥0.85, Medium ≥0.60, else Low): application triage bucket, independent of the fraud threshold.
- **Validation vs test**: candidates/thresholds chosen on validation; final numbers reported on the held-out test split.

## Limitations

- Synthetic data: patterns are generator-assumed; expect a gap on real data.
- The committed CSV (15k rows, 7 raw columns) predates the current generator; missing raw features fall back to defaults during training (see docs/reproducibility.md).
- Single seed (42); no cross-seed variance reported.
