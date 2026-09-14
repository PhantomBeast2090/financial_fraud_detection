# Reproducibility

## Deterministic evaluation (the supported path)

```bash
python -m backend.evaluate            # -> reports/model_evaluation.json + docs/model-evaluation.md
python -m backend.evaluate --output-dir /tmp/eval-check --no-docs   # CI mode, repo untouched
```

Captured in every report: seed (42), dataset rows + fraud rate, the 17-feature
list, candidate names + hyperparameters, split sizes (9600/2400/3000),
selected model + operating threshold, validation vs test metrics, threshold
sweep (validation only), permutation importance settings, training timestamp,
and library versions.

## Data caveat (read before citing metrics)

- The dataset is **synthetic** (`dataset/generate_data.py`, seed 42).
- The committed `dataset/transactions.csv` has **15,000 rows and 7 raw columns**
  (`account_id, amount, location, transaction_type, time_of_day,
  distance_from_home, is_fraud`) — it predates the current generator, which
  emits 3,200 rows with the full 12 raw inputs.
- Consequently the shipped model trained with the newer raw features
  (`device_trust_score`, `failed_attempts_24h`, …) falling back to
  `DEFAULT_TRANSACTION` defaults on most rows. This is a real limitation, not a
  bug in the pipeline: `build_feature_frame` is intentionally total (fills
  defaults), and the evaluation reproduces the committed metrics exactly.
- Proper fix (future work): regenerate a 15k-row full-schema dataset with the
  current generator scaled up, retrain, and re-evaluate. Do not compare these
  synthetic-data metrics against production fraud systems.

## Retraining

```bash
python backend/train_model.py   # script mode; overwrites backend/model.pkl + model_metrics.json
```

Deterministic given identical data + library versions (seed 42 everywhere,
stratified splits, pinned hyperparameters in `candidate_models()`), but it
**overwrites the committed artefact** — that is why CI evaluates instead of
retraining. After any retrain, re-run `python -m backend.evaluate` and commit
the refreshed `reports/model_evaluation.json` + `docs/model-evaluation.md`.

## Environment drift note

`requirements.txt` pins the 2024 stack (e.g. scikit-learn 1.4.2, fastapi
0.111). The local dev venv currently has newer versions (checked: sklearn 1.8,
fastapi 0.136) and everything passes there too, but the reproducible baseline
is **CI on Python 3.11 with the pinned files**.
