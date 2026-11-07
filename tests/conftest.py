from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.deps import set_db_path
from app.main import app


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    init_db(conn, seed=False)
    conn.close()
    set_db_path(path)
    # Force re-init flag
    import app.deps as deps

    deps._initialized = True
    return path


@pytest.fixture()
def client(db_path: Path) -> TestClient:
    return TestClient(app)


@pytest.fixture()
def conn(db_path: Path):
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()
