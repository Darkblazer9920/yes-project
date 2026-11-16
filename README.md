# Yachay Events System (YES)

Relational database, REST API and web GUI to manage event proposals, venue reservations and
activity tracking for student clubs at Yachay Tech University.

**Stack:** SQLite · SQLAlchemy 2.0 · FastAPI · vanilla HTML/JS · pytest · Docker

## Run with Docker

```bash
docker compose up --build
```

Then open:

- GUI: http://localhost:8000
- Interactive API docs (Swagger): http://localhost:8000/docs

The database lives in the `yes-data` volume. Demo data is loaded on the first start.

## Run locally (without Docker)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
python -m app.seed               # creates data/yes.db with demo data
uvicorn app.main:app --reload
```

## Run the tests

```bash
pytest -v
```

Each test runs on a fresh SQLite file. `tests/test_spec_cases.py` implements TC-01 to TC-05 of the
design specification; `tests/test_crud.py` covers CRUD for every resource.

## Project structure

```
app/
  models.py        ORM models (8 tables, Annex B naming conventions)
  triggers.py      SQLite triggers: double booking, status flow, approval log, reviewer role
  database.py      engine, PRAGMA foreign_keys=ON, init_db()
  schemas.py       Pydantic request/response models
  errors.py        database error -> HTTP status mapping, atomic commit
  routers/         basic.py (catalog CRUD), proposals.py, reservations.py, reports.py
  seed.py          demo data
  main.py          FastAPI app, serves the GUI from /static
static/            web GUI (index.html, app.js, style.css)
sql/schema.sql     generated DDL (tables, constraints, indexes, triggers)
tests/             pytest suite
```

## Main endpoints

| Resource | Endpoints |
| --- | --- |
| Organizations, users, venues, equipment | `GET/POST /api/<resource>`, `GET/PUT/DELETE /api/<resource>/{id}` |
| Venue availability | `GET /api/venues/{id}/availability?start_time=&end_time=` |
| Event proposals | `GET/POST /api/proposals`, `GET/PUT/DELETE /api/proposals/{id}` |
| Proposal lifecycle | `POST /api/proposals/{id}/status`, `GET /api/proposals/{id}/logs` |
| Proposal equipment | `POST /api/proposals/{id}/equipment`, `DELETE /api/proposals/{id}/equipment/{equipment_id}` |
| Reservations | `GET/POST /api/reservations`, `GET/PUT/DELETE /api/reservations/{id}` |
| Reports | `GET /api/reports/occupancy`, `/api/reports/club-activity?semester=2026-2`, `/api/reports/audience-overlaps` |
