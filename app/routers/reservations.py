"""Reservation endpoints: double-booking prevention (FR-02) and audience overlap warnings (FR-04)."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.errors import commit, get_or_404

router = APIRouter(prefix="/reservations", tags=["Reservations"])


def audience_warnings(db: Session, event: models.EventProposal, start: datetime, end: datetime) -> list[schemas.AudienceWarning]:
    """Approved events with the same target audience whose reservation overlaps [start, end)."""
    R, E = models.Reservation, models.EventProposal
    rows = db.execute(
        select(E.id, E.title, E.target_audience, R.start_time, R.end_time)
        .join(R, R.event_id == E.id)
        .where(
            E.id != event.id,
            E.status == "Approved",
            func.lower(E.target_audience) == event.target_audience.lower(),
            R.start_time < end,
            R.end_time > start,
        )
    ).all()
    return [
        schemas.AudienceWarning(
            message=f"Audience overlap: '{title}' also targets {aud} at the same time",
            other_event_id=eid, other_event_title=title, target_audience=aud,
            other_start_time=s, other_end_time=e,
        )
        for eid, title, aud, s, e in rows
    ]


@router.get("", response_model=list[schemas.ReservationOut], summary="List reservations")
def list_reservations(
    venue_id: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    db: Session = Depends(get_db),
):
    R = models.Reservation
    q = select(R).order_by(R.start_time)
    if venue_id:
        q = q.where(R.venue_id == venue_id)
    if start_time:
        q = q.where(R.end_time > start_time)
    if end_time:
        q = q.where(R.start_time < end_time)
    return db.scalars(q).all()


@router.get("/{reservation_id}", response_model=schemas.ReservationOut, summary="Get a reservation")
def get_reservation(reservation_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, models.Reservation, reservation_id)


@router.post("", response_model=schemas.ReservationCreated, status_code=201, summary="Reserve a venue for an approved event")
def create_reservation(payload: schemas.ReservationIn, db: Session = Depends(get_db)):
    event = get_or_404(db, models.EventProposal, payload.event_id)
    get_or_404(db, models.Venue, payload.venue_id)
    reservation = models.Reservation(**payload.model_dump())
    db.add(reservation)
    commit(db)  # trg_reservation_no_overlap_insert blocks double booking (FR-02)
    db.refresh(reservation)
    warnings = audience_warnings(db, event, payload.start_time, payload.end_time)
    return schemas.ReservationCreated(reservation=reservation, warnings=warnings)


@router.put("/{reservation_id}", response_model=schemas.ReservationCreated, summary="Move a reservation")
def update_reservation(reservation_id: int, payload: schemas.ReservationUpdate, db: Session = Depends(get_db)):
    r = get_or_404(db, models.Reservation, reservation_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(r, key, value)
    if r.end_time <= r.start_time:
        db.rollback()
        raise HTTPException(422, "end_time must be after start_time")
    commit(db)
    db.refresh(r)
    return schemas.ReservationCreated(reservation=r, warnings=audience_warnings(db, r.event, r.start_time, r.end_time))


@router.delete("/{reservation_id}", status_code=204, summary="Delete a reservation")
def delete_reservation(reservation_id: int, db: Session = Depends(get_db)):
    r = get_or_404(db, models.Reservation, reservation_id)
    db.delete(r)
    commit(db)
    return Response(status_code=204)
