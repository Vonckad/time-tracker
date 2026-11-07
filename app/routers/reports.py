from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
import sqlite3

from app.deps import get_db
from app.services import AppError, report

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/period")
def api_period_report(
    from_: str = Query(..., alias="from", description="Period start (ISO-8601)"),
    to: str = Query(..., description="Period end (ISO-8601)"),
    conn: sqlite3.Connection = Depends(get_db),
):
    try:
        return report(conn, from_, to)
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
    finally:
        conn.close()
