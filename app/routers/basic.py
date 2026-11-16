"""CRUD endpoints for the catalog entities: organizations, users, venues, equipment."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.errors import commit, get_or_404


def crud_router(prefix: str, tag: str, model, schema_in, schema_update, schema_out, order_by) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])

    @router.get("", response_model=list[schema_out], summary=f"List {tag.lower()}")
    def list_items(db: Session = Depends(get_db)):
        return db.scalars(select(model).order_by(order_by)).all()

    @router.get("/{item_id}", response_model=schema_out, summary=f"Get one {tag.lower()} record")
    def get_item(item_id: int, db: Session = Depends(get_db)):
        return get_or_404(db, model, item_id)

    @router.post("", response_model=schema_out, status_code=201, summary=f"Create {tag.lower()} record")
    def create_item(payload: schema_in, db: Session = Depends(get_db)):
        obj = model(**payload.model_dump())
        db.add(obj)
        commit(db)
        db.refresh(obj)
        return obj

    @router.put("/{item_id}", response_model=schema_out, summary=f"Update {tag.lower()} record")
    def update_item(item_id: int, payload: schema_update, db: Session = Depends(get_db)):
        obj = get_or_404(db, model, item_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(obj, key, value)
        commit(db)
        db.refresh(obj)
        return obj

    @router.delete("/{item_id}", status_code=204, summary=f"Delete {tag.lower()} record")
    def delete_item(item_id: int, db: Session = Depends(get_db)):
        obj = get_or_404(db, model, item_id)
        db.delete(obj)
        commit(db)  # FK RESTRICT blocks deletes of referenced rows (NFR-04, TC-04)
        return Response(status_code=204)

    return router


organizations = crud_router(
    "/organizations", "Organizations", models.Organization,
    schemas.OrganizationIn, schemas.OrganizationUpdate, schemas.OrganizationOut, models.Organization.name,
)
users = crud_router(
    "/users", "Users", models.User,
    schemas.UserIn, schemas.UserUpdate, schemas.UserOut, models.User.full_name,
)
venues = crud_router(
    "/venues", "Venues", models.Venue,
    schemas.VenueIn, schemas.VenueUpdate, schemas.VenueOut, models.Venue.name,
)
equipment = crud_router(
    "/equipment", "Equipment", models.Equipment,
    schemas.EquipmentIn, schemas.EquipmentUpdate, schemas.EquipmentOut, models.Equipment.name,
)


@venues.get("/{item_id}/availability", response_model=schemas.Availability, summary="Check venue availability")
def venue_availability(
    item_id: int,
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    db: Session = Depends(get_db),
):
    """Uses idx_reservation_venue_time to look up overlapping bookings (NFR-02)."""
    get_or_404(db, models.Venue, item_id)
    R = models.Reservation
    conflicts = db.scalars(
        select(R.id).where(R.venue_id == item_id, R.start_time < end_time, R.end_time > start_time)
    ).all()
    return schemas.Availability(
        venue_id=item_id, start_time=start_time, end_time=end_time,
        available=not conflicts, conflicts=list(conflicts),
    )
