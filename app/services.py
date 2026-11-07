"""Business logic for employees, timers, reports."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from app.timeutil import duration_seconds, overlap_seconds, parse_iso, to_iso, utc_now


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ---- employees ----

def list_employees(conn: sqlite3.Connection, include_deleted: bool = False) -> list[dict]:
    if include_deleted:
        rows = conn.execute(
            "SELECT id, name, title, deleted FROM employees ORDER BY id"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name, title, deleted FROM employees WHERE deleted = 0 ORDER BY id"
        ).fetchall()
    return [_employee_dict(r) for r in rows]


def get_employee(conn: sqlite3.Connection, employee_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, name, title, deleted FROM employees WHERE id = ?",
        (employee_id,),
    ).fetchone()
    return _employee_dict(row) if row else None


def create_employee(conn: sqlite3.Connection, name: str, title: str | None = None) -> dict:
    cleaned = (name or "").strip()
    if not cleaned:
        raise AppError("Employee name is required (empty or whitespace-only not allowed)")
    title_cleaned = (title or "").strip() or None
    cur = conn.execute(
        "INSERT INTO employees (name, title, deleted) VALUES (?, ?, 0)",
        (cleaned, title_cleaned),
    )
    conn.commit()
    return get_employee(conn, cur.lastrowid)  # type: ignore[arg-type]


def delete_employee(
    conn: sqlite3.Connection,
    employee_id: int,
    with_history: bool,
) -> dict:
    emp = get_employee(conn, employee_id)
    if emp is None:
        raise AppError("Employee not found", 404)
    if emp["deleted"]:
        raise AppError("Employee is already deleted")

    active = conn.execute(
        "SELECT id FROM time_entries WHERE employee_id = ? AND end_ts IS NULL",
        (employee_id,),
    ).fetchone()
    if active:
        raise AppError("Cannot delete employee who has an active timer")

    if with_history:
        conn.execute("DELETE FROM time_entries WHERE employee_id = ?", (employee_id,))
        conn.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
        conn.commit()
        return {"deleted": True, "mode": "with_history", "id": employee_id}

    conn.execute("UPDATE employees SET deleted = 1 WHERE id = ?", (employee_id,))
    conn.commit()
    return {"deleted": True, "mode": "without_history", "id": employee_id, "employee": get_employee(conn, employee_id)}


# ---- timers / entries ----

def start_timer(conn: sqlite3.Connection, employee_id: int, description: str) -> dict:
    emp = get_employee(conn, employee_id)
    if emp is None or emp["deleted"]:
        raise AppError("Employee not found or deleted", 404)

    desc = (description or "").strip()
    if not desc:
        raise AppError("Task description is required")
    if len(desc) > 500:
        raise AppError("Task description must be at most 500 characters")

    start = to_iso(utc_now())
    try:
        cur = conn.execute(
            "INSERT INTO time_entries (employee_id, description, start_ts, end_ts, duration_seconds) "
            "VALUES (?, ?, ?, NULL, NULL)",
            (employee_id, desc, start),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        # Unique partial index: one active timer per employee
        raise AppError("Employee already has an active timer") from exc

    return get_entry(conn, cur.lastrowid)  # type: ignore[arg-type]


def stop_timer(conn: sqlite3.Connection, employee_id: int) -> dict:
    emp = get_employee(conn, employee_id)
    if emp is None:
        raise AppError("Employee not found", 404)

    row = conn.execute(
        "SELECT id, start_ts FROM time_entries WHERE employee_id = ? AND end_ts IS NULL",
        (employee_id,),
    ).fetchone()
    if row is None:
        raise AppError("No active timer for this employee")

    end_dt = utc_now()
    start_dt = parse_iso(row["start_ts"])
    dur = duration_seconds(start_dt, end_dt)
    end = to_iso(end_dt)
    conn.execute(
        "UPDATE time_entries SET end_ts = ?, duration_seconds = ? WHERE id = ?",
        (end, dur, row["id"]),
    )
    conn.commit()
    return get_entry(conn, row["id"])


def get_entry(conn: sqlite3.Connection, entry_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT e.id, e.employee_id, e.description, e.start_ts, e.end_ts, e.duration_seconds,
               emp.name AS employee_name, emp.deleted AS employee_deleted
        FROM time_entries e
        JOIN employees emp ON emp.id = e.employee_id
        WHERE e.id = ?
        """,
        (entry_id,),
    ).fetchone()
    return _entry_dict(row) if row else None


def list_active_timers(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT e.id, e.employee_id, e.description, e.start_ts, e.end_ts, e.duration_seconds,
               emp.name AS employee_name, emp.deleted AS employee_deleted
        FROM time_entries e
        JOIN employees emp ON emp.id = e.employee_id
        WHERE e.end_ts IS NULL
        ORDER BY e.start_ts
        """
    ).fetchall()
    return [_entry_dict(r) for r in rows]


def update_entry(
    conn: sqlite3.Connection,
    entry_id: int,
    description: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    row = conn.execute(
        "SELECT id, employee_id, description, start_ts, end_ts, duration_seconds FROM time_entries WHERE id = ?",
        (entry_id,),
    ).fetchone()
    if row is None:
        raise AppError("Time entry not found", 404)

    is_running = row["end_ts"] is None
    new_desc = row["description"] if description is None else description.strip()
    if description is not None:
        if not new_desc:
            raise AppError("Task description is required")
        if len(new_desc) > 500:
            raise AppError("Task description must be at most 500 characters")

    new_start_iso = row["start_ts"] if start is None else to_iso(parse_iso(start))
    new_end_iso = row["end_ts"] if end is None else to_iso(parse_iso(end))

    if is_running:
        if start is not None:
            raise AppError("Editing start of a still-running timer is forbidden")
        if end is not None:
            # closing via edit is not the intended path; reject to keep stop_timer as the only closer
            raise AppError("Cannot set end on a running timer via edit; use stop instead")
        conn.execute(
            "UPDATE time_entries SET description = ? WHERE id = ?",
            (new_desc, entry_id),
        )
        conn.commit()
        return get_entry(conn, entry_id)  # type: ignore[arg-type]

    # Closed entry: may edit description, start, end
    if new_end_iso is None:
        raise AppError("Closed entry must have an end time")

    start_dt = parse_iso(new_start_iso)
    end_dt = parse_iso(new_end_iso)
    if end_dt < start_dt:
        raise AppError("End must not be before start")

    dur = duration_seconds(start_dt, end_dt)
    conn.execute(
        "UPDATE time_entries SET description = ?, start_ts = ?, end_ts = ?, duration_seconds = ? WHERE id = ?",
        (new_desc, new_start_iso, new_end_iso, dur, entry_id),
    )
    conn.commit()
    return get_entry(conn, entry_id)  # type: ignore[arg-type]


# ---- reports ----

def report(
    conn: sqlite3.Connection,
    period_from: str,
    period_to: str,
) -> dict[str, Any]:
    try:
        from_dt = parse_iso(period_from)
        to_dt = parse_iso(period_to)
    except ValueError as exc:
        raise AppError(f"Invalid datetime: {exc}") from exc

    if from_dt > to_dt:
        raise AppError("Invalid period: 'from' must not be after 'to'")

    # Entries that overlap the period (including active ones that started before/during)
    rows = conn.execute(
        """
        SELECT e.id, e.employee_id, e.description, e.start_ts, e.end_ts, e.duration_seconds,
               emp.name AS employee_name, emp.deleted AS employee_deleted
        FROM time_entries e
        JOIN employees emp ON emp.id = e.employee_id
        WHERE e.start_ts <= ?
          AND (e.end_ts IS NULL OR e.end_ts >= ?)
        ORDER BY e.employee_id, e.start_ts
        """,
        (to_iso(to_dt), to_iso(from_dt)),
    ).fetchall()

    entries_out: list[dict] = []
    sums: dict[int, float] = {}
    names: dict[int, dict] = {}

    for row in rows:
        entry = _entry_dict(row)
        start_dt = parse_iso(row["start_ts"])
        end_dt = parse_iso(row["end_ts"]) if row["end_ts"] else None
        clipped = overlap_seconds(start_dt, end_dt, from_dt, to_dt)

        item = {
            **entry,
            "running": end_dt is None,
            "clipped_seconds": clipped,  # None if running
            "clipped_hours": None if clipped is None else round(clipped / 3600.0, 4),
        }
        # Active: show as running, do NOT include in sum
        # Closed with 0 overlap: skip from list? PRD says "if entry overlaps period, show it"
        # Zero overlap shouldn't appear due to SQL, but inclusive edge cases may yield 0.
        if end_dt is not None and clipped == 0:
            continue

        entries_out.append(item)
        eid = row["employee_id"]
        names[eid] = {
            "employee_id": eid,
            "employee_name": entry["employee_name"],
            "employee_deleted": entry["employee_deleted"],
        }
        if clipped is not None:
            sums[eid] = sums.get(eid, 0.0) + clipped / 3600.0

    per_employee = []
    for eid, meta in sorted(names.items(), key=lambda x: x[0]):
        hours = round(sums.get(eid, 0.0), 4)
        per_employee.append({**meta, "total_hours": hours})

    # Also include employees with entries that were filtered? Already covered.
    # Empty period → empty list and 0h
    total_hours = round(sum(p["total_hours"] for p in per_employee), 4)

    return {
        "from": to_iso(from_dt),
        "to": to_iso(to_dt),
        "entries": entries_out,
        "per_employee": per_employee,
        "total_hours": total_hours,
    }


def _employee_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "title": row["title"],
        "deleted": bool(row["deleted"]),
    }


def _entry_dict(row: sqlite3.Row) -> dict:
    deleted = bool(row["employee_deleted"])
    name = row["employee_name"]
    display = f"{name} (удалён)" if deleted else name
    return {
        "id": row["id"],
        "employee_id": row["employee_id"],
        "employee_name": name,
        "employee_display_name": display,
        "employee_deleted": deleted,
        "description": row["description"],
        "start": row["start_ts"],
        "end": row["end_ts"],
        "duration_seconds": row["duration_seconds"],
        "running": row["end_ts"] is None,
    }
