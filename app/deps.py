"""Shared FastAPI dependencies."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.db import DEFAULT_DB_PATH, connect, init_db

_db_path: Path = DEFAULT_DB_PATH
_initialized = False


def set_db_path(path: Path | str) -> None:
    global _db_path, _initialized
    _db_path = Path(path)
    _initialized = False


def get_db() -> sqlite3.Connection:
    global _initialized
    conn = connect(_db_path)
    if not _initialized:
        init_db(conn, seed=True)
        _initialized = True
    return conn
