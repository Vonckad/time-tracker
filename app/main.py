"""Time tracker web app — FastAPI entrypoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.deps import get_db, set_db_path
from app.routers import employees, reports, timers
from app.services import AppError

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Time Tracker", version="1.0.0")


@app.on_event("startup")
def on_startup() -> None:
    conn = get_db()
    try:
        init_db(conn, seed=True)
    finally:
        conn.close()


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


app.include_router(employees.router)
app.include_router(timers.router)
app.include_router(reports.router)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


def create_app(db_path: str | Path | None = None) -> FastAPI:
    """Factory used by tests to point at a temp database."""
    if db_path is not None:
        set_db_path(db_path)
    return app
