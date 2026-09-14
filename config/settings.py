"""
config/settings.py
Central configuration loaded from environment variables / .env file.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]


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
    SECRET_KEY: str = "fraudguard-super-secret-key-change-in-production-2024"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

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


settings = Settings()
