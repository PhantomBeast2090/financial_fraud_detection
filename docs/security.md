# Security

## Authentication & authorisation

- Passwords: bcrypt (`backend/auth.py`). JWT (HS256) via python-jose, 60-min
  expiry, `sub` = username. `get_current_user` rejects unknown/inactive users;
  `require_admin` gates `/api/model/train`, `/api/model/history`.
- Route-level admin checks also exist on transaction delete and alert resolve
  (explicit `role != "admin"` → 403). Tested in `tests/test_security.py` +
  `tests/test_api.py`.

## Secrets handling (fixed in this pass)

- `SECRET_KEY`, admin/demo bootstrap credentials, and `ACCESS_TOKEN_EXPIRE_MINUTES`
  are environment-controlled (`config/settings.py` + `.env`; see `.env.example`).
- Built-in defaults exist **for local demo only**. With `DEBUG=false` and
  defaults still in place, startup emits a `RuntimeWarning`
  (`warn_if_insecure_defaults`) and seeding logs an explicit warning.
- `SEED_DEFAULT_USERS=false` disables bootstrap-user creation entirely
  (recommended for any non-local deployment). `.env` is git-ignored; only
  `.env.example` (dummy values) is committed.
- Tests: `test_secret_key_env_override`, `test_demo_credentials_env_override`,
  `test_insecure_defaults_warn`, `test_seeding_disabled_skips_db`.

## Rate limiting (fixed in this pass)

Previously the `60/minute` / `3/hour` settings existed but **no route enforced
them**. Now a shared limiter (`backend/rate_limit.py`, global `200/minute`)
backs the app, with per-route limits on `POST /api/transactions/predict`,
`POST /api/simulate/one` (`RATE_LIMIT_PREDICT`) and `POST /api/model/train`
(`RATE_LIMIT_TRAIN`). Wiring is asserted by
`test_rate_limit_config_wired` (shared instance identity).

## Known gaps (honest, not yet fixed)

- **DB viewer** (`GET /api/db/*`) requires authentication but not the admin
  role, despite its "Admin-only" docstring. Changing it would alter current UI
  behaviour, so it is documented here instead of silently tightened.
- No account lockout / password-complexity policy beyond min-length 6.
- JWT has no server-side revocation list; logout is client-side token discard.
- `SECRET_KEY` default is still present in code for demo convenience — rotation
  to env-only is a one-line follow-up once deployment is non-local.
