"""Shared fixtures: every test gets a fresh SQLite database file with all triggers installed."""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/yes_pytest_default.db")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import get_db, init_db, make_engine
from app.main import app


@pytest.fixture()
def engine(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def client(engine):
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def base(client):
    """Minimal catalog: one club, a leader, an admin and three venues."""
    org = client.post("/api/organizations", json={"name": "IEEE ComSoc", "category": "Technology"}).json()
    leader = client.post("/api/users", json={
        "full_name": "Ana Leader", "email": "ana.leader@yachaytech.edu.ec",
        "role": "Leader", "organization_id": org["id"]}).json()
    admin = client.post("/api/users", json={
        "full_name": "Luis Admin", "email": "luis.admin@yachaytech.edu.ec", "role": "Admin"}).json()
    venues = {
        name: client.post("/api/venues", json={"name": name, "building": b, "capacity": cap}).json()
        for name, b, cap in [("Auditorio Módulo 1", "Módulo 1", 250),
                             ("Aula 102", "Módulo 2", 40), ("Aula 104", "Módulo 2", 40)]
    }
    return {"org": org, "leader": leader, "admin": admin, "venues": venues}


@pytest.fixture()
def approved_event(client, base):
    """Factory: creates a proposal and walks it to Approved with a reviewer log."""
    def _make(title="Event", audience="Computer Engineering"):
        p = client.post("/api/proposals", json={
            "title": title, "target_audience": audience, "organization_id": base["org"]["id"],
            "submitter_id": base["leader"]["id"], "status": "Submitted"}).json()
        admin = base["admin"]["id"]
        for status in ("Under_Review", "Approved"):
            r = client.post(f"/api/proposals/{p['id']}/status",
                            json={"status": status, "reviewer_id": admin, "comments": f"{status} by test"})
            assert r.status_code == 200, r.text
        return p
    return _make
