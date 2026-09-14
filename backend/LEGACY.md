# Legacy Flask prototype — DO NOT USE

`app.py` (Flask routes on port 5001) and `db.py` (raw-sqlite helpers) are the
pre-FastAPI prototype. They are **frozen**: kept for history only.

- The canonical application is `backend/main.py` (FastAPI). Nothing in
  `backend/`, `config/`, `tests/` or CI imports these files
  (enforced by `tests/test_regression.py::test_legacy_files_unreferenced_by_canonical_code`
  and `test_legacy_modules_not_imported_by_app`).
- Their bare imports (`from model import ...`, `from db import ...`) only work
  with `backend/` on `sys.path`; do not "fix" them — that would invite reuse.
- They are excluded from coverage and partially from lint (see `pyproject.toml`).
- Safe removal requires: no references (verified), a DB migration check for the
  legacy `Transaction`/`Prediction`/`Fraud_Alert` tables still present in
  `database/schema.sql`, and frontend independence (verified — the UI talks to
  `:8000` only). Until then, they stay.
