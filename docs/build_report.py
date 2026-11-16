"""Build docs/Project_Advance_Report.pdf.

1. Runs the pytest suite and keeps its real output.
2. Takes screenshots of the running GUI (server must be up on http://localhost:8000).
3. Renders docs/report.html and prints it to PDF with headless Chrome.

Usage:  python docs/build_report.py
"""
import base64
import html
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "docs" / "build"
BUILD.mkdir(parents=True, exist_ok=True)
CHROME = os.getenv("CHROME", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
BASE_URL = os.getenv("YES_URL", "http://localhost:8000")
ENV = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT), str(ROOT / ".pydeps")])}

# ---------------------------------------------------------------- tests
junit = BUILD / "junit.xml"
proc = subprocess.run(
    [sys.executable, "-m", "pytest", "-v", "-s", "-p", "no:cacheprovider", "-W", "ignore::DeprecationWarning", f"--junitxml={junit}"],
    cwd=ROOT, env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace",
)
pytest_out = proc.stdout.replace(str(ROOT), "yes-project")
(BUILD / "pytest_output.txt").write_text(pytest_out, encoding="utf-8")
suite = ET.parse(junit).getroot().find("testsuite")
cases = []
for tc in suite.iter("testcase"):
    failed = tc.find("failure") is not None or tc.find("error") is not None
    cases.append((tc.get("classname").split(".")[-1], tc.get("name"), float(tc.get("time")), not failed))
n_total, n_pass = len(cases), sum(c[3] for c in cases)
tc05 = re.search(r"best ([\d.]+) ms, worst ([\d.]+) ms", pytest_out)
tc05_best, tc05_worst = (tc05.group(1), tc05.group(2)) if tc05 else ("n/a", "n/a")
summary_line = next((l for l in pytest_out.splitlines()[::-1] if " passed" in l or " failed" in l), "").strip("= ")

# ---------------------------------------------------------------- screenshots
def shot(name: str, url: str, height: int = 860) -> str:
    out = BUILD / f"shot_{name}.png"
    subprocess.run([
        CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
        f"--user-data-dir={BUILD / 'chrome-profile'}", f"--window-size=1280,{height}",
        "--virtual-time-budget=5000", f"--screenshot={out}", url,
    ], check=True, capture_output=True)
    return out

shots = {
    "dashboard": shot("dashboard", f"{BASE_URL}/#dashboard", 900),
    "proposals": shot("proposals", f"{BASE_URL}/#proposals", 720),
    "reservations": shot("reservations", f"{BASE_URL}/#reservations", 720),
    "venues": shot("venues", f"{BASE_URL}/#venues", 620),
    "swagger": shot("swagger", f"{BASE_URL}/docs", 1500),
}


def img(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


er_png = BUILD / "spec_p7_0.png"

# ---------------------------------------------------------------- content helpers
def table(head, rows, widths=None, cls=""):
    cols = "".join(f'<col style="width:{w}">' for w in widths) if widths else ""
    th = "".join(f"<th>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><colgroup>{cols}</colgroup><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


YES, NO, PART = '<span class="ok">Yes</span>', '<span class="no">No</span>', '<span class="part">Partial</span>'


def status_of(test_name):
    return next((("Passed" if ok else "Failed") for _, n, _, ok in cases if n == test_name), "Not run")


SPEC_TCS = [
    ("TC-01", "FR-02", "Prevent double booking of the same venue",
     "Auditorio Módulo 1 reserved 2026-10-15 10:00–12:00; a second reservation 11:00–13:00 is attempted.",
     "HTTP 409 <code>VENUE_CONFLICT</code>; trigger <code>trg_reservation_no_overlap_insert</code> aborts the insert, also through raw SQL.",
     ["test_tc01_prevent_double_booking_same_venue", "test_tc01_trigger_blocks_direct_sql_insert"]),
    ("TC-02", "FR-03", "Check proposal status flow",
     "Proposal in Draft is set directly to Approved.",
     "HTTP 409 <code>INVALID_TRANSITION</code>; status stays Draft and the log insert is rolled back. Raw SQL approval without a log fails with <code>LOG_REQUIRED</code>.",
     ["test_tc02_draft_cannot_jump_to_approved", "test_tc02_approval_without_log_is_blocked_in_database"]),
    ("TC-03", "FR-04", "Detect target audience conflict",
     "Event A (Computer Engineering) 14:00 in Aula 102; Event B (Computer Engineering) 14:30 in Aula 104.",
     "Reservation B is created (different rooms) and the response carries one audience-overlap warning; the overlap also appears in <code>/api/reports/audience-overlaps</code>.",
     ["test_tc03_audience_overlap_warning"]),
    ("TC-04", "NFR-04", "Foreign key deletion",
     "Club IEEE ComSoc has proposals; <code>DELETE</code> of the organization is attempted.",
     "HTTP 409 via API; <code>FOREIGN KEY constraint failed</code> via raw SQL; <code>PRAGMA foreign_keys = 1</code> confirmed.",
     ["test_tc04_delete_organization_with_proposals_is_blocked", "test_tc04_foreign_keys_enabled_at_sql_level"]),
    ("TC-05", "FR-06", "Occupancy query performance",
     "500 reservation records loaded; room-usage percentage query executed.",
     f"Best of 5 runs: <b>{tc05_best} ms</b> (worst {tc05_worst} ms), under the 50 ms target; index <code>idx_reservation_venue_time</code> is used.",
     ["test_tc05_occupancy_query_performance", "test_tc05_reservation_lookup_uses_index"]),
]
spec_rows = []
for tid, req, desc, pre, result, tests in SPEC_TCS:
    st = "Passed" if all(status_of(t) == "Passed" for t in tests) else "Failed"
    spec_rows.append([f"<b>{tid}</b>", req, desc, pre, result,
                      f'<span class="{"ok" if st == "Passed" else "no"}">{st}</span>'])

CRUD = [
    ("organization", YES, YES, YES, YES, "Delete blocked by FK when referenced"),
    ("user", YES, YES, YES, YES, ""),
    ("venue", YES, YES, YES, YES, "+ availability lookup"),
    ("equipment", YES, YES, YES, YES, ""),
    ("event_proposal", YES, YES, YES, YES, "Edit only in Draft/Submitted; delete only Draft"),
    ("reservation", YES, YES, YES, YES, "Create/move return audience warnings"),
    ("event_equipment", YES, YES, YES, YES, "Managed under /proposals/{id}/equipment"),
    ("approval_log", YES, YES, NO, NO, "Audit trail: written by status changes, immutable by design"),
]
crud_done = sum(r[1:5].count(YES) for r in CRUD)
crud_pct = round(100 * crud_done / (len(CRUD) * 4))

ENDPOINTS = [
    ("GET", "/api/{organizations|users|venues|equipment}", "List records"),
    ("POST", "/api/{organizations|users|venues|equipment}", "Create a record"),
    ("GET · PUT · DELETE", "/api/{resource}/{id}", "Read, update, delete one record"),
    ("GET", "/api/venues/{id}/availability", "Free/busy check for a time range (NFR-02)"),
    ("GET · POST", "/api/proposals", "List (filter by status, club, audience) and create (atomic with equipment)"),
    ("GET · PUT · DELETE", "/api/proposals/{id}", "Detail with equipment, logs and reservation"),
    ("POST", "/api/proposals/{id}/status", "Lifecycle transition; writes approval_log in the same transaction"),
    ("GET", "/api/proposals/{id}/logs", "Approval history (FR-07)"),
    ("POST · DELETE", "/api/proposals/{id}/equipment[/{equipment_id}]", "Request or remove equipment (M:N)"),
    ("GET · POST", "/api/reservations", "List (filter by venue/time) and reserve a venue"),
    ("GET · PUT · DELETE", "/api/reservations/{id}", "Read, move, delete a reservation"),
    ("GET", "/api/reports/occupancy", "Occupancy rate per venue in a window (FR-06)"),
    ("GET", "/api/reports/club-activity", "Club activity per semester (FR-06)"),
    ("GET", "/api/reports/audience-overlaps", "Approved events with the same audience at the same time (FR-04)"),
]

TRIGGER_ROWS = [
    ("trg_reservation_no_overlap_insert / _update", "FR-02", "Aborts a reservation that overlaps another one in the same venue."),
    ("trg_reservation_requires_approved", "FR-03", "Only proposals in status Approved can hold a reservation."),
    ("trg_event_proposal_initial_status", "FR-03", "New proposals start as Draft or Submitted."),
    ("trg_event_proposal_status_flow", "FR-03", "Allows only the defined lifecycle transitions."),
    ("trg_event_proposal_decision_logged", "FR-07", "Approved/Rejected requires a matching approval_log entry."),
    ("trg_approval_log_reviewer_role", "FR-07", "Only Admin or Reviewer users can write approval logs."),
]

GUI_ROWS = [
    ("Dashboard: counters, audience-overlap warnings, upcoming reservations", YES),
    ("Event proposals: list, filter, create, lifecycle changes with reviewer, delete drafts", YES),
    ("Reservations: reserve an approved event, conflict and overlap messages, delete", YES),
    ("Venues: list, create, delete", YES),
    ("Organizations: list, create, delete (FK errors shown)", YES),
    ("Edit forms for existing records", NO),
    ("Users management screen", NO),
    ("Equipment catalog and equipment requests", NO),
    ("Reports: occupancy and club activity per semester", NO),
    ("Login and role-based views", NO),
]
gui_pct = round(100 * sum(r[1] == YES for r in GUI_ROWS) / len(GUI_ROWS))

tests_rows = [[cls, f"<code>{html.escape(name)}</code>", f"{t:.3f}",
               f'<span class="{"ok" if ok else "no"}">{"Passed" if ok else "Failed"}</span>'] for cls, name, t, ok in cases]

today = date.today().strftime("%B %d, %Y")

# ---------------------------------------------------------------- HTML
HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>YES Project Advance Report</title>
<style>
@page {{ size: A4; margin: 18mm 16mm 18mm 16mm; }}
body {{ font-family: "Segoe UI", Arial, sans-serif; color: #1d2433; font-size: 10.5pt; line-height: 1.45; }}
h1 {{ font-size: 20pt; color: #0b4f8a; margin: 0 0 4px; }}
h2 {{ font-size: 14pt; color: #0b4f8a; border-bottom: 2px solid #0b4f8a; padding-bottom: 3px; margin: 22px 0 8px; break-after: avoid; }}
h3 {{ font-size: 11.5pt; margin: 14px 0 6px; break-after: avoid; }}
p {{ margin: 0 0 8px; }}
table {{ width: 100%; border-collapse: collapse; margin: 6px 0 12px; font-size: 9pt; break-inside: auto; }}
th, td {{ border: 1px solid #c9d1dc; padding: 4px 6px; text-align: left; vertical-align: top; }}
th {{ background: #e8eef6; }}
tr {{ break-inside: avoid; }}
code {{ font-family: Consolas, monospace; font-size: 8.5pt; background: #f2f4f7; padding: 0 2px; }}
pre {{ font-family: Consolas, monospace; font-size: 7.5pt; background: #f6f8fa; border: 1px solid #dde2ea; padding: 8px; white-space: pre-wrap; }}
.ok {{ color: #1e7a46; font-weight: 600; }} .no {{ color: #b3261e; font-weight: 600; }} .part {{ color: #a15c00; font-weight: 600; }}
.cover {{ height: 245mm; display: flex; flex-direction: column; justify-content: center; break-after: page; }}
.cover .sub {{ font-size: 14pt; color: #5b6475; margin-bottom: 30px; }}
.cover table {{ width: 70%; font-size: 10.5pt; }}
.fig {{ text-align: center; margin: 8px 0 14px; break-inside: avoid; }}
.fig img {{ max-width: 100%; border: 1px solid #c9d1dc; }}
.fig .cap {{ font-size: 9pt; color: #5b6475; font-style: italic; margin-top: 4px; }}
.kpi {{ display: flex; gap: 10px; margin: 8px 0 12px; }}
.kpi div {{ flex: 1; border: 1px solid #c9d1dc; border-radius: 6px; padding: 8px; text-align: center; }}
.kpi b {{ display: block; font-size: 18pt; color: #0b4f8a; }}
.note {{ background: #fff6e5; border-left: 4px solid #a15c00; padding: 6px 10px; font-size: 9.5pt; }}
.pb {{ break-before: page; }}
</style></head><body>

<div class="cover">
  <h1>Yachay Events System (YES)</h1>
  <div class="sub">Project Advance Report — Database, API and GUI</div>
  {table(["Item", "Detail"], [
      ["Author", "Marlon Andrés Almeida Coello"],
      ["Role", "Database Developer"],
      ["Institution", "Yachay Tech University"],
      ["Course", "[Course name]"],
      ["Instructor", "[Instructor name]"],
      ["Repository", "[GitHub repository URL]"],
      ["Date", today],
  ], ["30%", "70%"])}
</div>

<h2>1. Progress summary</h2>
<div class="kpi">
  <div><b>8</b>tables implemented</div>
  <div><b>{crud_pct}%</b>CRUD operations</div>
  <div><b>{n_pass}/{n_total}</b>tests passed</div>
  <div><b>{gui_pct}%</b>GUI screens</div>
</div>
{table(["Required item", "Target", "Status", "Evidence"], [
    ["Database designed and implemented", "MySQL / SQLite / other", '<span class="ok">Done (SQLite)</span>', "Sections 2–3, <code>sql/schema.sql</code>, <code>app/models.py</code>, <code>app/triggers.py</code>"],
    ["APIDB CRUD operations", "70% with test cases passed", f'<span class="ok">{crud_pct}% — {n_pass}/{n_total} tests passed</span>', "Sections 4–6, <code>app/routers/</code>, <code>tests/</code>"],
    ["GUI design integrated with APIDB", "50%", f'<span class="ok">{gui_pct}% — integrated</span>', "Section 7, <code>static/</code>"],
], ["24%", "18%", "22%", "36%"])}
<p><b>Scope change.</b> The original specification excluded a graphical frontend. For this advance a web GUI was added: it is served by the same FastAPI application and uses only the public API endpoints, so the database rules stay in one place.</p>

<h2>2. Database design</h2>
<p>The conceptual model of the specification was kept: <b>Organization</b>, <b>User</b>, <b>Venue</b>, <b>Event_Proposal</b>, <b>Reservation</b>, <b>Equipment</b> and <b>Approval_Log</b>, plus the associative table <b>event_equipment</b> that resolves the M:N relationship between proposals and equipment. All tables are in Third Normal Form: every non-key column depends only on its table's primary key, and repeated data (club, venue, equipment, user) is referenced through foreign keys.</p>
{table(["Relationship", "Cardinality", "Implementation"], [
    ["organization – event_proposal", "1 : N", "<code>event_proposal.organization_id</code> → organization (RESTRICT)"],
    ["organization – user", "1 : N (optional)", "<code>user.organization_id</code> nullable for staff"],
    ["user – event_proposal", "1 : N", "<code>event_proposal.submitter_id</code> → user"],
    ["event_proposal – reservation", "1 : 1", "<code>reservation.event_id</code> UNIQUE → event_proposal"],
    ["venue – reservation", "1 : N", "<code>reservation.venue_id</code> → venue, never overlapping (trigger)"],
    ["event_proposal – equipment", "M : N", "<code>event_equipment(event_id, equipment_id)</code> composite PK"],
    ["user – approval_log", "1 : N", "<code>approval_log.reviewer_id</code> → user (Admin/Reviewer only)"],
], ["32%", "16%", "52%"])}
<div class="fig"><img src="{img(er_png)}"><div class="cap">Figure 1. Logical data model (from the Database Design Specification).</div></div>
<h3>Changes made during implementation</h3>
{table(["Change", "Reason"], [
    ["<code>venue.built_in_equipment</code> (TEXT)", "FR-05 asks to store the built-in equipment of each venue; the original dictionary had no column for it."],
    ["<code>approval_log.new_status</code> (VARCHAR 30)", "FR-07 asks to log status changes; the column records which decision each log entry approves."],
    ["UNIQUE on <code>venue.name</code> and <code>equipment.name</code>", "Avoid duplicated catalog entries."],
    ["CHECK lists on <code>organization.category</code>, <code>user.role</code>, <code>event_proposal.status</code>", "Keep values inside the allowed domains."],
    ["<code>reservation</code>: CHECK <code>end_time &gt; start_time</code>", "Reject inverted time ranges."],
], ["40%", "60%"])}

<h2>3. Database implementation</h2>
<p>The schema is defined with SQLAlchemy 2.0 ORM models and created in SQLite by <code>init_db()</code>. Every connection runs <code>PRAGMA foreign_keys = ON</code> (NFR-04). Constraint names follow Annex B through a SQLAlchemy naming convention (<code>pk_venue</code>, <code>fk_event_proposal_organization</code>, <code>uq_organization_name</code>, <code>ck_venue_capacity_positive</code>, <code>idx_reservation_venue_time</code>). The generated DDL is in <code>sql/schema.sql</code>.</p>
<h3>Indexes (NFR-02)</h3>
{table(["Index", "Columns", "Used by"], [
    ["idx_reservation_venue_time", "venue_id, start_time, end_time", "Double-booking trigger, availability lookup, occupancy report"],
    ["idx_reservation_time", "start_time, end_time", "Reservation listing by date"],
    ["idx_event_proposal_status", "status", "Filtering proposals by lifecycle stage"],
    ["idx_event_proposal_target_audience", "target_audience", "Audience-overlap detection"],
    ["idx_event_proposal_organization_id", "organization_id", "Club activity report"],
    ["idx_approval_log_event_id", "event_id", "Approval history"],
], ["36%", "28%", "36%"])}
<h3>Business rules enforced by triggers</h3>
<p>The main rules live in the database, so they hold even if data is written without the API:</p>
{table(["Trigger", "Requirement", "Rule"], TRIGGER_ROWS, ["38%", "14%", "48%"])}
<p>Allowed lifecycle: Draft → Submitted → Under_Review → Approved / Rejected; Submitted → Draft; Rejected → Draft; Draft, Submitted, Under_Review and Approved → Canceled. Canceling an approved event deletes its reservation and frees the venue.</p>

<h2 class="pb">4. API design</h2>
<p>The API is built with FastAPI and organized in layers: <b>routers</b> (HTTP endpoints) → <b>Pydantic schemas</b> (validation) → <b>SQLAlchemy session</b> (one transaction per request) → <b>SQLite</b> (constraints and triggers). Database errors are translated to HTTP codes in <code>app/errors.py</code>: 404 not found, 409 conflict (double booking, invalid transition, foreign key), 422 invalid data, 403 reviewer without permission. Interactive documentation is generated at <code>/docs</code>.</p>
{table(["Method", "Path", "Purpose"], [[m, f"<code>{p}</code>", d] for m, p, d in ENDPOINTS], ["16%", "42%", "42%"])}
<p><b>Atomic operations (NFR-05).</b> Creating a proposal with equipment, changing a status together with its approval log, and canceling an event together with its reservation each run in one transaction; on any error the whole transaction is rolled back (verified by <code>test_proposal_creation_is_atomic</code> and TC-02).</p>
<div class="fig"><img src="{img(shots['swagger'])}" style="max-height:150mm"><div class="cap">Figure 2. Auto-generated API documentation (Swagger UI) at /docs.</div></div>

<h2 class="pb">5. API implementation and CRUD operations</h2>
{table(["Table", "Create", "Read", "Update", "Delete", "Notes"], CRUD, ["20%", "9%", "9%", "9%", "9%", "44%"])}
<p><b>Coverage: {crud_done} of {len(CRUD) * 4} operations ({crud_pct}%).</b> The two missing operations (update and delete of <code>approval_log</code>) are intentionally not exposed, because the log is an audit trail.</p>

<h2>6. Test cases and results</h2>
<p>The suite runs with <code>pytest</code>; each test uses a fresh SQLite file with all constraints and triggers. Result of the run used for this report: <b>{html.escape(summary_line)}</b>.</p>
<h3>6.1 Specification test cases (Section 4 of the design document)</h3>
{table(["ID", "Req.", "Description", "Preconditions / steps", "Actual result", "Status"], spec_rows, ["7%", "8%", "15%", "27%", "34%", "9%"])}
<h3>6.2 Full test list</h3>
{table(["File", "Test", "Time (s)", "Result"], tests_rows, ["20%", "58%", "10%", "12%"])}

<h2 class="pb">7. GUI design and integration</h2>
<p>The GUI is a single web page (<code>static/index.html</code>, <code>app.js</code>, <code>style.css</code>) served at <code>/</code>. It calls the API with <code>fetch</code>, so every action goes through the same validation and database rules. Errors returned by the API (for example a double booking) are shown to the user as messages.</p>
{table(["Screen / feature", "Implemented"], GUI_ROWS, ["80%", "20%"])}
<p><b>Progress: {gui_pct}% of the planned screens.</b></p>
<div class="fig"><img src="{img(shots['dashboard'])}"><div class="cap">Figure 3. Dashboard with the audience-overlap warning (FR-04) and upcoming reservations.</div></div>
<div class="fig"><img src="{img(shots['proposals'])}"><div class="cap">Figure 4. Event proposals: creation form, status filter and lifecycle actions.</div></div>
<div class="fig"><img src="{img(shots['reservations'])}"><div class="cap">Figure 5. Reservations: only approved events can reserve; conflicts are rejected by the database.</div></div>
<div class="fig"><img src="{img(shots['venues'])}"><div class="cap">Figure 6. Venues with capacity and built-in equipment (FR-05).</div></div>

<h2 class="pb">8. Repository and documentation</h2>
<pre>yes-project/
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
├── docs/build_report.py   builds this report
├── Dockerfile, docker-compose.yml, requirements.txt, README.md</pre>
<h3>How to run</h3>
<pre>docker compose up --build          # GUI: http://localhost:8000   API docs: http://localhost:8000/docs
pytest -v                          # run the test suite (local Python environment)</pre>

<h2>9. Demonstration plan</h2>
<ol>
  <li>Start the system with <code>docker compose up --build</code> and open the dashboard.</li>
  <li>Show the audience-overlap warning between two Computer Engineering events (FR-04).</li>
  <li>Create a proposal, submit it, move it to review and approve it with a reviewer; show the approval log (FR-03, FR-07).</li>
  <li>Try to approve a Draft proposal directly and show the rejection (TC-02).</li>
  <li>Reserve a venue for the approved event, then try an overlapping reservation in the same venue (TC-01).</li>
  <li>Try to delete a club that has proposals (TC-04).</li>
  <li>Run <code>pytest -v</code> and show {n_pass}/{n_total} tests passing, including the TC-05 timing.</li>
</ol>

<h2>10. Next steps</h2>
<ul>
  <li>GUI: edit forms, users and equipment screens, occupancy and club-activity report pages.</li>
  <li>Authentication and role-based permissions (Leader, Reviewer, Admin).</li>
  <li>Equipment availability by time slot (today only total stock is checked).</li>
</ul>

<h2>11. Use of generative AI</h2>
{table(["Section / task", "Prompt used", "Model", "Version", "Date"], [
    ["LaTeX formatting (specification)", '"Format the data dictionary and requirements tables into clean LaTeX longtable environment code."', "Gemini", "2.5", "2026-09-24"],
    ["Grammar check (specification)", '"Check the English grammar of the database project description and make it concise."', "Gemini", "2.5", "2026-09-24"],
    ["Implementation of the advance: SQLAlchemy models, triggers, FastAPI endpoints, tests, GUI, Docker files and this report", '"Build the project advance from scratch from the Database Design Specification: database in SQLite, CRUD API with FastAPI and SQLAlchemy with passing test cases, and a GUI integrated with the API."', "Claude (Anthropic)", "Opus 5.5", today],
], ["26%", "40%", "13%", "9%", "12%"])}
<p class="note">[Author: review and adjust this section to describe exactly how you used each tool and what you verified yourself, following your course policy.]</p>

<h2 class="pb">Annex A. Test run output</h2>
<pre>{html.escape(pytest_out[-12000:])}</pre>
</body></html>"""

report_html = ROOT / "docs" / "report.html"
report_html.write_text(HTML, encoding="utf-8")
pdf = ROOT / "docs" / "Project_Advance_Report.pdf"
subprocess.run([
    CHROME, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={BUILD / 'chrome-profile'}",
    "--no-pdf-header-footer", f"--print-to-pdf={pdf}", report_html.as_uri(),
], check=True, capture_output=True)
print(f"Tests: {summary_line}")
print(f"CRUD coverage: {crud_pct}%  GUI: {gui_pct}%  TC-05 best: {tc05_best} ms")
print(f"Report: {pdf}")
