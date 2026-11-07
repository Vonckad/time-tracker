from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import sqlite3

from app.deps import get_db
from app.services import (
    AppError,
    get_entry,
    list_active_timers,
    start_timer,
    stop_timer,
    update_entry,
)

router = APIRouter(prefix="/api", tags=["timers"])


class StartBody(BaseModel):
    employee_id: int
    description: str = Field(..., min_length=1, max_length=500)


class StopBody(BaseModel):
    employee_id: int


class EditBody(BaseModel):
    description: str | None = Field(None, max_length=500)
    start: str | None = None
    end: str | None = None


@router.get("/timers/active")
def api_active(conn: sqlite3.Connection = Depends(get_db)):
    try:
        return list_active_timers(conn)
    finally:
        conn.close()


@router.post("/timers/start", status_code=201)
def api_start(body: StartBody, conn: sqlite3.Connection = Depends(get_db)):
    try:
        return start_timer(conn, body.employee_id, body.description)
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
    finally:
        conn.close()


@router.post("/timers/stop")
def api_stop(body: StopBody, conn: sqlite3.Connection = Depends(get_db)):
    try:
        return stop_timer(conn, body.employee_id)
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
    finally:
        conn.close()


@router.get("/entries/{entry_id}")
def api_get_entry(entry_id: int, conn: sqlite3.Connection = Depends(get_db)):
    try:
        entry = get_entry(conn, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Time entry not found")
        return entry
    finally:
        conn.close()


@router.patch("/entries/{entry_id}")
def api_edit_entry(entry_id: int, body: EditBody, conn: sqlite3.Connection = Depends(get_db)):
    try:
        return update_entry(
            conn,
            entry_id,
            description=body.description,
            start=body.start,
            end=body.end,
        )
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
    finally:
        conn.close()
