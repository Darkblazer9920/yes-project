"""Event proposal endpoints: CRUD, lifecycle (FR-03), approval log (FR-07), equipment (M:N)."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.database import get_db
from app.errors import commit, flush, get_or_404

router = APIRouter(prefix="/proposals", tags=["Event proposals"])

EDITABLE_STATUSES = ("Draft", "Submitted")


def _detail(p: models.EventProposal) -> schemas.ProposalDetail:
    out = schemas.ProposalDetail.model_validate(p)
    out.reservation_id = p.reservation.id if p.reservation else None
    return out


def _check_equipment(db: Session, req: schemas.EquipmentRequest) -> None:
    item = get_or_404(db, models.Equipment, req.equipment_id)
    if req.quantity_requested > item.total_quantity:
        raise HTTPException(
            status_code=409,
            detail=f"Only {item.total_quantity} unit(s) of '{item.name}' exist; requested {req.quantity_requested}",
        )


@router.get("", response_model=list[schemas.ProposalOut], summary="List event proposals")
def list_proposals(
    status: schemas.Status | None = None,
    organization_id: int | None = None,
    target_audience: str | None = None,
    db: Session = Depends(get_db),
):
    q = select(models.EventProposal).order_by(models.EventProposal.id.desc())
    if status:
        q = q.where(models.EventProposal.status == status)
    if organization_id:
        q = q.where(models.EventProposal.organization_id == organization_id)
    if target_audience:
        q = q.where(models.EventProposal.target_audience == target_audience)
    return db.scalars(q).all()


@router.get("/{proposal_id}", response_model=schemas.ProposalDetail, summary="Get a proposal with equipment and logs")
def get_proposal(proposal_id: int, db: Session = Depends(get_db)):
    p = db.scalars(
        select(models.EventProposal)
        .where(models.EventProposal.id == proposal_id)
        .options(selectinload(models.EventProposal.equipment_items), selectinload(models.EventProposal.logs))
    ).first()
    if p is None:
        raise HTTPException(404, f"event_proposal {proposal_id} not found")
    return _detail(p)


@router.post("", response_model=schemas.ProposalDetail, status_code=201, summary="Create a proposal (atomic with equipment)")
def create_proposal(payload: schemas.ProposalIn, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude={"equipment"})
    proposal = models.EventProposal(**data)
    db.add(proposal)
    flush(db)
    for req in payload.equipment:
        _check_equipment(db, req)
        db.add(models.EventEquipment(event_id=proposal.id, **req.model_dump()))
    commit(db)  # proposal + equipment saved together or not at all (NFR-05)
    db.refresh(proposal)
    return _detail(proposal)


@router.put("/{proposal_id}", response_model=schemas.ProposalDetail, summary="Edit a proposal (Draft/Submitted only)")
def update_proposal(proposal_id: int, payload: schemas.ProposalUpdate, db: Session = Depends(get_db)):
    p = get_or_404(db, models.EventProposal, proposal_id)
    if p.status not in EDITABLE_STATUSES:
        raise HTTPException(409, f"Proposal in status {p.status} can no longer be edited")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(p, key, value)
    commit(db)
    db.refresh(p)
    return _detail(p)


@router.delete("/{proposal_id}", status_code=204, summary="Delete a Draft proposal")
def delete_proposal(proposal_id: int, db: Session = Depends(get_db)):
    p = get_or_404(db, models.EventProposal, proposal_id)
    if p.status != "Draft":
        raise HTTPException(409, "Only Draft proposals can be deleted; cancel it instead")
    db.delete(p)
    commit(db)
    return Response(status_code=204)


@router.post("/{proposal_id}/status", response_model=schemas.ProposalDetail, summary="Move a proposal through its lifecycle")
def change_status(proposal_id: int, payload: schemas.StatusChange, db: Session = Depends(get_db)):
    """Approved/Rejected require a reviewer: the log entry and the status change are one transaction."""
    p = get_or_404(db, models.EventProposal, proposal_id)
    if payload.status in ("Approved", "Rejected", "Under_Review"):
        if payload.reviewer_id is None:
            raise HTTPException(422, f"reviewer_id is required to set status {payload.status}")
    if payload.reviewer_id is not None:
        get_or_404(db, models.User, payload.reviewer_id)
        db.add(models.ApprovalLog(
            event_id=p.id, reviewer_id=payload.reviewer_id,
            new_status=payload.status, comments=payload.comments,
        ))
        flush(db)
    if payload.status == "Canceled" and p.reservation is not None:
        db.delete(p.reservation)  # free the venue
        flush(db)
    p.status = payload.status
    commit(db)  # triggers validate the transition (FR-03) and the log (FR-07)
    db.refresh(p)
    return _detail(p)


@router.get("/{proposal_id}/logs", response_model=list[schemas.ApprovalLogOut], summary="Approval history")
def get_logs(proposal_id: int, db: Session = Depends(get_db)):
    get_or_404(db, models.EventProposal, proposal_id)
    return db.scalars(
        select(models.ApprovalLog).where(models.ApprovalLog.event_id == proposal_id).order_by(models.ApprovalLog.id)
    ).all()


@router.post("/{proposal_id}/equipment", response_model=schemas.ProposalDetail, status_code=201, summary="Request equipment")
def add_equipment(proposal_id: int, payload: schemas.EquipmentRequest, db: Session = Depends(get_db)):
    p = get_or_404(db, models.EventProposal, proposal_id)
    _check_equipment(db, payload)
    existing = db.get(models.EventEquipment, (proposal_id, payload.equipment_id))
    if existing:
        existing.quantity_requested = payload.quantity_requested
    else:
        db.add(models.EventEquipment(event_id=proposal_id, **payload.model_dump()))
    commit(db)
    db.refresh(p)
    return _detail(p)


@router.delete("/{proposal_id}/equipment/{equipment_id}", status_code=204, summary="Remove requested equipment")
def remove_equipment(proposal_id: int, equipment_id: int, db: Session = Depends(get_db)):
    link = db.get(models.EventEquipment, (proposal_id, equipment_id))
    if link is None:
        raise HTTPException(404, "Equipment not requested by this proposal")
    db.delete(link)
    commit(db)
    return Response(status_code=204)
