# FraudGuard AI — Project Context

> Source of truth for humans and AI agents. Verified against code 2026-09-14.
> Owner / sole contributor: **Rakshan_Adithyaa** <rakshanadithyaa@gmail.com>

## 1. What this is
Production-oriented full-stack ML **prototype** ("FraudGuard AI" v2.0.0) for
transaction fraud triage — NOT a production system (synthetic data; see §8):
- **Backend:** FastAPI (`backend/main.py`, `:8000`), JWT auth, enforced
  rate limits, 7 routers, SQLite via SQLAlchemy 2.0.
- **ML:** `BalancedLogisticRegression-v2`, 17 features, operating threshold
  0.78. Held-out test (n=3000): acc 0.9873, prec 0.9734, rec 0.9071,
  F1 0.9391, ROC-AUC 0.9534, PR-AUC 0.9183 (FP 8, FN 30).
- **Frontend:** vanilla HTML/CSS/JS (`frontend/`, nginx `:3000`).
- **Quality:** 132 pytest tests (~5s, 85% coverage), ruff, GitHub Actions CI
  (py3.11, pinned reqs), reproducible `python -m backend.evaluate`.
- **Legacy:** `backend/app.py` + `backend/db.py` = frozen Flask prototype
  (see `backend/LEGACY.md`). Never import, extend, or "fix" them.

## 2. Tech stack
- Python ≥3.11 (CI 3.11; Dockerfile 3.11-slim). Pinned `requirements.txt`
  (fastapi 0.111, sklearn 1.4.2, …) + `requirements-dev.txt`
  (pytest 8.3.4, pytest-cov 6.0.0, httpx 0.27.0, ruff 0.8.4).
- FastAPI + Uvicorn + SQLAlchemy 2.0 + Pydantic v2 + pydantic-settings.
- Auth: bcrypt + python-jose (HS256). Limits: slowapi (global 200/min,
  predict 60/min, train 3/hour — ENFORCED via `backend/rate_limit.py`).
- ML: sklearn pipelines (one-hot + RobustScaler + calibrated classifier).
- Frontend: vanilla JS + Chart.js 4.4.2, SSE live feed, no framework.

## 3. Repo layout
```
├── backend/
│   ├── main.py  rate_limit.py  auth.py  database.py  models_db.py  schemas.py
│   ├── ml_features.py   # THE 17-feature contract (train == inference)
│   ├── model.py         # load_model_artifact() + predict_fraud() + reasons
│   ├── explain.py       # structured explanations (factors + disclaimer)
│   ├── train_model.py   # candidates, threshold rule, artefact writer
│   ├── evaluate.py      # python -m backend.evaluate (no retrain)
│   ├── model.pkl / model_metrics.json  # committed artefact (tracked)
│   ├── app.py db.py LEGACY.md          # frozen Flask prototype
│   └── routers/  auth|transaction|analytics|model|simulate|review|db_viewer
├── config/settings.py   # env-driven (.env); SECRET_KEY + demo creds overridable
├── dataset/  transactions.csv (15k×7, synthetic) + generate_data.py (3.2k full-schema)
├── database/  schema.sql setup_db.py  (live *.db* git-ignored)
├── frontend/  index.html app.js style.css
├── tests/ (132)  conftest + features|model|train|api|db|security|explain|evaluation|regression|db_viewer
├── docs/  architecture|model-evaluation|testing|security|reproducibility.md
├── reports/model_evaluation.json  # committed reproducible baseline
├── .github/workflows/ci.yml  pyproject.toml  requirements-dev.txt  .env.example
├── README.md  PROJECT_CONTEXT.md  AGENTS.md  Dockerfile  docker-compose.yml
```

## 4. Data / ML contract (verified)
- Raw (12) → derived (6) = **17 features** (`MODEL_FEATURE_COLUMNS`); committed
  `model_metrics.json` feature list is identical (contract test).
- Thresholds: model cut **0.78** (validation utility rule, clipped
  [0.35, 0.78]) vs app risk buckets High ≥0.85 / Medium ≥0.60 (independent).
- Splits: stratified 64/16/20 → 9600/2400/3000, seed 42. Threshold/threshold
  sweep use validation ONLY; test is held out (`backend/evaluate.py`).
- Retrain: `POST /api/model/train` (admin) → subprocess → `ModelRun` row →
  hot-reload. CI never retrains; it evaluates to `/tmp`.
- ⚠️ CSV/model skew: committed CSV (15k, 7 cols) predates generator (3.2k,
  full schema); newer raw features train on defaults. See
  `docs/reproducibility.md`. Any feature change must touch `ml_features.py` +
  `train_model.py` + `model.py` + `explain.py` + predict form together.

## 5. API (base `http://localhost:8000`)
System `/` `/health`; auth register/login/me (+ OAuth2 form for Swagger);
transactions predict (201) + list/get/delete (delete admin);
analytics dashboard/alerts(+resolve)/model-metrics/export-csv;
simulate one + SSE stream (`?token=`); review queue approve/reject;
model train/status/info/history (train+history admin); db tables/rows
(auth-only — known gap, see `docs/security.md`).

## 6. Run / verify (all runnable)
```bash
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
python -m uvicorn backend.main:app --reload --port 8000   # :8000/docs, :8000/health
docker-compose up --build                                 # api:8000 + UI:3000
pytest                                                    # 132 passed ~5s
pytest --cov=backend --cov=config --cov-report=term-missing  # 85%
ruff check backend config tests
python -m backend.evaluate                               # refresh reports/ + docs/model-evaluation.md
```
Seeded demo logins: `admin/admin123` (admin), `demo/demo1234` (user) —
env-overridable, `SEED_DEFAULT_USERS=false` disables.

## 7. Conventions
- Typed FastAPI + Pydantic schemas for all I/O; per-request sessions
  (simulator + train worker use their own sessions — documented).
- No raw sqlite in new code; no framework in frontend.
- Config only via `config/settings.py` + env. Never commit `.env`/`*.db*`/`*.log`.
- Commits: single author, conventional messages, no `Co-authored-by`.
- Small diffs; update this file + README when architecture/API/ML changes.

## 8. Do NOT
- Revive `app.py`/`db.py`; depend on them from tests/CI; "fix" their imports.
- Retrain in CI or commit regenerated `model.pkl` without re-running
  `evaluate` + refreshing `reports/` + `docs/model-evaluation.md`.
- Claim production performance: dataset is synthetic; report test metrics
  with the CSV-skew caveat.
- Weaken auth/RBAC/validation/rate limits; add k8s/kafka/redis/graphql.

## 9. Gaps / roadmap
- Regenerate 15k-row full-schema dataset + retrain + re-evaluate.
- Tighten DB viewer to admin-only (behavior change — needs UI sign-off).
- Lockout policy, token revocation, SECRET_KEY env-only (remove default).
- Cross-seed variance, calibration curves, frontend automated checks.
