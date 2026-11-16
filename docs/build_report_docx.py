"""Build docs/Project_Advance_Report.docx (editable Word version of the report).

Reuses the real test results and screenshots saved by docs/build_report.py in docs/build/.
Run docs/build_report.py first if those files are missing or out of date.

Usage:  python docs/build_report_docx.py      (needs: pip install python-docx)
"""
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".pydeps"))

from docx import Document  # noqa: E402
from docx.enum.section import WD_ORIENT  # noqa: E402,F401
from docx.enum.table import WD_TABLE_ALIGNMENT  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_COLOR_INDEX  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Cm, Pt, RGBColor  # noqa: E402

BUILD = ROOT / "docs" / "build"
OUT = ROOT / "docs" / "Project_Advance_Report.docx"
BLUE = RGBColor(0x0B, 0x4F, 0x8A)
GREEN = RGBColor(0x1E, 0x7A, 0x46)
RED = RGBColor(0xB3, 0x26, 0x1E)
GREY = RGBColor(0x5B, 0x64, 0x75)

# ------------------------------------------------------------------ test data
suite = ET.parse(BUILD / "junit.xml").getroot().find("testsuite")
cases = []
for tc in suite.iter("testcase"):
    failed = tc.find("failure") is not None or tc.find("error") is not None
    cases.append((tc.get("classname").split(".")[-1], tc.get("name"), float(tc.get("time")), not failed))
n_total, n_pass = len(cases), sum(c[3] for c in cases)
pytest_out = (BUILD / "pytest_output.txt").read_text(encoding="utf-8")
m = re.search(r"best ([\d.]+) ms, worst ([\d.]+) ms", pytest_out)
tc05_best, tc05_worst = (m.group(1), m.group(2)) if m else ("n/a", "n/a")
summary_line = next((l for l in pytest_out.splitlines()[::-1] if " passed" in l or " failed" in l), "").strip("= ")


def status_of(name):
    return next((("Passed" if ok else "Failed") for _, n, _, ok in cases if n == name), "Not run")


# ------------------------------------------------------------------ document setup
doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
for side in ("left_margin", "right_margin"):
    setattr(sec, side, Cm(2))
sec.top_margin = sec.bottom_margin = Cm(2)
CONTENT_CM = 17.0

normal = doc.styles["Normal"]
normal.font.name = "Calibri"
normal.font.size = Pt(10.5)
normal.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
normal.paragraph_format.space_after = Pt(6)
for lvl, size in ((1, 15), (2, 12)):
    st = doc.styles[f"Heading {lvl}"]
    st.font.name, st.font.size, st.font.bold, st.font.color.rgb = "Calibri", Pt(size), True, BLUE
    st.element.rPr.rFonts.set(qn("w:asciiTheme"), "")
    st.paragraph_format.space_before = Pt(16 if lvl == 1 else 10)
    st.paragraph_format.space_after = Pt(6)
    st.paragraph_format.keep_with_next = True

# footer page numbers
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
for tag, text in (("begin", None), (None, "PAGE"), ("end", None)):
    r = fp.add_run()
    if tag:
        el = OxmlElement("w:fldChar")
        el.set(qn("w:fldCharType"), tag)
    else:
        el = OxmlElement("w:instrText")
        el.set(qn("xml:space"), "preserve")
        el.text = text
    r._r.append(el)
    r.font.size = Pt(9)

TOKEN = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\])")


def add_runs(par, text, size=None, color=None, bold=False):
    """Light markup: **bold**, `code`, [placeholder] (yellow, to fill in)."""
    for part in TOKEN.split(text):
        if not part:
            continue
        if part.startswith("**"):
            r = par.add_run(part[2:-2]); r.bold = True
        elif part.startswith("`"):
            r = par.add_run(part[1:-1]); r.font.name = "Consolas"; r.font.size = Pt((size or 10.5) - 1)
        elif part.startswith("["):
            r = par.add_run(part); r.bold = True; r.font.highlight_color = WD_COLOR_INDEX.YELLOW
        else:
            r = par.add_run(part)
        if bold:
            r.bold = True
        if size and not part.startswith("`"):
            r.font.size = Pt(size)
        if color is not None:
            r.font.color.rgb = color
    return par


def p(text, **kw):
    return add_runs(doc.add_paragraph(), text, **kw)


def h(text, level=1):
    doc.add_heading(text, level=level)


def bullets(items, style="List Bullet"):
    for it in items:
        add_runs(doc.add_paragraph(style=style), it)


def shade(cell, hex_fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hex_fill)
    tcPr.append(shd)


STATUS_COLORS = {"Yes": GREEN, "Passed": GREEN, "Done": GREEN, "No": RED, "Failed": RED}


def table(head, rows, widths, size=9):
    t = doc.add_table(rows=1, cols=len(head))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    scale = CONTENT_CM / sum(widths)
    for i, txt in enumerate(head):
        c = t.rows[0].cells[i]
        c.text = ""
        add_runs(c.paragraphs[0], txt, size=size, bold=True)
        shade(c, "E8EEF6")
    for row in rows:
        cells = t.add_row().cells
        for i, txt in enumerate(row):
            c = cells[i]
            c.text = ""
            txt = str(txt)
            color = STATUS_COLORS.get(txt.split(" ")[0]) if txt.split(" ")[0] in STATUS_COLORS else None
            add_runs(c.paragraphs[0], txt, size=size, color=color, bold=color is not None)
    for row in t.rows:
        for i, w in enumerate(widths):
            row.cells[i].width = Cm(w * scale)
        for c in row.cells:
            c.paragraphs[0].paragraph_format.space_after = Pt(0)
    # header row repeats on each page
    trPr = t.rows[0]._tr.get_or_add_trPr()
    th = OxmlElement("w:tblHeader"); th.set(qn("w:val"), "true"); trPr.append(th)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def figure(path, caption, width_cm=CONTENT_CM):
    par = doc.add_paragraph(); par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.add_run().add_picture(str(path), width=Cm(width_cm))
    par.paragraph_format.keep_with_next = True
    cap = doc.add_paragraph(); cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cap.add_run(caption); r.italic = True; r.font.size = Pt(9); r.font.color.rgb = GREY


def code_block(text, size=8):
    for line in text.splitlines():
        par = doc.add_paragraph()
        par.paragraph_format.space_after = Pt(0)
        par.paragraph_format.left_indent = Cm(0.3)
        r = par.add_run(line if line else " ")
        r.font.name = "Consolas"; r.font.size = Pt(size)
        pPr = par._p.get_or_add_pPr()
        shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:fill"), "F2F4F7"); pPr.append(shd)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def page_break():
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


today = date.today().strftime("%B %d, %Y")

# ------------------------------------------------------------------ cover
for _ in range(6):
    doc.add_paragraph()
t = doc.add_paragraph(); r = t.add_run("Yachay Events System (YES)"); r.bold = True; r.font.size = Pt(26); r.font.color.rgb = BLUE
s = doc.add_paragraph(); r = s.add_run("Project Advance Report — Database, API and GUI"); r.font.size = Pt(14); r.font.color.rgb = GREY
doc.add_paragraph()
table(["Item", "Detail"], [
    ["Author", "Marlon Andrés Almeida Coello"],
    ["Role", "Database Developer"],
    ["Institution", "Yachay Tech University"],
    ["Course", "[Course name]"],
    ["Instructor", "[Instructor name]"],
    ["Repository", "[GitHub repository URL]"],
    ["Date", today],
], [4, 9], size=10.5)
page_break()

# ------------------------------------------------------------------ 1. summary
CRUD = [
    ("organization", "Yes", "Yes", "Yes", "Yes", "Delete blocked by FK when referenced"),
    ("user", "Yes", "Yes", "Yes", "Yes", ""),
    ("venue", "Yes", "Yes", "Yes", "Yes", "+ availability lookup"),
    ("equipment", "Yes", "Yes", "Yes", "Yes", ""),
    ("event_proposal", "Yes", "Yes", "Yes", "Yes", "Edit only in Draft/Submitted; delete only Draft"),
    ("reservation", "Yes", "Yes", "Yes", "Yes", "Create/move return audience warnings"),
    ("event_equipment", "Yes", "Yes", "Yes", "Yes", "Managed under /proposals/{id}/equipment"),
    ("approval_log", "Yes", "Yes", "No", "No", "Audit trail: written by status changes, immutable by design"),
]
crud_done = sum(r[1:5].count("Yes") for r in CRUD)
crud_pct = round(100 * crud_done / (len(CRUD) * 4))
GUI_ROWS = [
    ("Dashboard: counters, audience-overlap warnings, upcoming reservations", "Yes"),
    ("Event proposals: list, filter, create, lifecycle changes with reviewer, delete drafts", "Yes"),
    ("Reservations: reserve an approved event, conflict and overlap messages, delete", "Yes"),
    ("Venues: list, create, delete", "Yes"),
    ("Organizations: list, create, delete (FK errors shown)", "Yes"),
    ("Edit forms for existing records", "No"),
    ("Users management screen", "No"),
    ("Equipment catalog and equipment requests", "No"),
    ("Reports: occupancy and club activity per semester", "No"),
    ("Login and role-based views", "No"),
]
gui_pct = round(100 * sum(r[1] == "Yes" for r in GUI_ROWS) / len(GUI_ROWS))

h("1. Progress summary")
table(["Tables implemented", "CRUD operations", "Tests passed", "GUI screens"],
      [["8", f"{crud_pct}%", f"{n_pass}/{n_total}", f"{gui_pct}%"]], [1, 1, 1, 1], size=11)
table(["Required item", "Target", "Status", "Evidence"], [
    ["Database designed and implemented", "MySQL / SQLite / other", "Done (SQLite)",
     "Sections 2–3, `sql/schema.sql`, `app/models.py`, `app/triggers.py`"],
    ["APIDB CRUD operations", "70% with test cases passed", f"Done — {crud_pct}% CRUD, {n_pass}/{n_total} tests passed",
     "Sections 4–6, `app/routers/`, `tests/`"],
    ["GUI design integrated with APIDB", "50%", f"Done — {gui_pct}% of screens, integrated", "Section 7, `static/`"],
], [4.2, 3.2, 3.8, 5.8])
p("**Scope change.** The original specification excluded a graphical frontend. For this advance a web GUI was added: "
  "it is served by the same FastAPI application and uses only the public API endpoints, so the database rules stay in one place.")

# ------------------------------------------------------------------ 2. database design
h("2. Database design")
p("The conceptual model of the specification was kept: **Organization**, **User**, **Venue**, **Event_Proposal**, "
  "**Reservation**, **Equipment** and **Approval_Log**, plus the associative table **event_equipment** that resolves the "
  "M:N relationship between proposals and equipment. All tables are in Third Normal Form: every non-key column depends only "
  "on its table's primary key, and repeated data (club, venue, equipment, user) is referenced through foreign keys.")
table(["Relationship", "Cardinality", "Implementation"], [
    ["organization – event_proposal", "1 : N", "`event_proposal.organization_id` → organization (RESTRICT)"],
    ["organization – user", "1 : N (optional)", "`user.organization_id` nullable for staff"],
    ["user – event_proposal", "1 : N", "`event_proposal.submitter_id` → user"],
    ["event_proposal – reservation", "1 : 1", "`reservation.event_id` UNIQUE → event_proposal"],
    ["venue – reservation", "1 : N", "`reservation.venue_id` → venue, never overlapping (trigger)"],
    ["event_proposal – equipment", "M : N", "`event_equipment(event_id, equipment_id)` composite PK"],
    ["user – approval_log", "1 : N", "`approval_log.reviewer_id` → user (Admin/Reviewer only)"],
], [5, 2.7, 9.3])
figure(BUILD / "spec_p7_0.png", "Figure 1. Logical data model (from the Database Design Specification).")
h("Changes made during implementation", 2)
table(["Change", "Reason"], [
    ["`venue.built_in_equipment` (TEXT)", "FR-05 asks to store the built-in equipment of each venue; the original dictionary had no column for it."],
    ["`approval_log.new_status` (VARCHAR 30)", "FR-07 asks to log status changes; the column records which decision each log entry approves."],
    ["UNIQUE on `venue.name` and `equipment.name`", "Avoid duplicated catalog entries."],
    ["CHECK lists on `organization.category`, `user.role`, `event_proposal.status`", "Keep values inside the allowed domains."],
    ["`reservation`: CHECK end_time > start_time", "Reject inverted time ranges."],
], [7, 10])

# ------------------------------------------------------------------ 3. implementation
h("3. Database implementation")
p("The schema is defined with SQLAlchemy 2.0 ORM models and created in SQLite by `init_db()`. Every connection runs "
  "`PRAGMA foreign_keys = ON` (NFR-04). Constraint names follow Annex B through a SQLAlchemy naming convention "
  "(`pk_venue`, `fk_event_proposal_organization`, `uq_organization_name`, `ck_venue_capacity_positive`, "
  "`idx_reservation_venue_time`). The generated DDL is in `sql/schema.sql`.")
h("Indexes (NFR-02)", 2)
table(["Index", "Columns", "Used by"], [
    ["idx_reservation_venue_time", "venue_id, start_time, end_time", "Double-booking trigger, availability lookup, occupancy report"],
    ["idx_reservation_time", "start_time, end_time", "Reservation listing by date"],
    ["idx_event_proposal_status", "status", "Filtering proposals by lifecycle stage"],
    ["idx_event_proposal_target_audience", "target_audience", "Audience-overlap detection"],
    ["idx_event_proposal_organization_id", "organization_id", "Club activity report"],
    ["idx_approval_log_event_id", "event_id", "Approval history"],
], [6, 4.8, 6.2])
h("Business rules enforced by triggers", 2)
p("The main rules live in the database, so they hold even if data is written without the API:")
table(["Trigger", "Requirement", "Rule"], [
    ["trg_reservation_no_overlap_insert / _update", "FR-02", "Aborts a reservation that overlaps another one in the same venue."],
    ["trg_reservation_requires_approved", "FR-03", "Only proposals in status Approved can hold a reservation."],
    ["trg_event_proposal_initial_status", "FR-03", "New proposals start as Draft or Submitted."],
    ["trg_event_proposal_status_flow", "FR-03", "Allows only the defined lifecycle transitions."],
    ["trg_event_proposal_decision_logged", "FR-07", "Approved/Rejected requires a matching approval_log entry."],
    ["trg_approval_log_reviewer_role", "FR-07", "Only Admin or Reviewer users can write approval logs."],
], [6.5, 2.3, 8.2])
p("Allowed lifecycle: Draft → Submitted → Under_Review → Approved / Rejected; Submitted → Draft; Rejected → Draft; "
  "Draft, Submitted, Under_Review and Approved → Canceled. Canceling an approved event deletes its reservation and frees the venue.")

# ------------------------------------------------------------------ 4. API design
page_break()
h("4. API design")
p("The API is built with FastAPI and organized in layers: **routers** (HTTP endpoints) → **Pydantic schemas** (validation) → "
  "**SQLAlchemy session** (one transaction per request) → **SQLite** (constraints and triggers). Database errors are translated "
  "to HTTP codes in `app/errors.py`: 404 not found, 409 conflict (double booking, invalid transition, foreign key), "
  "422 invalid data, 403 reviewer without permission. Interactive documentation is generated at `/docs`.")
table(["Method", "Path", "Purpose"], [
    ["GET", "`/api/{organizations|users|venues|equipment}`", "List records"],
    ["POST", "`/api/{organizations|users|venues|equipment}`", "Create a record"],
    ["GET · PUT · DELETE", "`/api/{resource}/{id}`", "Read, update, delete one record"],
    ["GET", "`/api/venues/{id}/availability`", "Free/busy check for a time range (NFR-02)"],
    ["GET · POST", "`/api/proposals`", "List (filter by status, club, audience) and create (atomic with equipment)"],
    ["GET · PUT · DELETE", "`/api/proposals/{id}`", "Detail with equipment, logs and reservation"],
    ["POST", "`/api/proposals/{id}/status`", "Lifecycle transition; writes approval_log in the same transaction"],
    ["GET", "`/api/proposals/{id}/logs`", "Approval history (FR-07)"],
    ["POST · DELETE", "`/api/proposals/{id}/equipment[/{equipment_id}]`", "Request or remove equipment (M:N)"],
    ["GET · POST", "`/api/reservations`", "List (filter by venue/time) and reserve a venue"],
    ["GET · PUT · DELETE", "`/api/reservations/{id}`", "Read, move, delete a reservation"],
    ["GET", "`/api/reports/occupancy`", "Occupancy rate per venue in a window (FR-06)"],
    ["GET", "`/api/reports/club-activity`", "Club activity per semester (FR-06)"],
    ["GET", "`/api/reports/audience-overlaps`", "Approved events with the same audience at the same time (FR-04)"],
], [3, 7, 7])
p("**Atomic operations (NFR-05).** Creating a proposal with equipment, changing a status together with its approval log, and "
  "canceling an event together with its reservation each run in one transaction; on any error the whole transaction is rolled "
  "back (verified by `test_proposal_creation_is_atomic` and TC-02).")
figure(BUILD / "shot_swagger.png", "Figure 2. Auto-generated API documentation (Swagger UI) at /docs.", width_cm=12.5)

# ------------------------------------------------------------------ 5. CRUD
h("5. API implementation and CRUD operations")
table(["Table", "Create", "Read", "Update", "Delete", "Notes"], CRUD, [3.4, 1.5, 1.5, 1.5, 1.5, 7.6])
p(f"**Coverage: {crud_done} of {len(CRUD) * 4} operations ({crud_pct}%).** The two missing operations (update and delete of "
  "`approval_log`) are intentionally not exposed, because the log is an audit trail.")

# ------------------------------------------------------------------ 6. tests
h("6. Test cases and results")
p(f"The suite runs with `pytest`; each test uses a fresh SQLite file with all constraints and triggers. "
  f"Result of the run used for this report: **{summary_line}**.")
h("6.1 Specification test cases (Section 4 of the design document)", 2)
SPEC = [
    ("TC-01", "FR-02", "Prevent double booking of the same venue",
     "Auditorio Módulo 1 reserved 2026-10-15 10:00–12:00; a second reservation 11:00–13:00 is attempted.",
     "HTTP 409 `VENUE_CONFLICT`; trigger `trg_reservation_no_overlap_insert` aborts the insert, also through raw SQL.",
     ["test_tc01_prevent_double_booking_same_venue", "test_tc01_trigger_blocks_direct_sql_insert"]),
    ("TC-02", "FR-03", "Check proposal status flow", "Proposal in Draft is set directly to Approved.",
     "HTTP 409 `INVALID_TRANSITION`; status stays Draft and the log insert is rolled back. Raw SQL approval without a log fails with `LOG_REQUIRED`.",
     ["test_tc02_draft_cannot_jump_to_approved", "test_tc02_approval_without_log_is_blocked_in_database"]),
    ("TC-03", "FR-04", "Detect target audience conflict",
     "Event A (Computer Engineering) 14:00 in Aula 102; Event B (Computer Engineering) 14:30 in Aula 104.",
     "Reservation B is created (different rooms) and the response carries one audience-overlap warning; the overlap also appears in `/api/reports/audience-overlaps`.",
     ["test_tc03_audience_overlap_warning"]),
    ("TC-04", "NFR-04", "Foreign key deletion", "Club IEEE ComSoc has proposals; DELETE of the organization is attempted.",
     "HTTP 409 via API; FOREIGN KEY constraint failed via raw SQL; `PRAGMA foreign_keys = 1` confirmed.",
     ["test_tc04_delete_organization_with_proposals_is_blocked", "test_tc04_foreign_keys_enabled_at_sql_level"]),
    ("TC-05", "FR-06", "Occupancy query performance", "500 reservation records loaded; room-usage percentage query executed.",
     f"Best of 5 runs: **{tc05_best} ms** (worst {tc05_worst} ms), under the 50 ms target; index `idx_reservation_venue_time` is used.",
     ["test_tc05_occupancy_query_performance", "test_tc05_reservation_lookup_uses_index"]),
]
table(["ID", "Req.", "Description", "Preconditions / steps", "Actual result", "Status"],
      [[f"**{a}**", b, c, d, e, "Passed" if all(status_of(x) == "Passed" for x in tests) else "Failed"]
       for a, b, c, d, e, tests in SPEC], [1.4, 1.5, 2.8, 4.4, 5.4, 1.5], size=8.5)
h("6.2 Full test list", 2)
table(["File", "Test", "Time (s)", "Result"],
      [[cls, f"`{name}`", f"{t:.3f}", "Passed" if ok else "Failed"] for cls, name, t, ok in cases], [3.2, 10, 1.8, 2], size=8)

# ------------------------------------------------------------------ 7. GUI
page_break()
h("7. GUI design and integration")
p("The GUI is a single web page (`static/index.html`, `app.js`, `style.css`) served at `/`. It calls the API with `fetch`, "
  "so every action goes through the same validation and database rules. Errors returned by the API (for example a double "
  "booking) are shown to the user as messages.")
table(["Screen / feature", "Implemented"], GUI_ROWS, [13.5, 3.5])
p(f"**Progress: {gui_pct}% of the planned screens.**")
figure(BUILD / "shot_dashboard.png", "Figure 3. Dashboard with the audience-overlap warning (FR-04) and upcoming reservations.")
figure(BUILD / "shot_proposals.png", "Figure 4. Event proposals: creation form, status filter and lifecycle actions.")
figure(BUILD / "shot_reservations.png", "Figure 5. Reservations: only approved events can reserve; conflicts are rejected by the database.")
figure(BUILD / "shot_venues.png", "Figure 6. Venues with capacity and built-in equipment (FR-05).")

# ------------------------------------------------------------------ 8. repository
page_break()
h("8. Repository and documentation")
code_block("""yes-project/
├── app/
│   ├── main.py            FastAPI app, serves GUI
│   ├── database.py        engine, PRAGMA foreign_keys, init_db()
│   ├── models.py          8 ORM models, Annex B naming
│   ├── triggers.py        business-rule triggers
│   ├── schemas.py         Pydantic validation
│   ├── errors.py          DB error → HTTP mapping
│   ├── seed.py            demo data
│   └── routers/           basic.py, proposals.py, reservations.py, reports.py
├── static/                index.html, app.js, style.css
├── tests/                 conftest.py, test_spec_cases.py, test_crud.py
├── sql/schema.sql         generated DDL
├── docs/                  report, manual, report build scripts
├── Dockerfile, docker-compose.yml, requirements.txt, pytest.ini, README.md""")
h("How to run", 2)
code_block("""docker compose up --build     # GUI: http://localhost:8000   API docs: http://localhost:8000/docs
pytest -v                     # run the test suite (local Python environment)""")

# ------------------------------------------------------------------ 9-10
h("9. Demonstration plan")
bullets([
    "Start the system with `docker compose up --build` and open the dashboard.",
    "Show the audience-overlap warning between two Computer Engineering events (FR-04).",
    "Create a proposal, submit it, move it to review and approve it with a reviewer; show the approval log (FR-03, FR-07).",
    "Try to approve a Draft proposal directly and show the rejection (TC-02).",
    "Reserve a venue for the approved event, then try an overlapping reservation in the same venue (TC-01).",
    "Try to delete a club that has proposals (TC-04).",
    f"Run `pytest -v` and show {n_pass}/{n_total} tests passing, including the TC-05 timing.",
], style="List Number")
h("10. Next steps")
bullets([
    "GUI: edit forms, users and equipment screens, occupancy and club-activity report pages.",
    "Authentication and role-based permissions (Leader, Reviewer, Admin).",
    "Equipment availability by time slot (today only total stock is checked).",
])

# ------------------------------------------------------------------ 11. AI
h("11. Use of generative AI")
table(["Section / task", "Prompt used", "Model", "Version", "Date"], [
    ["LaTeX formatting (specification)", '"Format the data dictionary and requirements tables into clean LaTeX longtable environment code."', "Gemini", "2.5", "2026-09-24"],
    ["Grammar check (specification)", '"Check the English grammar of the database project description and make it concise."', "Gemini", "2.5", "2026-09-24"],
    ["Implementation of the advance: SQLAlchemy models, triggers, FastAPI endpoints, tests, GUI, Docker files and this report",
     '"Build the project advance from scratch from the Database Design Specification: database in SQLite, CRUD API with FastAPI and SQLAlchemy with passing test cases, and a GUI integrated with the API."',
     "Claude (Anthropic)", "Opus 5.5", today],
], [4.2, 6.6, 2.4, 1.6, 2.2], size=8.5)
p("[Author: review and adjust this section to describe exactly how you used each tool and what you verified yourself, following your course policy.]")

# ------------------------------------------------------------------ annex
page_break()
h("Annex A. Test run output")
code_block(pytest_out[-12000:].strip(), size=7)

doc.save(OUT)
print(f"Saved {OUT}  ({n_pass}/{n_total} tests, CRUD {crud_pct}%, GUI {gui_pct}%)")
