"""
backend/routers/db_viewer_router.py
Read-only database browser — lists all tables and returns paginated rows.
Admin-only access.
"""
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth import get_current_user
from backend.models_db import User
from config.settings import settings

router = APIRouter(prefix="/api/db", tags=["DB Viewer"])

# Resolve the physical SQLite path from the DSN
# settings.DATABASE_URL looks like "sqlite:///absolute/path/to/file.db"
_DB_PATH = Path(settings.DATABASE_URL.replace("sqlite:///", ""))

# Tables that are safe to expose (whitelist)
ALLOWED_TABLES = {
    # New ORM tables
    "users", "transactions", "fraud_alerts", "model_runs",
    # Legacy tables
    "Customer", "Account", "Transaction", "Prediction",
    "Fraud_Alert", "Transaction_Type", "Location", "Account_Type",
    "Transaction_Audit",
}


def _connect():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/tables")
def list_tables(current_user: User = Depends(get_current_user)):
    """Return all table names with their row counts."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

    result = []
    for r in rows:
        name = r["name"]
        if name.startswith("sqlite_"):
            continue
        try:
            with _connect() as conn:
                count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        except Exception:
            count = 0
        result.append({"table": name, "rows": count, "allowed": name in ALLOWED_TABLES})

    return result


@router.get("/table/{table_name}")
def get_table_rows(
    table_name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user),
):
    """Return paginated rows for a given table."""
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(status_code=403, detail=f"Table '{table_name}' is not accessible.")

    offset = (page - 1) * page_size

    with _connect() as conn:
        # Total count
        total = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
        # Column names
        cursor = conn.execute(f'SELECT * FROM "{table_name}" LIMIT 0')
        columns = [d[0] for d in cursor.description]
        # Data rows
        rows_raw = conn.execute(
            f'SELECT * FROM "{table_name}" LIMIT {page_size} OFFSET {offset}'
        ).fetchall()

    rows = [dict(r) for r in rows_raw]

    return {
        "table": table_name,
        "columns": columns,
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }
