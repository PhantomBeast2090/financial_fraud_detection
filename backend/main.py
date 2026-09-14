"""
backend/main.py
FastAPI application entry-point with middleware, CORS, rate-limiting, and startup.
"""
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# ── Path setup (project root must be importable) ──────────────────────────────
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import settings
from backend.database import Base, engine
from backend.routers import auth_router, transaction_router, analytics_router, model_router, simulate_router, review_router, db_viewer_router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(ROOT_DIR / "server.log"),
    ],
)
logger = logging.getLogger("fraudguard")

# ── Rate Limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables and seed a default admin user on first run."""
    logger.info("🚀 Starting %s v%s ...", settings.APP_NAME, settings.APP_VERSION)
    Base.metadata.create_all(bind=engine)
    _seed_default_users()
    logger.info("✅ Database tables ready")
    yield
    logger.info("🛑 Shutting down")


def _seed_default_users():
    """Create admin + demo user if they don't already exist."""
    from sqlalchemy.orm import Session
    from backend.auth import hash_password
    from backend.models_db import User

    with Session(engine) as db:
        if not db.query(User).filter(User.username == "admin").first():
            db.add(User(
                username="admin",
                email="admin@fraudguard.ai",
                hashed_password=hash_password("admin123"),
                role="admin",
            ))
            logger.info("🔑 Seeded admin user (admin / admin123)")

        if not db.query(User).filter(User.username == "demo").first():
            db.add(User(
                username="demo",
                email="demo@fraudguard.ai",
                hashed_password=hash_password("demo1234"),
                role="user",
            ))
            logger.info("🔑 Seeded demo user (demo / demo1234)")

        db.commit()


# ── App Factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Production-grade ML-powered Financial Fraud Detection API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS – allow any localhost origin in dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8080",
        "null",  # file:// origin for local HTML
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global error handler ──────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "error": str(exc)},
    )


# ── Request logging middleware ────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info("→ %s %s", request.method, request.url.path)
    response = await call_next(request)
    logger.info("← %s %s %d", request.method, request.url.path, response.status_code)
    return response


# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(transaction_router)
app.include_router(analytics_router)
app.include_router(model_router)
app.include_router(simulate_router)
app.include_router(review_router)
app.include_router(db_viewer_router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
def health():
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/", tags=["System"])
def root():
    return {
        "message": f"Welcome to {settings.APP_NAME} API",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
