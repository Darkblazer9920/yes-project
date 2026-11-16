"""Database engine, session factory and SQLite-specific setup.

- Foreign keys are switched on for every connection (NFR-04).
- Business-rule triggers (FR-02, FR-03, FR-07) are installed by ``init_db``.
"""
import os

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.models import Base
from app.triggers import TRIGGERS

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/yes.db")


def make_engine(url: str = DATABASE_URL) -> Engine:
    if url.startswith("sqlite:///./"):
        os.makedirs(os.path.dirname(url.replace("sqlite:///", "")) or ".", exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - trivial
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")  # NFR-04
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.close()

    return engine


def init_db(engine: Engine) -> None:
    """Create tables, indexes and triggers (idempotent)."""
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for ddl in TRIGGERS:
            conn.execute(text(ddl))


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
