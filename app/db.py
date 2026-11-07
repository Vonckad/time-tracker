"""SQLite persistence for the time tracker."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "time_tracker.db"

_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    title TEXT,
    deleted INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1)),
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS time_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    description TEXT NOT NULL,
    start_ts TEXT NOT NULL,
    end_ts TEXT,
    duration_seconds INTEGER,
    CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
    CHECK (
        (end_ts IS NULL AND duration_seconds IS NULL)
        OR (end_ts IS NOT NULL AND duration_seconds IS NOT NULL)
    )
);

-- At most one active timer per employee (end_ts IS NULL).
CREATE UNIQUE INDEX IF NOT EXISTS ux_one_active_timer
    ON time_entries(employee_id)
    WHERE end_ts IS NULL;
"""

_SEED = [
    ("Anna Petrova", "Designer"),
    ("Boris Ivanov", "Developer"),
    ("Anna Petrova", "QA Engineer"),  # duplicate name for color demo
]


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection, seed: bool = True) -> None:
    conn.executescript(_SCHEMA)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(employees)").fetchall()}
    if "position" not in cols:
        # Migration for databases created before manual ordering existed.
        conn.execute("ALTER TABLE employees ADD COLUMN position INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE employees SET position = id")
    if seed:
        row = conn.execute("SELECT COUNT(*) AS c FROM employees").fetchone()
        if row["c"] == 0:
            conn.executemany(
                "INSERT INTO employees (name, title) VALUES (?, ?)",
                _SEED,
            )
            conn.execute("UPDATE employees SET position = id")
    conn.commit()


@contextmanager
def get_connection(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
