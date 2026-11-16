"""Load demo data (python -m app.seed). Runs through the same rules as the API."""
from datetime import datetime

from sqlalchemy import select

from app.database import SessionLocal, engine, init_db
from app.models import (ApprovalLog, Equipment, EventEquipment, EventProposal, Organization, Reservation, User, Venue)


def _approve(db, proposal, reviewer, comment):
    proposal.status = "Under_Review"
    db.add(ApprovalLog(event_id=proposal.id, reviewer_id=reviewer.id, new_status="Under_Review"))
    db.flush()
    db.add(ApprovalLog(event_id=proposal.id, reviewer_id=reviewer.id, new_status="Approved", comments=comment))
    db.flush()
    proposal.status = "Approved"
    db.flush()


def seed() -> None:
    init_db(engine)
    with SessionLocal() as db:
        if db.scalar(select(Organization.id).limit(1)):
            print("Database already has data; seed skipped.")
            return

        orgs = {name: Organization(name=name, category=cat) for name, cat in [
            ("IEEE ComSoc", "Technology"), ("IEEE Computer Society", "Technology"),
            ("Club de Ciencias Computacionales", "Academic"), ("Club de Teatro", "Cultural"),
            ("Club de Fútbol", "Sports")]}
        db.add_all(orgs.values())
        db.flush()

        admin = User(full_name="Patricia Andrade", email="pandrade@yachaytech.edu.ec", role="Admin")
        reviewer = User(full_name="Carlos Vega", email="cvega@yachaytech.edu.ec", role="Reviewer")
        leaders = [
            User(full_name="Marlon Almeida", email="marlon.almeida@yachaytech.edu.ec", role="Leader",
                 organization_id=orgs["IEEE ComSoc"].id),
            User(full_name="Daniela Ruiz", email="daniela.ruiz@yachaytech.edu.ec", role="Leader",
                 organization_id=orgs["Club de Ciencias Computacionales"].id),
            User(full_name="Sofía Torres", email="sofia.torres@yachaytech.edu.ec", role="Leader",
                 organization_id=orgs["Club de Teatro"].id),
        ]
        db.add_all([admin, reviewer, *leaders])

        venues = {v.name: v for v in [
            Venue(name="Auditorio Módulo 1", building="Módulo 1", capacity=250, built_in_equipment="Projector, PA system"),
            Venue(name="Aula 102", building="Módulo 2", capacity=40, built_in_equipment="Projector"),
            Venue(name="Aula 104", building="Módulo 2", capacity=40, built_in_equipment="Projector"),
            Venue(name="Library Meeting Room", building="Library", capacity=20, built_in_equipment="TV screen"),
            Venue(name="Laboratorio de Redes", building="Módulo 3", capacity=30, built_in_equipment="30 PCs"),
        ]}
        db.add_all(venues.values())
        equipment = [Equipment(name="Projector", total_quantity=6), Equipment(name="Portable Speaker", total_quantity=3),
                     Equipment(name="Wireless Microphone", total_quantity=8)]
        db.add_all(equipment)
        db.flush()

        plan = [
            ("Intro to 5G Networks", "Computer Engineering", "IEEE ComSoc", leaders[0], "Auditorio Módulo 1",
             datetime(2026, 12, 2, 10), datetime(2026, 12, 2, 12), True),
            ("Python Workshop", "Computer Engineering", "Club de Ciencias Computacionales", leaders[1], "Aula 102",
             datetime(2026, 12, 3, 14), datetime(2026, 12, 3, 16), True),
            ("Git & GitHub Bootcamp", "Computer Engineering", "IEEE ComSoc", leaders[0], "Aula 104",
             datetime(2026, 12, 3, 14, 30), datetime(2026, 12, 3, 16, 30), True),
            ("Improv Night", "All majors", "Club de Teatro", leaders[2], "Auditorio Módulo 1",
             datetime(2026, 12, 4, 18), datetime(2026, 12, 4, 20), True),
            ("Networking Lab Day", "Telecommunications", "IEEE ComSoc", leaders[0], None, None, None, False),
        ]
        for title, audience, org, leader, venue, start, end, approve in plan:
            p = EventProposal(title=title, target_audience=audience, organization_id=orgs[org].id,
                              submitter_id=leader.id, status="Submitted",
                              description=f"{title} organized by {org}.")
            db.add(p)
            db.flush()
            if approve:
                _approve(db, p, reviewer, "Meets venue and safety requirements.")
                db.add(Reservation(event_id=p.id, venue_id=venues[venue].id, start_time=start, end_time=end))
                db.add(EventEquipment(event_id=p.id, equipment_id=equipment[0].id, quantity_requested=1))
                db.flush()
        db.add(EventProposal(title="Robotics Exhibition", target_audience="Mechatronics", status="Draft",
                             organization_id=orgs["IEEE Computer Society"].id, submitter_id=leaders[0].id))
        db.commit()
        print("Demo data loaded.")


if __name__ == "__main__":
    seed()
