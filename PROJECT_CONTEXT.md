# FraudGuard AI — Project Context

> Single source of truth for humans and AI agents working in this repo.
> Owner / sole contributor: **Rakshan_Adithyaa** <rakshanadithyaa@gmail.com>

## 1. What this is
Production-grade ML-powered **Financial Fraud Detection** platform ("FraudGuard AI" v2.0.0):
- **Backend:** FastAPI (`backend/main.py`) with JWT auth, rate-limiting, 7 routers, SQLite via SQLAlchemy.
- **ML:** BalancedLogisticRegression (v2) + leaderboard (ExtraTrees / RandomForest), 17 engineered features, threshold 0.78. Test F1 ~0.939, ROC-AUC ~0.953.
- **Frontend:** Vanilla HTML/CSS/JS dashboard (`frontend/`) served via nginx (port 3000) — login, dashboard, predict, analytics, alerts, review queue, DB viewer, admin.
- **Legacy:** `backend/app.py` is an old Flask prototype (port 5001). **Do not use** — FastAPI in `backend/main.py` is canonical.

## 2. Tech stack
- Python 3.11, FastAPI 0.111, Uvicorn, SQLAlchemy 2.0, Pydantic v2 + pydantic-settings
- Auth: python-jose + passlib[bcrypt]; Rate limit: slowapi
- ML: scikit-learn 1.4.2, xgboost 2.0.3, imbalanced-learn, pandas, numpy, joblib
- Viz: matplotlib, seaborn (backend) + Chart.js 4.4.2 (frontend)
- Infra: Docker + docker-compose (api:8000, frontend:3000), SQLite file DB
- No test suite yet. No CI yet.

## 3. Repo layout
```
financial_fraud_detection/
├── backend/
│   ├── main.py            # FastAPI entry-point (CANONICAL)
│   ├── app.py             # LEGACY Flask prototype — ignore
│   ├── auth.py            # JWT + bcrypt helpers
│   ├── database.py        # engine / Session / Base (imports DATABASE_URL from config)
│   ├── db.py              # legacy sqlite helper for Flask app
│   ├── models_db.py       # SQLAlchemy User / Transaction / Prediction / Alert models
│   ├── schemas.py         # Pydantic request/response schemas
│   ├── ml_features.py     # 17-feature engineering (must match train + inference)
│   ├── model.py           # load model.pkl / predict_fraud()
│   ├── train_model.py     # retraining + leaderboard + metrics json
│   ├── model.pkl / encoders.pkl / model_metrics.json  # tracked demo artefacts
│   └── routers/           # auth, transaction, analytics, model, simulate, review, db_viewer
├── config/settings.py     # BaseSettings (.env override); APP_NAME, SECRET_KEY, thresholds
├── dataset/generate_data.py + transactions.csv  # synthetic 15k rows, 10.8% fraud
├── database/schema.sql + setup_db.py + dbms_project_review.sql  # SQL sources of truth
├── frontend/index.html + app.js + style.css  # vanilla SPA, talks to :8000
├── requirements.txt / Dockerfile / docker-compose.yml
├── PROJECT_CONTEXT.md / AGENTS.md / .gitignore
```

## 4. Data / ML contract
- Raw inputs: amount, location, transaction_type, time_of_day, distance_from_home, device_trust_score, failed_attempts_24h, txn_velocity_1h, merchant_risk_score, is_international, card_present
- Engineered (`ml_features.py`): amount_log, night_risk, distance_amount_pressure, trust_gap, velocity_pressure, cross_border_card_not_present (+ one-hot via encoders.pkl)
- Thresholds: `FRAUD_HIGH_THRESHOLD=0.85`, `FRAUD_MEDIUM_THRESHOLD=0.60`, model decision threshold `0.78` (see `model_metrics.json`)
- Retrain flow: `POST /model/retrain` (admin, 3/hour limit) → background job → `GET /model/train-status` → updates `model.pkl` + `model_metrics.json`
- **Rule: any feature change must update `ml_features.py` + `train_model.py` + `model.py` + frontend predict form together.**

## 5. API surface (base `http://localhost:8000`)
- System: `GET /`, `GET /health`, `GET /docs`, `GET /redoc`
- Auth: routers/auth_router.py (seeded `admin/admin123`, `demo/demo1234`)
- Transactions / Predict / Analytics / Simulate / Review queue / DB viewer / Model admin — see `backend/routers/*.py`
- Rate limits: global 200/min; predict 60/min; train 3/hour
- CORS allows: localhost:3000, 127.0.0.1:3000, :5500, :8080, `null` (file://)

## 6. Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
# frontend: open frontend/index.html directly, or:
docker-compose up --build
# API → http://localhost:8000/docs, UI → http://localhost:3000
```
Default log file `server.log` is git-ignored. DB auto-creates on startup (`Base.metadata.create_all`) + seeds admin/demo.

## 7. Conventions
- Python: type hints, Pydantic schemas for all I/O, SQLAlchemy sessions per-request, no raw sqlite in new code (legacy `db.py` excepted).
- Frontend: no framework — vanilla JS `fetch` to `:8000`, JWT in localStorage, Chart.js for charts.
- Config only via `config/settings.py` + `.env` (never hardcode secrets; `SECRET_KEY` default must be overridden in prod).
- Commits: single author only (`Rakshan_Adithyaa`). No `Co-authored-by` trailers. Conventional messages (`feat:`, `fix:`, `chore:`).

## 8. What NOT to do
- Don't revive `backend/app.py` / `backend/db.py` Flask code.
- Don't commit `.env`, `*.db*`, `*.log`, `.venv/`, `__pycache__/`, `.DS_Store` (see `.gitignore`).
- Don't change feature engineering in one place only — keep train/inference/UI in sync.
- Don't lower auth/rate-limit protections without explicit approval.

## 9. Roadmap / known gaps
- [ ] Add pytest suite + CI
- [ ] Move `SECRET_KEY` to env-only + add `.env.example`
- [ ] Postgres migration path (currently `DATABASE_URL` sqlite default)
- [ ] Remove legacy Flask files once verified unused
- [ ] Add pagination tests for DB viewer + review queue
