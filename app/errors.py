"""Translate database errors into clear HTTP responses."""
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Prefix raised by a trigger (or SQLite message fragment) -> HTTP status.
_RULES = [
    ("VENUE_CONFLICT", 409),
    ("NOT_APPROVED", 409),
    ("INVALID_STATUS", 422),
    ("INVALID_TRANSITION", 409),
    ("LOG_REQUIRED", 409),
    ("FORBIDDEN_REVIEWER", 403),
    ("FOREIGN KEY constraint failed", 409),
    ("UNIQUE constraint failed", 409),
    ("CHECK constraint failed", 422),
    ("NOT NULL constraint failed", 422),
]


def http_error_from(exc: Exception) -> HTTPException:
    message = str(getattr(exc, "orig", exc))
    for fragment, code in _RULES:
        if fragment in message:
            if fragment.startswith("FOREIGN KEY"):
                message = "Operation blocked by a foreign key: the record is referenced by other data or a referenced id does not exist"
            return HTTPException(status_code=code, detail=message)
    return HTTPException(status_code=400, detail=message)


def commit(db: Session) -> None:
    """Commit the current transaction; roll back and raise HTTP error on failure (NFR-05)."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise http_error_from(exc) from exc


def flush(db: Session) -> None:
    """Send pending changes inside the open transaction; roll back everything on failure."""
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise http_error_from(exc) from exc


def get_or_404(db: Session, model, obj_id: int):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{model.__tablename__} {obj_id} not found")
    return obj
