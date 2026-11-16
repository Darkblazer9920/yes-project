"""FastAPI application entry point for the Yachay Events System (YES)."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import engine, init_db
from app.routers import basic, proposals, reports, reservations

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db(engine)
    yield


app = FastAPI(
    title="Yachay Events System (YES) API",
    version="0.5.0",
    description="Event proposals, venue reservations and activity tracking for Yachay Tech student clubs.",
    lifespan=lifespan,
)

for r in (basic.organizations, basic.users, basic.venues, basic.equipment,
          proposals.router, reservations.router, reports.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health", tags=["Health"])
def health():
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")
