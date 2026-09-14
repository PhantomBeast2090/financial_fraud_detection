# Testing

Run: `pytest` from the repo root (config in `pyproject.toml`).

- Full suite: **132 tests**, ~5s, isolated per-test SQLite files — no test
  touches the real `database/fraud_detection.db` (the app lifespan is never
  started by `TestClient` outside a context manager; the simulator's direct
  `SessionLocal` and the DB viewer's file path are monkeypatched).
- Coverage: `pytest --cov=backend --cov=config --cov-report=term-missing`
  → **85% total** (`ml_features`, `auth`, `settings`, `models_db` at 100%).
  Legacy `app.py`/`db.py` are excluded (frozen prototype).
- bcrypt is patched to 4 rounds in-process for speed; real-round hashing is
  still verified by `test_real_bcrypt_rounds_still_work`.
- `POST /api/model/train` is tested with the background worker **mocked**, so
  tests never overwrite `model.pkl`.

## Layout

| File | Covers |
|---|---|
| `tests/test_features.py` (33) | normalisation, clipping, invalid/NaN handling, all 6 derived features incl. boundary cases, categoricals, train↔inference contract |
| `tests/test_model.py` (13) | artefact loading, missing/corrupt/bare pickles, probability range, threshold rule, reasons, explanation envelope |
| `tests/test_train.py` (12) | dataset shape, stratified 9600/2400/3000 splits + determinism, candidate names/hyperparams, threshold bounds, scoring math, tiny end-to-end selection repeatability |
| `tests/test_api.py` (26) | root/health, register/login/me, 401/403s, predict happy path + 422s, persistence, admin-only delete, dashboard math, alerts resolve flow, CSV export, simulate (redirected DB), review approve/reject + guards, model info/status/history, train trigger (mocked) + 409, limiter wiring |
| `tests/test_db.py` (9) | table creation, user/txn/prediction/alert/review persistence, cascade delete, label filtering |
| `tests/test_security.py` (14) | hash roundtrip, JWT roundtrip/expiry/tamper, inactive user, RBAC, SECRET_KEY + credential env override, insecure-default warning, seeding disable flag |
| `tests/test_explain.py` (9) | risk buckets, factor sets for safe/risky payloads, explanation envelope, reasons↔factors consistency |
| `tests/test_evaluation.py` (6) | committed-numbers reproduction, confusion-matrix math, sweep monotonicity, report structure, CLI to temp dir |
| `tests/test_regression.py` (6) | single feature contract, legacy modules never imported, no legacy imports in canonical code, no legacy response keys, single threshold source |
| `tests/test_db_viewer.py` (4) | table listing, pagination, whitelist rejection, auth required |

## What is NOT covered by unit tests (by design)

- Full retraining (minutes of CPU; would overwrite the committed artefact).
  Validated instead by `python -m backend.evaluate` (CI runs it to `/tmp`).
- The SSE `/api/simulate/stream` infinite endpoint (covered: `POST /api/simulate/one`
  shares its `_process_and_store` path).
- Browser/JS behaviour — vanilla frontend, manually verified against `:8000`.
