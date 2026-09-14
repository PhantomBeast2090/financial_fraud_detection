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
pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
# docs: http://localhost:8000/docs | health: http://localhost:8000/health
docker-compose up --build  # api:8000 + nginx frontend:3000
```
- No test runner configured. If you add code, smoke-test imports + `/health` + relevant router.
- Seeded logins: `admin/admin123` (admin), `demo/demo1234` (user).

## Code rules
- Backend: FastAPI + SQLAlchemy 2.0 + Pydantic v2. Per-request sessions, typed schemas, `HTTPException` with proper codes.
- Auth: JWT via `backend/auth.py`; admin-only routes must enforce `role == "admin"`.
- Rate limits (slowapi): global 200/min, predict 60/min, train 3/hour — keep them.
- Frontend: vanilla JS/CSS, `fetch` to `http://localhost:8000`, JWT from localStorage, no framework without approval.
- Never commit: `.env`, `*.db*`, `*.log`, `.venv/`, `__pycache__/`, `.DS_Store` — `.gitignore` already covers these.

## Commit rules
- Single author only: `Rakshan_Adithyaa <rakshanadithyaa@gmail.com>`.
- Conventional commits: `feat:`, `fix:`, `refactor:`, `chore:`, `docs:`.
- Keep diffs minimal; update `PROJECT_CONTEXT.md` if architecture/API/ML contract changes.
