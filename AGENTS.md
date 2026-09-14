# AGENTS.md — Instructions for AI Coding Agents

Owner / sole contributor: **Rakshan_Adithyaa**. Never add `Co-authored-by` or other authors to commits.

## Canonical entry-points
- API: `backend/main.py` (`uvicorn backend.main:app --reload --port 8000`). This is the ONLY backend to modify.
- Legacy `backend/app.py` (Flask) + `backend/db.py` are frozen prototypes — read-only, do not extend.
- Config: `config/settings.py` (pydantic-settings, `.env` override). Never hardcode secrets.
- ML contract: `backend/ml_features.py` ↔ `backend/train_model.py` ↔ `backend/model.py` ↔ `frontend/` predict form must stay in sync (17 features, threshold 0.78).

## Build / run / verify
```bash
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # local demo defaults; never commit .env
python -m uvicorn backend.main:app --reload --port 8000
# docs: http://localhost:8000/docs | health: http://localhost:8000/health
docker-compose up --build  # api:8000 + nginx frontend:3000
pytest  # 132 tests, ~5s, isolated test DBs (never touches database/*.db)
pytest --cov=backend --cov=config --cov-report=term-missing
ruff check backend config tests
python -m backend.evaluate  # refresh reports/ + docs/model-evaluation.md
```
- Seeded logins: `admin/admin123` (admin), `demo/demo1234` (user) — env-overridable via `ADMIN_*`/`DEMO_*`, disable with `SEED_DEFAULT_USERS=false`.
- `POST /api/model/train` is admin-only and spawns a real subprocess — tests mock it; never trigger it casually (overwrites `model.pkl`).

## Code rules
- Backend: FastAPI + SQLAlchemy 2.0 + Pydantic v2. Per-request sessions, typed schemas, `HTTPException` with proper codes.
- Auth: JWT via `backend/auth.py`; admin-only routes must enforce `role == "admin"`.
- Rate limits (slowapi, shared `backend/rate_limit.py`): global 200/min, predict 60/min, train 3/hour — enforced on routes, covered by `test_rate_limit_config_wired`. Do not weaken.
- ML: single feature contract `backend/ml_features.py` (17 cols) shared by train/inference; threshold 0.78 from validation only; explanations via `backend/explain.py` (heuristic, non-causal — never claim causality).
- Frontend: vanilla JS/CSS, `fetch` to `http://localhost:8000`, JWT from localStorage, no framework without approval.
- Never commit: `.env`, `*.db*`, `*.log`, `.venv/`, `__pycache__/`, `.DS_Store` — `.gitignore` already covers these.

## Commit rules
- Single author only: `Rakshan_Adithyaa <rakshanadithyaa@gmail.com>`.
- Conventional commits: `feat:`, `fix:`, `refactor:`, `chore:`, `docs:`.
- Keep diffs minimal; update `PROJECT_CONTEXT.md` if architecture/API/ML contract changes.
