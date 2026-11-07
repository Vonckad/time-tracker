"""Time tracker web app — FastAPI entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.deps import get_db, set_db_path
from app.routers import employees, reports, timers
from app.services import AppError
from app.errors import validation_message, http_message

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    conn = get_db()
    try:
        init_db(conn, seed=True)
    finally:
        conn.close()
    yield


app = FastAPI(title="Time Tracker", version="1.0.0", lifespan=lifespan)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    # Never leak raw pydantic error lists to the UI: one readable Russian message.
    return JSONResponse(status_code=422, content={"detail": validation_message(exc.errors())})


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": http_message(exc.status_code, exc.detail)},
        headers=getattr(exc, "headers", None),
    )


app.include_router(employees.router)
app.include_router(timers.router)
app.include_router(reports.router)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/favicon.ico", include_in_schema=False)
@app.get("/apple-touch-icon.png", include_in_schema=False)
@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
def empty_icon():
    """Empty icon responses so browsers stop logging 404s."""
    return Response(status_code=204)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


def create_app(db_path: str | Path | None = None) -> FastAPI:
    """Factory used by tests to point at a temp database."""
    if db_path is not None:
        set_db_path(db_path)
    return app
