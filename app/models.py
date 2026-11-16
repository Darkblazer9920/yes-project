"""SQLAlchemy ORM models for the Yachay Events System (YES).

Table and constraint names follow Annex B of the design specification:
pk_<table>, fk_<table>_<ref>, uq_<table>_<col>, ck_<table>_<rule>, idx_<table>_<col(s)>.
"""
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "idx_%(table_name)s_%(column_0_name)s",
}

PROPOSAL_STATUSES = ("Draft", "Submitted", "Under_Review", "Approved", "Rejected", "Canceled")
USER_ROLES = ("Leader", "Admin", "Reviewer")
ORG_CATEGORIES = ("Academic", "Cultural", "Sports", "Technology", "Social")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Organization(Base):
    __tablename__ = "organization"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())

    users: Mapped[list["User"]] = relationship(back_populates="organization", passive_deletes=True)
    proposals: Mapped[list["EventProposal"]] = relationship(back_populates="organization", passive_deletes=True)

    __table_args__ = (CheckConstraint(_in_list("category", ORG_CATEGORIES), name="category_valid"),)


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization.id", ondelete="RESTRICT"), nullable=True
    )

    organization: Mapped[Organization | None] = relationship(back_populates="users")

    __table_args__ = (CheckConstraint(_in_list("role", USER_ROLES), name="role_valid"),)


class Venue(Base):
    __tablename__ = "venue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    building: Mapped[str] = mapped_column(String(80), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    # FR-05: built-in equipment of the room (e.g. "Projector, PA system").
    built_in_equipment: Mapped[str | None] = mapped_column(Text, nullable=True)

    reservations: Mapped[list["Reservation"]] = relationship(back_populates="venue", passive_deletes=True)

    __table_args__ = (CheckConstraint("capacity > 0", name="capacity_positive"),)


class EventProposal(Base):
    __tablename__ = "event_proposal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="Draft", server_default="Draft")
    target_audience: Mapped[str] = mapped_column(String(80), nullable=False)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id", ondelete="RESTRICT"), nullable=False)
    submitter_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())

    organization: Mapped[Organization] = relationship(back_populates="proposals")
    submitter: Mapped[User] = relationship()
    reservation: Mapped["Reservation | None"] = relationship(back_populates="event", uselist=False, passive_deletes=True)
    equipment_items: Mapped[list["EventEquipment"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    logs: Mapped[list["ApprovalLog"]] = relationship(back_populates="event", order_by="ApprovalLog.id", passive_deletes=True)

    __table_args__ = (
        CheckConstraint(_in_list("status", PROPOSAL_STATUSES), name="status_valid"),
        Index("idx_event_proposal_status", "status"),
        Index("idx_event_proposal_target_audience", "target_audience"),
        Index("idx_event_proposal_organization_id", "organization_id"),
    )


class Reservation(Base):
    __tablename__ = "reservation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("event_proposal.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    venue_id: Mapped[int] = mapped_column(ForeignKey("venue.id", ondelete="RESTRICT"), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    event: Mapped[EventProposal] = relationship(back_populates="reservation")
    venue: Mapped[Venue] = relationship(back_populates="reservations")

    __table_args__ = (
        CheckConstraint("end_time > start_time", name="time_order"),
        # NFR-02: venue availability lookups (venue + time range).
        Index("idx_reservation_venue_time", "venue_id", "start_time", "end_time"),
        Index("idx_reservation_time", "start_time", "end_time"),
    )


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (CheckConstraint("total_quantity >= 0", name="quantity_non_negative"),)


class EventEquipment(Base):
    """Associative table for the M:N Event_Proposal - Equipment relationship."""

    __tablename__ = "event_equipment"

    event_id: Mapped[int] = mapped_column(ForeignKey("event_proposal.id", ondelete="CASCADE"), primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id", ondelete="RESTRICT"), primary_key=True)
    quantity_requested: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    event: Mapped[EventProposal] = relationship(back_populates="equipment_items")
    equipment: Mapped[Equipment] = relationship()

    __table_args__ = (CheckConstraint("quantity_requested > 0", name="quantity_positive"),)


class ApprovalLog(Base):
    __tablename__ = "approval_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event_proposal.id", ondelete="RESTRICT"), nullable=False)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    # FR-07: the decision recorded by this log entry.
    new_status: Mapped[str] = mapped_column(String(30), nullable=False)
    action_timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    event: Mapped[EventProposal] = relationship(back_populates="logs")
    reviewer: Mapped[User] = relationship()

    __table_args__ = (
        CheckConstraint(_in_list("new_status", PROPOSAL_STATUSES), name="new_status_valid"),
        Index("idx_approval_log_event_id", "event_id"),
    )
