"""
backend/routers/model_router.py
Model training trigger and status endpoints.
"""
import json
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth import require_admin
from backend.database import get_db
from backend.models_db import ModelRun, User
from backend.schemas import TrainResponse
from config.settings import settings

router = APIRouter(prefix="/api/model", tags=["Model"])

_training_status: dict = {"running": False, "last_result": None}


def _run_training(db_url_hint: str, trained_by: str):
    """Background task: re-train model and persist metrics to DB."""
    _training_status["running"] = True
    try:
        root = Path(__file__).resolve().parents[2]
        script = root / "backend" / "train_model.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            cwd=str(root),
        )
        if result.returncode != 0:
            _training_status["last_result"] = {
                "success": False,
                "error": result.stderr[-2000:],
            }
            return

        # Read freshly written metrics
        if settings.METRICS_PATH.exists():
            raw = json.loads(settings.METRICS_PATH.read_text())
            tm = raw.get("test_metrics", {})

            from backend.database import SessionLocal
            with SessionLocal() as session:
                run = ModelRun(
                    model_name=raw.get("model_name", "Unknown"),
                    model_version=raw.get("model_version", "v2"),
                    accuracy=tm.get("accuracy"),
                    precision=tm.get("precision"),
                    recall=tm.get("recall"),
                    f1_score=tm.get("f1"),
                    roc_auc=tm.get("roc_auc"),
                    threshold=raw.get("threshold"),
                    training_rows=raw.get("training_rows"),
                    metrics_json=json.dumps(raw),
                    trained_by=trained_by,
                )
                session.add(run)
                session.commit()

            _training_status["last_result"] = {
                "success": True,
                "model_name": raw.get("model_name"),
                "model_version": raw.get("model_version"),
                "test_metrics": tm,
            }

        # Hot-reload the in-memory model so new predictions use latest weights
        import importlib
        import backend.model as model_module
        importlib.reload(model_module)

    except Exception as exc:
        _training_status["last_result"] = {"success": False, "error": str(exc)}
    finally:
        _training_status["running"] = False


@router.post("/train", response_model=dict)
def trigger_training(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Kick off async model re-training (admin only).
    Returns immediately; poll /api/model/status for progress.
    """
    if _training_status["running"]:
        raise HTTPException(status_code=409, detail="Training already in progress")

    background_tasks.add_task(_run_training, settings.DATABASE_URL, admin.username)
    return {"success": True, "message": "Model training started in background. Poll /api/model/status."}


@router.get("/status")
def training_status():
    """Return current training state."""
    return {
        "running": _training_status["running"],
        "last_result": _training_status["last_result"],
    }


@router.get("/info")
def model_info():
    """Return loaded model metadata without re-querying the DB."""
    from backend.model import get_model_metadata
    return get_model_metadata()


@router.get("/history")
def training_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Return all historical model training runs (admin only)."""
    runs = db.query(ModelRun).order_by(ModelRun.trained_at.desc()).all()
    return [
        {
            "id": r.id,
            "model_name": r.model_name,
            "model_version": r.model_version,
            "accuracy": r.accuracy,
            "precision": r.precision,
            "recall": r.recall,
            "f1_score": r.f1_score,
            "roc_auc": r.roc_auc,
            "threshold": r.threshold,
            "training_rows": r.training_rows,
            "trained_by": r.trained_by,
            "trained_at": r.trained_at.isoformat() if r.trained_at else None,
        }
        for r in runs
    ]
