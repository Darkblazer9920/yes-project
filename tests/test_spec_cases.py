"""Test cases TC-01 to TC-05 from Section 4 of the Database Design Specification."""
import time
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.routers.reports import OCCUPANCY_SQL, _fmt


def test_tc01_prevent_double_booking_same_venue(client, base, approved_event):
    """TC-01 (FR-02): Auditorio Módulo 1 booked 10:00-12:00; 11:00-13:00 must fail."""
    venue = base["venues"]["Auditorio Módulo 1"]["id"]
    a, b = approved_event("Event A"), approved_event("Event B", audience="Biology")
    ok = client.post("/api/reservations", json={
        "event_id": a["id"], "venue_id": venue,
        "start_time": "2026-10-15T10:00:00", "end_time": "2026-10-15T12:00:00"})
    assert ok.status_code == 201
    clash = client.post("/api/reservations", json={
        "event_id": b["id"], "venue_id": venue,
        "start_time": "2026-10-15T11:00:00", "end_time": "2026-10-15T13:00:00"})
    assert clash.status_code == 409
    assert "VENUE_CONFLICT" in clash.json()["detail"]
    assert len(client.get("/api/reservations").json()) == 1


def test_tc01_trigger_blocks_direct_sql_insert(engine, client, base, approved_event):
    """TC-01 at database level: the trigger rejects the overlap even without the API."""
    venue = base["venues"]["Auditorio Módulo 1"]["id"]
    a, b = approved_event("Event A"), approved_event("Event B", audience="Biology")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO reservation(event_id, venue_id, start_time, end_time) "
                          "VALUES (:e, :v, '2026-10-15 10:00:00.000000', '2026-10-15 12:00:00.000000')"),
                     {"e": a["id"], "v": venue})
    with pytest.raises(IntegrityError, match="VENUE_CONFLICT"):
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO reservation(event_id, venue_id, start_time, end_time) "
                              "VALUES (:e, :v, '2026-10-15 11:00:00.000000', '2026-10-15 13:00:00.000000')"),
                         {"e": b["id"], "v": venue})


def test_tc01_back_to_back_bookings_are_allowed(client, base, approved_event):
    """A booking that starts exactly when the previous one ends is not a conflict."""
    venue = base["venues"]["Aula 102"]["id"]
    a, b = approved_event("Morning"), approved_event("Noon", audience="Biology")
    assert client.post("/api/reservations", json={"event_id": a["id"], "venue_id": venue,
        "start_time": "2026-10-15T10:00:00", "end_time": "2026-10-15T12:00:00"}).status_code == 201
    assert client.post("/api/reservations", json={"event_id": b["id"], "venue_id": venue,
        "start_time": "2026-10-15T12:00:00", "end_time": "2026-10-15T13:00:00"}).status_code == 201


def test_tc02_draft_cannot_jump_to_approved(client, base):
    """TC-02 (FR-03): a Draft proposal cannot be approved directly."""
    p = client.post("/api/proposals", json={
        "title": "EP-01", "target_audience": "Computer Engineering",
        "organization_id": base["org"]["id"], "submitter_id": base["leader"]["id"]}).json()
    assert p["status"] == "Draft"
    r = client.post(f"/api/proposals/{p['id']}/status",
                    json={"status": "Approved", "reviewer_id": base["admin"]["id"]})
    assert r.status_code == 409
    assert "INVALID_TRANSITION" in r.json()["detail"]
    detail = client.get(f"/api/proposals/{p['id']}").json()
    assert detail["status"] == "Draft"
    assert detail["logs"] == []  # the log insert was rolled back with the failed update (NFR-05)


def test_tc02_approval_without_log_is_blocked_in_database(engine, client, base):
    """TC-02: even through raw SQL, Approved requires an approval_log entry (FR-07)."""
    p = client.post("/api/proposals", json={
        "title": "EP-02", "target_audience": "Physics", "status": "Submitted",
        "organization_id": base["org"]["id"], "submitter_id": base["leader"]["id"]}).json()
    with engine.begin() as conn:
        conn.execute(text("UPDATE event_proposal SET status='Under_Review' WHERE id=:id"), {"id": p["id"]})
    with pytest.raises(IntegrityError, match="LOG_REQUIRED"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE event_proposal SET status='Approved' WHERE id=:id"), {"id": p["id"]})


def test_tc02_full_lifecycle_records_logs(client, base):
    p = client.post("/api/proposals", json={
        "title": "Hackathon", "target_audience": "All majors",
        "organization_id": base["org"]["id"], "submitter_id": base["leader"]["id"]}).json()
    admin = base["admin"]["id"]
    assert client.post(f"/api/proposals/{p['id']}/status", json={"status": "Submitted"}).status_code == 200
    assert client.post(f"/api/proposals/{p['id']}/status",
                       json={"status": "Under_Review", "reviewer_id": admin}).status_code == 200
    r = client.post(f"/api/proposals/{p['id']}/status",
                    json={"status": "Approved", "reviewer_id": admin, "comments": "Looks good"})
    assert r.status_code == 200 and r.json()["status"] == "Approved"
    logs = client.get(f"/api/proposals/{p['id']}/logs").json()
    assert [log["new_status"] for log in logs] == ["Under_Review", "Approved"]
    assert logs[-1]["comments"] == "Looks good"


def test_tc02_leader_cannot_approve(client, base):
    """Only Admin or Reviewer users may write approval logs."""
    p = client.post("/api/proposals", json={
        "title": "Self approval", "target_audience": "Physics", "status": "Submitted",
        "organization_id": base["org"]["id"], "submitter_id": base["leader"]["id"]}).json()
    r = client.post(f"/api/proposals/{p['id']}/status",
                    json={"status": "Under_Review", "reviewer_id": base["leader"]["id"]})
    assert r.status_code == 403


def test_tc03_audience_overlap_warning(client, base, approved_event):
    """TC-03 (FR-04): two Computer Engineering events at 14:00 and 14:30 trigger a warning."""
    a = approved_event("Event A", audience="Computer Engineering")
    b = approved_event("Event B", audience="Computer Engineering")
    first = client.post("/api/reservations", json={
        "event_id": a["id"], "venue_id": base["venues"]["Aula 102"]["id"],
        "start_time": "2026-10-20T14:00:00", "end_time": "2026-10-20T16:00:00"})
    assert first.status_code == 201 and first.json()["warnings"] == []
    second = client.post("/api/reservations", json={
        "event_id": b["id"], "venue_id": base["venues"]["Aula 104"]["id"],
        "start_time": "2026-10-20T14:30:00", "end_time": "2026-10-20T16:30:00"})
    assert second.status_code == 201
    warnings = second.json()["warnings"]
    assert len(warnings) == 1 and warnings[0]["other_event_id"] == a["id"]
    report = client.get("/api/reports/audience-overlaps").json()
    assert len(report) == 1 and report[0]["target_audience"] == "Computer Engineering"


def test_tc03_no_warning_for_different_audience(client, base, approved_event):
    a = approved_event("Event A", audience="Computer Engineering")
    b = approved_event("Event B", audience="Biology")
    client.post("/api/reservations", json={"event_id": a["id"], "venue_id": base["venues"]["Aula 102"]["id"],
        "start_time": "2026-10-20T14:00:00", "end_time": "2026-10-20T16:00:00"})
    r = client.post("/api/reservations", json={"event_id": b["id"], "venue_id": base["venues"]["Aula 104"]["id"],
        "start_time": "2026-10-20T14:30:00", "end_time": "2026-10-20T16:30:00"})
    assert r.json()["warnings"] == []


def test_tc04_delete_organization_with_proposals_is_blocked(client, base):
    """TC-04 (NFR-04): deleting a club with active proposals is blocked by the foreign key."""
    client.post("/api/proposals", json={
        "title": "Active proposal", "target_audience": "Physics",
        "organization_id": base["org"]["id"], "submitter_id": base["leader"]["id"]})
    r = client.delete(f"/api/organizations/{base['org']['id']}")
    assert r.status_code == 409
    assert "foreign key" in r.json()["detail"].lower()
    assert client.get(f"/api/organizations/{base['org']['id']}").status_code == 200


def test_tc04_foreign_keys_enabled_at_sql_level(engine, client, base):
    client.post("/api/proposals", json={
        "title": "Active proposal", "target_audience": "Physics",
        "organization_id": base["org"]["id"], "submitter_id": base["leader"]["id"]})
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM organization WHERE id = :id"), {"id": base["org"]["id"]})


def _bulk_reservations(engine, org_id, leader_id, admin_id, venue_ids, n=500):
    """Insert n approved events with non-overlapping reservations (respects every trigger)."""
    start = datetime(2026, 9, 1, 7, 0)
    with engine.begin() as conn:
        for i in range(n):
            pid = conn.execute(text(
                "INSERT INTO event_proposal(title, target_audience, status, organization_id, submitter_id) "
                "VALUES (:t, :a, 'Submitted', :o, :s) RETURNING id"),
                {"t": f"Bulk event {i}", "a": f"Major {i % 7}", "o": org_id, "s": leader_id}).scalar()
            conn.execute(text("UPDATE event_proposal SET status='Under_Review' WHERE id=:id"), {"id": pid})
            conn.execute(text("INSERT INTO approval_log(event_id, reviewer_id, new_status) VALUES (:e, :r, 'Approved')"),
                         {"e": pid, "r": admin_id})
            conn.execute(text("UPDATE event_proposal SET status='Approved' WHERE id=:id"), {"id": pid})
            venue = venue_ids[i % len(venue_ids)]
            slot = start + timedelta(hours=2 * (i // len(venue_ids)))
            conn.execute(text("INSERT INTO reservation(event_id, venue_id, start_time, end_time) VALUES (:e, :v, :s, :f)"),
                         {"e": pid, "v": venue, "s": _fmt(slot), "f": _fmt(slot + timedelta(hours=2))})


def test_tc05_occupancy_query_performance(engine, client, base):
    """TC-05 (FR-06, NFR-02): occupancy over 500 reservations returns in < 50 ms."""
    venue_ids = [v["id"] for v in base["venues"].values()]
    _bulk_reservations(engine, base["org"]["id"], base["leader"]["id"], base["admin"]["id"], venue_ids)
    window = {"start": _fmt(datetime(2026, 9, 1)), "end": _fmt(datetime(2026, 12, 1))}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM reservation")).scalar() == 500
        conn.execute(OCCUPANCY_SQL, window).all()  # warm-up
        timings = []
        for _ in range(5):
            t0 = time.perf_counter()
            rows = conn.execute(OCCUPANCY_SQL, window).all()
            timings.append((time.perf_counter() - t0) * 1000)
    best = min(timings)
    print(f"\nTC-05 occupancy SQL over 500 reservations: best {best:.2f} ms, worst {max(timings):.2f} ms")
    assert len(rows) == 3
    assert best < 50

    r = client.get("/api/reports/occupancy", params={"start": "2026-09-01T00:00:00", "end": "2026-12-01T00:00:00"})
    assert r.status_code == 200
    total_hours = sum(v["booked_hours"] for v in r.json()["venues"])
    assert round(total_hours) == 1000  # 500 reservations x 2 h


def test_tc05_reservation_lookup_uses_index(engine, client, base):
    """NFR-02: the availability lookup is served by idx_reservation_venue_time."""
    with engine.connect() as conn:
        plan = conn.execute(text(
            "EXPLAIN QUERY PLAN SELECT id FROM reservation WHERE venue_id = 1 "
            "AND start_time < '2026-10-15 12:00:00' AND end_time > '2026-10-15 10:00:00'")).all()
    assert any("idx_reservation_venue_time" in str(row) for row in plan)
