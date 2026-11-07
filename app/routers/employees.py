from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
import sqlite3

from app.deps import get_db
from app.services import AppError, create_employee, delete_employee, list_employees

router = APIRouter(prefix="/api/employees", tags=["employees"])


class EmployeeCreate(BaseModel):
    name: str = Field(..., min_length=1)
    title: Optional[str] = None


@router.get("")
def api_list_employees(
    include_deleted: bool = Query(False),
    conn: sqlite3.Connection = Depends(get_db),
):
    try:
        return list_employees(conn, include_deleted=include_deleted)
    finally:
        conn.close()


@router.post("", status_code=201)
def api_create_employee(body: EmployeeCreate, conn: sqlite3.Connection = Depends(get_db)):
    try:
        return create_employee(conn, body.name, body.title)
    except AppError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=e.status_code, detail=e.message) from e
    finally:
        conn.close()


@router.delete("/{employee_id}")
def api_delete_employee(
    employee_id: int,
    with_history: bool = Query(False, description="If true, delete employee and all entries"),
    conn: sqlite3.Connection = Depends(get_db),
):
    try:
        return delete_employee(conn, employee_id, with_history=with_history)
    except AppError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=e.status_code, detail=e.message) from e
    finally:
        conn.close()
