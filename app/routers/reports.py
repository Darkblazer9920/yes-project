"""Reporting endpoints: occupancy (FR-06), club activity per semester (FR-06), audience overlaps (FR-04)."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(prefix="/reports", tags=["Reports"])

OCCUPANCY_SQL = text("""
SELECT v.id AS venue_id,
       v.name AS venue_name,
       v.building AS building,
       COUNT(r.id) AS reservations,
       COALESCE(SUM(
           (julianday(MIN(r.end_time, :end)) - julianday(MAX(r.start_time, :start))) * 24
       ), 0) AS booked_hours
FROM venue v
LEFT JOIN reservation r
       ON r.venue_id = v.id AND r.start_time < :end AND r.end_time > :start
GROUP BY v.id, v.name, v.building
ORDER BY booked_hours DESC, v.name
""")

CLUB_ACTIVITY_SQL = text("""
SELECT o.id AS organization_id,
       o.name AS organization_name,
       COUNT(p.id) AS proposals,
       SUM(CASE WHEN p.status = 'Approved' THEN 1 ELSE 0 END) AS approved,
       SUM(CASE WHEN p.status = 'Rejected' THEN 1 ELSE 0 END) AS rejected,
       SUM(CASE WHEN p.status = 'Canceled' THEN 1 ELSE 0 END) AS canceled,
       SUM(CASE WHEN p.status IN ('Draft', 'Submitted', 'Under_Review') THEN 1 ELSE 0 END) AS in_progress,
       COUNT(r.id) AS events_scheduled,
       COALESCE(SUM((julianday(r.end_time) - julianday(r.start_time)) * 24), 0) AS reserved_hours
FROM organization o
LEFT JOIN event_proposal p
       ON p.organization_id = o.id AND p.created_at >= :start AND p.created_at < :end
LEFT JOIN reservation r ON r.event_id = p.id
GROUP BY o.id, o.name
ORDER BY proposals DESC, o.name
""")

OVERLAP_SQL = text("""
SELECT a.id AS event_a_id, a.title AS event_a_title, va.name AS venue_a,
       ra.start_time AS event_a_start, ra.end_time AS event_a_end,
       b.id AS event_b_id, b.title AS event_b_title, vb.name AS venue_b,
       rb.start_time AS event_b_start, rb.end_time AS event_b_end,
       a.target_audience AS target_audience
FROM event_proposal a
JOIN reservation ra ON ra.event_id = a.id
JOIN venue va ON va.id = ra.venue_id
JOIN event_proposal b ON lower(b.target_audience) = lower(a.target_audience) AND b.id > a.id
JOIN reservation rb ON rb.event_id = b.id
JOIN venue vb ON vb.id = rb.venue_id
WHERE a.status = 'Approved' AND b.status = 'Approved'
  AND ra.start_time < rb.end_time AND ra.end_time > rb.start_time
ORDER BY ra.start_time
""")


def _fmt(dt: datetime) -> str:
    # Same text format SQLAlchemy uses to store DATETIME values in SQLite.
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")


@router.get("/occupancy", summary="Room occupancy rate in a time window")
def occupancy(start: datetime = Query(...), end: datetime = Query(...), db: Session = Depends(get_db)):
    if end <= start:
        raise HTTPException(422, "end must be after start")
    window_hours = (end - start).total_seconds() / 3600
    rows = db.execute(OCCUPANCY_SQL, {"start": _fmt(start), "end": _fmt(end)}).mappings().all()
    return {
        "start": start, "end": end, "window_hours": round(window_hours, 2),
        "venues": [
            {**row, "booked_hours": round(row["booked_hours"], 2),
             "occupancy_rate": round(100 * row["booked_hours"] / window_hours, 2)}
            for row in rows
        ],
    }


def _semester_bounds(semester: str) -> tuple[datetime, datetime]:
    """'2026-1' = Jan 1 to Jul 1, '2026-2' = Jul 1 to Jan 1 of the next year."""
    try:
        year_s, term_s = semester.split("-")
        year, term = int(year_s), int(term_s)
        if term not in (1, 2):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(422, "semester must look like 2026-1 or 2026-2") from exc
    if term == 1:
        return datetime(year, 1, 1), datetime(year, 7, 1)
    return datetime(year, 7, 1), datetime(year + 1, 1, 1)


@router.get("/club-activity", summary="Club activity summary per semester")
def club_activity(semester: str = Query(..., examples=["2026-2"]), db: Session = Depends(get_db)):
    start, end = _semester_bounds(semester)
    rows = db.execute(CLUB_ACTIVITY_SQL, {"start": _fmt(start), "end": _fmt(end)}).mappings().all()
    return {
        "semester": semester, "start": start, "end": end,
        "organizations": [{**row, "reserved_hours": round(row["reserved_hours"], 2)} for row in rows],
    }


@router.get("/audience-overlaps", summary="Approved events sharing a target audience at the same time")
def audience_overlaps(db: Session = Depends(get_db)):
    return [dict(row) for row in db.execute(OVERLAP_SQL).mappings().all()]
