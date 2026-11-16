-- Yachay Events System (YES) - SQLite schema generated from app/models.py and app/triggers.py
PRAGMA foreign_keys = ON;

CREATE TABLE equipment (
	id INTEGER NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	total_quantity INTEGER NOT NULL, 
	CONSTRAINT pk_equipment PRIMARY KEY (id), 
	CONSTRAINT ck_equipment_quantity_non_negative CHECK (total_quantity >= 0), 
	CONSTRAINT uq_equipment_name UNIQUE (name)
);


CREATE TABLE organization (
	id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	category VARCHAR(50) NOT NULL, 
	created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	CONSTRAINT pk_organization PRIMARY KEY (id), 
	CONSTRAINT ck_organization_category_valid CHECK (category IN ('Academic', 'Cultural', 'Sports', 'Technology', 'Social')), 
	CONSTRAINT uq_organization_name UNIQUE (name)
);


CREATE TABLE venue (
	id INTEGER NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	building VARCHAR(80) NOT NULL, 
	capacity INTEGER NOT NULL, 
	built_in_equipment TEXT, 
	CONSTRAINT pk_venue PRIMARY KEY (id), 
	CONSTRAINT ck_venue_capacity_positive CHECK (capacity > 0), 
	CONSTRAINT uq_venue_name UNIQUE (name)
);


CREATE TABLE user (
	id INTEGER NOT NULL, 
	full_name VARCHAR(100) NOT NULL, 
	email VARCHAR(100) NOT NULL, 
	role VARCHAR(30) NOT NULL, 
	organization_id INTEGER, 
	CONSTRAINT pk_user PRIMARY KEY (id), 
	CONSTRAINT ck_user_role_valid CHECK (role IN ('Leader', 'Admin', 'Reviewer')), 
	CONSTRAINT uq_user_email UNIQUE (email), 
	CONSTRAINT fk_user_organization FOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE RESTRICT
);


CREATE TABLE event_proposal (
	id INTEGER NOT NULL, 
	title VARCHAR(150) NOT NULL, 
	description TEXT, 
	status VARCHAR(30) DEFAULT 'Draft' NOT NULL, 
	target_audience VARCHAR(80) NOT NULL, 
	organization_id INTEGER NOT NULL, 
	submitter_id INTEGER NOT NULL, 
	created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	CONSTRAINT pk_event_proposal PRIMARY KEY (id), 
	CONSTRAINT ck_event_proposal_status_valid CHECK (status IN ('Draft', 'Submitted', 'Under_Review', 'Approved', 'Rejected', 'Canceled')), 
	CONSTRAINT fk_event_proposal_organization FOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_event_proposal_user FOREIGN KEY(submitter_id) REFERENCES user (id) ON DELETE RESTRICT
);

CREATE INDEX idx_event_proposal_organization_id ON event_proposal (organization_id);
CREATE INDEX idx_event_proposal_status ON event_proposal (status);
CREATE INDEX idx_event_proposal_target_audience ON event_proposal (target_audience);

CREATE TABLE approval_log (
	id INTEGER NOT NULL, 
	event_id INTEGER NOT NULL, 
	reviewer_id INTEGER NOT NULL, 
	new_status VARCHAR(30) NOT NULL, 
	action_timestamp DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	comments TEXT, 
	CONSTRAINT pk_approval_log PRIMARY KEY (id), 
	CONSTRAINT ck_approval_log_new_status_valid CHECK (new_status IN ('Draft', 'Submitted', 'Under_Review', 'Approved', 'Rejected', 'Canceled')), 
	CONSTRAINT fk_approval_log_event_proposal FOREIGN KEY(event_id) REFERENCES event_proposal (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_approval_log_user FOREIGN KEY(reviewer_id) REFERENCES user (id) ON DELETE RESTRICT
);

CREATE INDEX idx_approval_log_event_id ON approval_log (event_id);

CREATE TABLE event_equipment (
	event_id INTEGER NOT NULL, 
	equipment_id INTEGER NOT NULL, 
	quantity_requested INTEGER NOT NULL, 
	CONSTRAINT pk_event_equipment PRIMARY KEY (event_id, equipment_id), 
	CONSTRAINT ck_event_equipment_quantity_positive CHECK (quantity_requested > 0), 
	CONSTRAINT fk_event_equipment_event_proposal FOREIGN KEY(event_id) REFERENCES event_proposal (id) ON DELETE CASCADE, 
	CONSTRAINT fk_event_equipment_equipment FOREIGN KEY(equipment_id) REFERENCES equipment (id) ON DELETE RESTRICT
);


CREATE TABLE reservation (
	id INTEGER NOT NULL, 
	event_id INTEGER NOT NULL, 
	venue_id INTEGER NOT NULL, 
	start_time DATETIME NOT NULL, 
	end_time DATETIME NOT NULL, 
	CONSTRAINT pk_reservation PRIMARY KEY (id), 
	CONSTRAINT ck_reservation_time_order CHECK (end_time > start_time), 
	CONSTRAINT uq_reservation_event_id UNIQUE (event_id), 
	CONSTRAINT fk_reservation_event_proposal FOREIGN KEY(event_id) REFERENCES event_proposal (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_reservation_venue FOREIGN KEY(venue_id) REFERENCES venue (id) ON DELETE RESTRICT
);

CREATE INDEX idx_reservation_time ON reservation (start_time, end_time);
CREATE INDEX idx_reservation_venue_time ON reservation (venue_id, start_time, end_time);

-- Business-rule triggers
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

CREATE TRIGGER IF NOT EXISTS trg_reservation_requires_approved
BEFORE INSERT ON reservation
BEGIN
    SELECT RAISE(ABORT, 'NOT_APPROVED: only approved proposals can reserve a venue')
    WHERE (SELECT status FROM event_proposal WHERE id = NEW.event_id) <> 'Approved';
END;

CREATE TRIGGER IF NOT EXISTS trg_event_proposal_initial_status
BEFORE INSERT ON event_proposal
BEGIN
    SELECT RAISE(ABORT, 'INVALID_STATUS: a new proposal must start as Draft or Submitted')
    WHERE NEW.status NOT IN ('Draft', 'Submitted');
END;

CREATE TRIGGER IF NOT EXISTS trg_event_proposal_status_flow
BEFORE UPDATE OF status ON event_proposal
WHEN NEW.status <> OLD.status AND NOT ((OLD.status = 'Draft' AND NEW.status IN ('Submitted', 'Canceled')) OR (OLD.status = 'Submitted' AND NEW.status IN ('Under_Review', 'Draft', 'Canceled')) OR (OLD.status = 'Under_Review' AND NEW.status IN ('Approved', 'Rejected', 'Canceled')) OR (OLD.status = 'Approved' AND NEW.status IN ('Canceled')) OR (OLD.status = 'Rejected' AND NEW.status IN ('Draft')))
BEGIN
    SELECT RAISE(ABORT, 'INVALID_TRANSITION: status change not allowed');
END;

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

CREATE TRIGGER IF NOT EXISTS trg_approval_log_reviewer_role
BEFORE INSERT ON approval_log
BEGIN
    SELECT RAISE(ABORT, 'FORBIDDEN_REVIEWER: reviewer must have role Admin or Reviewer')
    WHERE (SELECT role FROM "user" WHERE id = NEW.reviewer_id) NOT IN ('Admin', 'Reviewer');
END;
