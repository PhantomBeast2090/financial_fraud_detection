"""
config/settings.py
Central configuration loaded from environment variables / .env file.

Secret handling policy (see docs/security.md):
- SECRET_KEY and the demo bootstrap credentials are environment-controlled.
- Built-in defaults exist ONLY for convenient local development.
- Production (DEBUG=false) MUST set SECRET_KEY + unique credentials; the app
  logs an explicit warning if the built-in defaults are still in use.
"""
import warnings
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]

# Built-in development default. Never use in production.
DEFAULT_SECRET_KEY = "fraudguard-super-secret-key-change-in-production-2024"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "FraudGuard AI"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = f"sqlite:///{ROOT_DIR}/database/fraud_detection.db"

    # ── JWT Auth ─────────────────────────────────────────────────────────────
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── Demo bootstrap users (seeded on startup, see backend/main.py) ─────────
    # Override via environment / .env. Set SEED_DEFAULT_USERS=false in prod.
    SEED_DEFAULT_USERS: bool = True
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    ADMIN_EMAIL: str = "admin@fraudguard.ai"
    DEMO_USERNAME: str = "demo"
    DEMO_PASSWORD: str = "demo1234"
    DEMO_EMAIL: str = "demo@fraudguard.ai"

    # ── ML Paths ─────────────────────────────────────────────────────────────
    MODEL_PATH: Path = ROOT_DIR / "backend" / "model.pkl"
    METRICS_PATH: Path = ROOT_DIR / "backend" / "model_metrics.json"
    DATA_PATH: Path = ROOT_DIR / "dataset" / "transactions.csv"

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_PREDICT: str = "60/minute"
    RATE_LIMIT_TRAIN: str = "3/hour"

    # ── Fraud Thresholds ──────────────────────────────────────────────────────
    FRAUD_HIGH_THRESHOLD: float = 0.85
    FRAUD_MEDIUM_THRESHOLD: float = 0.60

    @property
    def uses_default_secret(self) -> bool:
        """True when SECRET_KEY is still the built-in development default."""
        return self.SECRET_KEY == DEFAULT_SECRET_KEY

    @property
    def uses_default_demo_credentials(self) -> bool:
        """True when the bootstrap admin/demo passwords are still defaults."""
        return self.ADMIN_PASSWORD == "admin123" or self.DEMO_PASSWORD == "demo1234"

    def warn_if_insecure_defaults(self) -> None:
        """Emit a loud warning when dev defaults are used outside debug mode."""
        if not self.DEBUG and (self.uses_default_secret or self.uses_default_demo_credentials):
            warnings.warn(
                "INSECURE DEFAULTS: running with DEBUG=false while SECRET_KEY and/or "
                "demo credentials are still built-in defaults. Set SECRET_KEY, "
                "ADMIN_PASSWORD and DEMO_PASSWORD via environment/.env (see "
                ".env.example), or set SEED_DEFAULT_USERS=false in production.",
                RuntimeWarning,
                stacklevel=2,
            )


settings = Settings()
