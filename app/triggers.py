"""SQLite triggers that enforce business rules inside the database itself.

They guarantee the rules even if data is written without the API.
"""

# Allowed status transitions (FR-03). Anything else is rejected.
ALLOWED_TRANSITIONS = {
    "Draft": ("Submitted", "Canceled"),
    "Submitted": ("Under_Review", "Draft", "Canceled"),
    "Under_Review": ("Approved", "Rejected", "Canceled"),
    "Approved": ("Canceled",),
    "Rejected": ("Draft",),
    "Canceled": (),
}


def _transition_condition() -> str:
    parts = []
    for old, news in ALLOWED_TRANSITIONS.items():
        if news:
            quoted = ", ".join(f"'{n}'" for n in news)
            parts.append(f"(OLD.status = '{old}' AND NEW.status IN ({quoted}))")
    return " OR ".join(parts)


TRIGGERS = [
    # FR-02 / TC-01: block double booking of the same venue (insert).
    """
    CREATE TRIGGER IF NOT EXISTS trg_reservation_no_overlap_insert
    BEFORE INSERT ON reservation
    BEGIN
        SELECT RAISE(ABORT, 'VENUE_CONFLICT: venue already booked for that time range')
        WHERE EXISTS (
            SELECT 1 FROM reservation r
            WHERE r.venue_id = NEW.venue_id
              AND NEW.start_time < r.end_time
              AND NEW.end_time > r.start_time
        );
    END;
    """,
    # FR-02: same rule when a reservation is moved (update).
    """
    CREATE TRIGGER IF NOT EXISTS trg_reservation_no_overlap_update
    BEFORE UPDATE OF venue_id, start_time, end_time ON reservation
    BEGIN
        SELECT RAISE(ABORT, 'VENUE_CONFLICT: venue already booked for that time range')
        WHERE EXISTS (
            SELECT 1 FROM reservation r
            WHERE r.venue_id = NEW.venue_id
              AND r.id <> NEW.id
              AND NEW.start_time < r.end_time
              AND NEW.end_time > r.start_time
        );
    END;
    """,
    # Reservations can only be created for approved proposals.
    """
    CREATE TRIGGER IF NOT EXISTS trg_reservation_requires_approved
    BEFORE INSERT ON reservation
    BEGIN
        SELECT RAISE(ABORT, 'NOT_APPROVED: only approved proposals can reserve a venue')
        WHERE (SELECT status FROM event_proposal WHERE id = NEW.event_id) <> 'Approved';
    END;
    """,
    # FR-03: new proposals start as Draft or Submitted.
    """
    CREATE TRIGGER IF NOT EXISTS trg_event_proposal_initial_status
    BEFORE INSERT ON event_proposal
    BEGIN
        SELECT RAISE(ABORT, 'INVALID_STATUS: a new proposal must start as Draft or Submitted')
        WHERE NEW.status NOT IN ('Draft', 'Submitted');
    END;
    """,
    # FR-03 / TC-02: only the allowed lifecycle transitions.
    f"""
    CREATE TRIGGER IF NOT EXISTS trg_event_proposal_status_flow
    BEFORE UPDATE OF status ON event_proposal
    WHEN NEW.status <> OLD.status AND NOT ({_transition_condition()})
    BEGIN
        SELECT RAISE(ABORT, 'INVALID_TRANSITION: status change not allowed');
    END;
    """,
    # FR-07 / TC-02: Approved or Rejected requires an administrative log entry.
    """
    CREATE TRIGGER IF NOT EXISTS trg_event_proposal_decision_logged
    BEFORE UPDATE OF status ON event_proposal
    WHEN NEW.status IN ('Approved', 'Rejected') AND NEW.status <> OLD.status
    BEGIN
        SELECT RAISE(ABORT, 'LOG_REQUIRED: approval or rejection needs an approval_log entry')
        WHERE NOT EXISTS (
            SELECT 1 FROM approval_log
            WHERE event_id = NEW.id AND new_status = NEW.status
        );
    END;
    """,
    # Approval logs can only be written by Admin or Reviewer users.
    """
    CREATE TRIGGER IF NOT EXISTS trg_approval_log_reviewer_role
    BEFORE INSERT ON approval_log
    BEGIN
        SELECT RAISE(ABORT, 'FORBIDDEN_REVIEWER: reviewer must have role Admin or Reviewer')
        WHERE (SELECT role FROM "user" WHERE id = NEW.reviewer_id) NOT IN ('Admin', 'Reviewer');
    END;
    """,
]
