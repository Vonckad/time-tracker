from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
import sqlite3

from app.deps import get_db
from app.services import AppError, create_employee, delete_employee, employee_board, list_employees, move_employee

router = APIRouter(prefix="/api/employees", tags=["employees"])


class EmployeeCreate(BaseModel):
    name: str = ""
    title: Optional[str] = Field(None, max_length=200)


class EmployeeMove(BaseModel):
    to_index: int = Field(..., ge=0)


@router.get("")
def api_list_employees(
    include_deleted: bool = Query(False),
    conn: sqlite3.Connection = Depends(get_db),
):
    try:
        return list_employees(conn, include_deleted=include_deleted)
    finally:
        conn.close()


@router.get("/board")
def api_employee_board(
    page: int = Query(1, ge=1),
    per_page: int = Query(10),
    conn: sqlite3.Connection = Depends(get_db),
):
    try:
        return employee_board(conn, page=page, per_page=per_page)
    except AppError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=e.status_code, detail=e.message) from e
    finally:
        conn.close()


@router.post("/{employee_id}/move")
def api_move_employee(employee_id: int, body: EmployeeMove, conn: sqlite3.Connection = Depends(get_db)):
    try:
        return move_employee(conn, employee_id, body.to_index)
    except AppError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=e.status_code, detail=e.message) from e
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
