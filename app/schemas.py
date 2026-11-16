"""Pydantic request/response schemas."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

Status = Literal["Draft", "Submitted", "Under_Review", "Approved", "Rejected", "Canceled"]
Role = Literal["Leader", "Admin", "Reviewer"]
Category = Literal["Academic", "Cultural", "Sports", "Technology", "Social"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Organization ----------
class OrganizationIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    category: Category


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    category: Category | None = None


class OrganizationOut(ORM):
    id: int
    name: str
    category: str
    created_at: datetime


# ---------- User ----------
class UserIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    role: Role
    organization_id: int | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=100)
    email: EmailStr | None = None
    role: Role | None = None
    organization_id: int | None = None


class UserOut(ORM):
    id: int
    full_name: str
    email: str
    role: str
    organization_id: int | None


# ---------- Venue ----------
class VenueIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    building: str = Field(min_length=1, max_length=80)
    capacity: int = Field(gt=0)
    built_in_equipment: str | None = None


class VenueUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    building: str | None = Field(default=None, min_length=1, max_length=80)
    capacity: int | None = Field(default=None, gt=0)
    built_in_equipment: str | None = None


class VenueOut(ORM):
    id: int
    name: str
    building: str
    capacity: int
    built_in_equipment: str | None


class Availability(BaseModel):
    venue_id: int
    start_time: datetime
    end_time: datetime
    available: bool
    conflicts: list[int]


# ---------- Equipment ----------
class EquipmentIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    total_quantity: int = Field(ge=0)


class EquipmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    total_quantity: int | None = Field(default=None, ge=0)


class EquipmentOut(ORM):
    id: int
    name: str
    total_quantity: int


class EquipmentRequest(BaseModel):
    equipment_id: int
    quantity_requested: int = Field(default=1, gt=0)


class EquipmentRequestOut(ORM):
    equipment_id: int
    quantity_requested: int


# ---------- Event proposal ----------
class ProposalIn(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    description: str | None = None
    target_audience: str = Field(min_length=2, max_length=80)
    organization_id: int
    submitter_id: int
    status: Literal["Draft", "Submitted"] = "Draft"
    equipment: list[EquipmentRequest] = []


class ProposalUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=150)
    description: str | None = None
    target_audience: str | None = Field(default=None, min_length=2, max_length=80)


class StatusChange(BaseModel):
    status: Status
    reviewer_id: int | None = None
    comments: str | None = None


class ApprovalLogOut(ORM):
    id: int
    event_id: int
    reviewer_id: int
    new_status: str
    action_timestamp: datetime
    comments: str | None


class ProposalOut(ORM):
    id: int
    title: str
    description: str | None
    status: str
    target_audience: str
    organization_id: int
    submitter_id: int
    created_at: datetime


class ProposalDetail(ProposalOut):
    equipment_items: list[EquipmentRequestOut]
    logs: list[ApprovalLogOut]
    reservation_id: int | None = None


# ---------- Reservation ----------
class ReservationIn(BaseModel):
    event_id: int
    venue_id: int
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def _check_order(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class ReservationUpdate(BaseModel):
    venue_id: int | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class ReservationOut(ORM):
    id: int
    event_id: int
    venue_id: int
    start_time: datetime
    end_time: datetime


class AudienceWarning(BaseModel):
    message: str
    other_event_id: int
    other_event_title: str
    target_audience: str
    other_start_time: datetime
    other_end_time: datetime


class ReservationCreated(BaseModel):
    reservation: ReservationOut
    warnings: list[AudienceWarning]
