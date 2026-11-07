"""PRD-critical automated tests."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from app.services import (
    AppError,
    create_employee,
    delete_employee,
    list_active_timers,
    report,
    start_timer,
    stop_timer,
    update_entry,
)
from app.timeutil import to_iso


def _iso(dt: datetime) -> str:
    return to_iso(dt)


def test_empty_report(conn):
    create_employee(conn, "Alice")
    frm = datetime(2026, 1, 1, tzinfo=timezone.utc)
    to = datetime(2026, 1, 2, tzinfo=timezone.utc)
    result = report(conn, _iso(frm), _iso(to))
    assert result["entries"] == []
    assert result["per_employee"] == []
    assert result["total_hours"] == 0


def test_invalid_period_from_after_to(conn):
    create_employee(conn, "Alice")
    frm = datetime(2026, 1, 2, tzinfo=timezone.utc)
    to = datetime(2026, 1, 1, tzinfo=timezone.utc)
    try:
        report(conn, _iso(frm), _iso(to))
        assert False, "expected AppError"
    except AppError as e:
        assert "Неверный период" in e.message


def test_period_clipping(conn):
    emp = create_employee(conn, "Bob")
    # Entry 10:00–18:00; filter 12:00–15:00 → 3h in sum, real times shown
    start = datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 3, 10, 18, 0, tzinfo=timezone.utc)
    conn.execute(
        "INSERT INTO time_entries (employee_id, description, start_ts, end_ts, duration_seconds) "
        "VALUES (?, ?, ?, ?, ?)",
        (emp["id"], "Full day", _iso(start), _iso(end), 8 * 3600),
    )
    conn.commit()

    period_from = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    period_to = datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc)
    result = report(conn, _iso(period_from), _iso(period_to))

    assert len(result["entries"]) == 1
    entry = result["entries"][0]
    assert entry["start"] == _iso(start)
    assert entry["end"] == _iso(end)
    assert entry["clipped_seconds"] == 3 * 3600
    assert abs(result["total_hours"] - 3.0) < 1e-6
    assert abs(result["per_employee"][0]["total_hours"] - 3.0) < 1e-6


def test_active_timer_in_report_not_summed(conn):
    emp = create_employee(conn, "Cara")
    start = datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)
    conn.execute(
        "INSERT INTO time_entries (employee_id, description, start_ts, end_ts, duration_seconds) "
        "VALUES (?, ?, ?, NULL, NULL)",
        (emp["id"], "Still going", _iso(start)),
    )
    conn.commit()

    period_from = datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc)
    period_to = datetime(2026, 3, 10, 18, 0, tzinfo=timezone.utc)
    result = report(conn, _iso(period_from), _iso(period_to))
    assert len(result["entries"]) == 1
    assert result["entries"][0]["running"] is True
    assert result["entries"][0]["clipped_seconds"] is None
    assert result["total_hours"] == 0


def test_duplicate_start_rejected(conn):
    emp = create_employee(conn, "Dan")
    start_timer(conn, emp["id"], "Task A")
    try:
        start_timer(conn, emp["id"], "Task B")
        assert False, "expected AppError"
    except AppError as e:
        assert "уже запущен" in e.message


def test_duplicate_start_rejected_via_api(client, conn):
    r = client.post("/api/employees", json={"name": "Eve"})
    assert r.status_code == 201
    eid = r.json()["id"]
    r1 = client.post("/api/timers/start", json={"employee_id": eid, "description": "One"})
    assert r1.status_code == 201
    r2 = client.post("/api/timers/start", json={"employee_id": eid, "description": "Two"})
    assert r2.status_code == 400
    assert r2.json()["detail"] == "У сотрудника уже запущен таймер"


def test_concurrent_start_race(db_path):
    """Second concurrent start for same employee must be refused."""
    from app.db import connect, init_db
    from app.services import create_employee, start_timer

    # Prepare employee in shared DB
    setup = connect(db_path)
    init_db(setup, seed=False)
    emp = create_employee(setup, "Racey")
    eid = emp["id"]
    setup.close()

    results = []

    def attempt(i: int):
        c = connect(db_path)
        try:
            entry = start_timer(c, eid, f"race-{i}")
            return ("ok", entry["id"])
        except AppError as e:
            return ("err", e.message)
        finally:
            c.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(attempt, i) for i in range(8)]
        for f in as_completed(futs):
            results.append(f.result())

    oks = [r for r in results if r[0] == "ok"]
    errs = [r for r in results if r[0] == "err"]
    assert len(oks) == 1, results
    assert len(errs) == 7, results


def test_delete_stops_active_timer(conn):
    emp = create_employee(conn, "Frank")
    entry = start_timer(conn, emp["id"], "Busy")
    delete_employee(conn, emp["id"], with_history=False)
    row = conn.execute(
        "SELECT end_ts, duration_seconds FROM time_entries WHERE id = ?", (entry["id"],)
    ).fetchone()
    assert row["end_ts"] is not None
    assert row["duration_seconds"] is not None
    assert list_active_timers(conn) == []


def test_hard_delete_with_active_timer(conn):
    emp = create_employee(conn, "Frank2")
    start_timer(conn, emp["id"], "Busy")
    delete_employee(conn, emp["id"], with_history=True)
    assert conn.execute("SELECT COUNT(*) AS c FROM time_entries").fetchone()["c"] == 0


def test_duration_recalc_on_edit(conn):
    emp = create_employee(conn, "Gina")
    start = datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc)
    end = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
    cur = conn.execute(
        "INSERT INTO time_entries (employee_id, description, start_ts, end_ts, duration_seconds) "
        "VALUES (?, ?, ?, ?, ?)",
        (emp["id"], "Old", _iso(start), _iso(end), 7200),
    )
    conn.commit()
    entry_id = cur.lastrowid

    new_end = datetime(2026, 4, 1, 11, 30, tzinfo=timezone.utc)
    updated = update_entry(
        conn,
        entry_id,
        description="Updated",
        start=_iso(start),
        end=_iso(new_end),
    )
    assert updated["description"] == "Updated"
    assert updated["duration_seconds"] == int(3.5 * 3600)


def test_edit_end_before_start_error(conn):
    emp = create_employee(conn, "Hank")
    start = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    cur = conn.execute(
        "INSERT INTO time_entries (employee_id, description, start_ts, end_ts, duration_seconds) "
        "VALUES (?, ?, ?, ?, ?)",
        (emp["id"], "X", _iso(start), _iso(end), 7200),
    )
    conn.commit()
    try:
        update_entry(
            conn,
            cur.lastrowid,
            start=_iso(start),
            end=_iso(start - timedelta(hours=1)),
        )
        assert False, "expected AppError"
    except AppError as e:
        assert "раньше начала" in e.message


def test_edit_start_of_running_forbidden(conn):
    emp = create_employee(conn, "Ivy")
    entry = start_timer(conn, emp["id"], "Run")
    new_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    try:
        update_entry(conn, entry["id"], start=_iso(new_start))
        assert False, "expected AppError"
    except AppError as e:
        assert "идущего" in e.message


def test_stop_with_no_active(conn):
    emp = create_employee(conn, "Jake")
    try:
        stop_timer(conn, emp["id"])
        assert False, "expected AppError"
    except AppError as e:
        assert "нет запущенного" in e.message


def test_empty_name_rejected(client):
    r = client.post("/api/employees", json={"name": "   "})
    assert r.status_code == 400


def test_restart_after_stop_creates_new_entry(conn):
    emp = create_employee(conn, "Kate")
    first = start_timer(conn, emp["id"], "One")
    stopped = stop_timer(conn, emp["id"])
    assert stopped["id"] == first["id"]
    assert stopped["end"] is not None
    second = start_timer(conn, emp["id"], "Two")
    assert second["id"] != first["id"]
    assert second["running"] is True
    # old untouched
    row = conn.execute(
        "SELECT description, end_ts FROM time_entries WHERE id = ?", (first["id"],)
    ).fetchone()
    assert row["description"] == "One"
    assert row["end_ts"] is not None


def test_soft_delete_keeps_entries_with_label(conn):
    emp = create_employee(conn, "Leo")
    start = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
    conn.execute(
        "INSERT INTO time_entries (employee_id, description, start_ts, end_ts, duration_seconds) "
        "VALUES (?, ?, ?, ?, ?)",
        (emp["id"], "Kept", _iso(start), _iso(end), 3600),
    )
    conn.commit()
    delete_employee(conn, emp["id"], with_history=False)
    result = report(
        conn,
        _iso(datetime(2026, 5, 1, tzinfo=timezone.utc)),
        _iso(datetime(2026, 5, 2, tzinfo=timezone.utc)),
    )
    assert len(result["entries"]) == 1
    assert result["entries"][0]["employee_deleted"] is True
    assert "удалён" in result["entries"][0]["employee_display_name"]


def test_hard_delete_removes_entries(conn):
    emp = create_employee(conn, "Mia")
    start = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
    conn.execute(
        "INSERT INTO time_entries (employee_id, description, start_ts, end_ts, duration_seconds) "
        "VALUES (?, ?, ?, ?, ?)",
        (emp["id"], "Gone", _iso(start), _iso(end), 3600),
    )
    conn.commit()
    delete_employee(conn, emp["id"], with_history=True)
    result = report(
        conn,
        _iso(datetime(2026, 5, 1, tzinfo=timezone.utc)),
        _iso(datetime(2026, 5, 2, tzinfo=timezone.utc)),
    )
    assert result["entries"] == []
    assert conn.execute("SELECT COUNT(*) AS c FROM employees WHERE id = ?", (emp["id"],)).fetchone()["c"] == 0


def test_empty_description_is_russian_not_raw_json(client):
    eid = client.post("/api/employees", json={"name": "Lena"}).json()["id"]
    r = client.post("/api/timers/start", json={"employee_id": eid, "description": ""})
    assert r.status_code == 400
    assert r.json() == {"detail": "Введите описание задачи"}


def test_validation_errors_are_russian_strings(client):
    r = client.post("/api/timers/start", json={"description": "x"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, str)
    assert "Сотрудник" in detail
    r = client.post("/api/timers/start", json={"employee_id": "abc", "description": "x"})
    assert isinstance(r.json()["detail"], str)
    assert "числом" in r.json()["detail"]
    r = client.get("/api/nope")
    assert r.json()["detail"] == "Не найдено"


def test_board_pagination_and_active_timer(client, conn):
    ids = [client.post("/api/employees", json={"name": f"E{i}"}).json()["id"] for i in range(25)]
    start_timer(conn, ids[0], "Work")
    b = client.get("/api/employees/board?page=1&per_page=10").json()
    assert b["total"] == 25 and b["pages"] == 3 and len(b["items"]) == 10
    assert b["items"][0]["active_timer"]["description"] == "Work"
    assert b["items"][1]["active_timer"] is None
    b3 = client.get("/api/employees/board?page=3&per_page=10").json()
    assert len(b3["items"]) == 5
    assert len(client.get("/api/employees/board?per_page=50").json()["items"]) == 25
    r = client.get("/api/employees/board?per_page=7")
    assert r.status_code == 400
    assert "10, 20 или 50" in r.json()["detail"]


def test_move_employee_reorders(client):
    ids = [client.post("/api/employees", json={"name": n}).json()["id"] for n in "ABCD"]
    r = client.post(f"/api/employees/{ids[3]}/move", json={"to_index": 0})
    assert r.status_code == 200
    assert [e["name"] for e in r.json()] == ["D", "A", "B", "C"]
    client.post(f"/api/employees/{ids[3]}/move", json={"to_index": 99})
    names = [e["name"] for e in client.get("/api/employees").json()]
    assert names == ["A", "B", "C", "D"]
