"""CRUD tests for every API resource."""
import pytest

CATALOG = [
    ("/api/organizations", {"name": "Club de Robótica", "category": "Academic"}, {"category": "Technology"}),
    ("/api/users", {"full_name": "María Pérez", "email": "maria.perez@yachaytech.edu.ec", "role": "Reviewer"},
     {"role": "Admin"}),
    ("/api/venues", {"name": "Library Meeting Room", "building": "Library", "capacity": 20,
                     "built_in_equipment": "TV screen"}, {"capacity": 25}),
    ("/api/equipment", {"name": "Projector", "total_quantity": 4}, {"total_quantity": 6}),
]


@pytest.mark.parametrize("url,payload,update", CATALOG, ids=[c[0].split("/")[-1] for c in CATALOG])
def test_catalog_crud_cycle(client, url, payload, update):
    created = client.post(url, json=payload)
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]
    assert client.get(f"{url}/{item_id}").json()[next(iter(payload))] == payload[next(iter(payload))]
    assert any(i["id"] == item_id for i in client.get(url).json())
    updated = client.put(f"{url}/{item_id}", json=update)
    assert updated.status_code == 200
    key = next(iter(update))
    assert updated.json()[key] == update[key]
    assert client.delete(f"{url}/{item_id}").status_code == 204
    assert client.get(f"{url}/{item_id}").status_code == 404


def test_not_found_returns_404(client):
    for url in ("/api/organizations/999", "/api/users/999", "/api/venues/999",
                "/api/equipment/999", "/api/proposals/999", "/api/reservations/999"):
        assert client.get(url).status_code == 404


def test_unique_organization_name(client):
    payload = {"name": "IEEE CIS", "category": "Technology"}
    assert client.post("/api/organizations", json=payload).status_code == 201
    assert client.post("/api/organizations", json=payload).status_code == 409


def test_invalid_values_rejected(client):
    assert client.post("/api/venues", json={"name": "Bad", "building": "X", "capacity": 0}).status_code == 422
    assert client.post("/api/equipment", json={"name": "Mic", "total_quantity": -1}).status_code == 422
    assert client.post("/api/users", json={"full_name": "X Y", "email": "not-an-email", "role": "Leader"}).status_code == 422
    assert client.post("/api/organizations", json={"name": "Club", "category": "Unknown"}).status_code == 422


def test_user_with_missing_organization_is_rejected(client):
    r = client.post("/api/users", json={"full_name": "Ghost", "email": "ghost@yachaytech.edu.ec",
                                         "role": "Leader", "organization_id": 42})
    assert r.status_code == 409


def test_proposal_crud_and_equipment(client, base):
    proj = client.post("/api/equipment", json={"name": "Projector", "total_quantity": 2}).json()
    mic = client.post("/api/equipment", json={"name": "Microphone", "total_quantity": 5}).json()
    created = client.post("/api/proposals", json={
        "title": "Intro to 5G", "description": "Talk", "target_audience": "Telecommunications",
        "organization_id": base["org"]["id"], "submitter_id": base["leader"]["id"],
        "equipment": [{"equipment_id": proj["id"], "quantity_requested": 1}]})
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert created.json()["equipment_items"] == [{"equipment_id": proj["id"], "quantity_requested": 1}]

    assert client.put(f"/api/proposals/{pid}", json={"title": "Intro to 5G networks"}).json()["title"] == "Intro to 5G networks"
    assert client.post(f"/api/proposals/{pid}/equipment", json={"equipment_id": mic["id"], "quantity_requested": 2}).status_code == 201
    assert len(client.get(f"/api/proposals/{pid}").json()["equipment_items"]) == 2
    assert client.delete(f"/api/proposals/{pid}/equipment/{mic['id']}").status_code == 204
    assert client.get("/api/proposals", params={"status": "Draft"}).json()[0]["id"] == pid
    assert client.delete(f"/api/proposals/{pid}").status_code == 204
    assert client.get(f"/api/proposals/{pid}").status_code == 404


def test_proposal_creation_is_atomic(client, base):
    """NFR-05: asking for more units than exist rolls back the whole proposal."""
    proj = client.post("/api/equipment", json={"name": "Projector", "total_quantity": 1}).json()
    r = client.post("/api/proposals", json={
        "title": "Too many projectors", "target_audience": "Physics",
        "organization_id": base["org"]["id"], "submitter_id": base["leader"]["id"],
        "equipment": [{"equipment_id": proj["id"], "quantity_requested": 3}]})
    assert r.status_code == 409
    assert client.get("/api/proposals").json() == []


def test_reservation_requires_approved_proposal(client, base):
    p = client.post("/api/proposals", json={
        "title": "Not approved", "target_audience": "Physics",
        "organization_id": base["org"]["id"], "submitter_id": base["leader"]["id"]}).json()
    r = client.post("/api/reservations", json={"event_id": p["id"], "venue_id": base["venues"]["Aula 102"]["id"],
        "start_time": "2026-10-15T10:00:00", "end_time": "2026-10-15T12:00:00"})
    assert r.status_code == 409 and "NOT_APPROVED" in r.json()["detail"]


def test_reservation_crud(client, base, approved_event):
    ev = approved_event("Workshop")
    venue = base["venues"]["Aula 102"]["id"]
    r = client.post("/api/reservations", json={"event_id": ev["id"], "venue_id": venue,
        "start_time": "2026-10-15T10:00:00", "end_time": "2026-10-15T12:00:00"})
    rid = r.json()["reservation"]["id"]
    moved = client.put(f"/api/reservations/{rid}", json={"start_time": "2026-10-16T10:00:00", "end_time": "2026-10-16T12:00:00"})
    assert moved.status_code == 200 and moved.json()["reservation"]["start_time"].startswith("2026-10-16")
    avail = client.get(f"/api/venues/{venue}/availability",
                       params={"start_time": "2026-10-16T11:00:00", "end_time": "2026-10-16T13:00:00"}).json()
    assert avail["available"] is False and avail["conflicts"] == [rid]
    assert client.delete(f"/api/reservations/{rid}").status_code == 204
    assert client.get("/api/reservations").json() == []


def test_end_before_start_rejected(client, base, approved_event):
    ev = approved_event("Bad times")
    r = client.post("/api/reservations", json={"event_id": ev["id"], "venue_id": base["venues"]["Aula 102"]["id"],
        "start_time": "2026-10-15T12:00:00", "end_time": "2026-10-15T10:00:00"})
    assert r.status_code == 422


def test_cancel_frees_the_venue(client, base, approved_event):
    a, b = approved_event("Event A"), approved_event("Event B", audience="Biology")
    venue = base["venues"]["Aula 102"]["id"]
    slot = {"venue_id": venue, "start_time": "2026-10-15T10:00:00", "end_time": "2026-10-15T12:00:00"}
    assert client.post("/api/reservations", json={"event_id": a["id"], **slot}).status_code == 201
    assert client.post(f"/api/proposals/{a['id']}/status", json={"status": "Canceled"}).json()["reservation_id"] is None
    assert client.post("/api/reservations", json={"event_id": b["id"], **slot}).status_code == 201


def test_club_activity_report(client, base, approved_event):
    approved_event("Talk")
    report = client.get("/api/reports/club-activity", params={"semester": "2026-2"}).json()
    row = next(o for o in report["organizations"] if o["organization_id"] == base["org"]["id"])
    assert row["proposals"] == 1 and row["approved"] == 1
    assert client.get("/api/reports/club-activity", params={"semester": "2026-3"}).status_code == 422
