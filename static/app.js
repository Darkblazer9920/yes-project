// Yachay Events System - web client. Talks to the FastAPI backend under /api.
const API = "/api";
const NEXT = {
  Draft: ["Submitted", "Canceled"],
  Submitted: ["Under_Review", "Draft", "Canceled"],
  Under_Review: ["Approved", "Rejected", "Canceled"],
  Approved: ["Canceled"],
  Rejected: ["Draft"],
  Canceled: [],
};
const NEEDS_REVIEWER = ["Under_Review", "Approved", "Rejected"];
const cache = { organizations: [], users: [], venues: [], proposals: [], reservations: [] };

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (iso) => iso ? new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) : "";
const byId = (list, id) => list.find((x) => x.id === id);

async function api(path, options = {}) {
  const res = await fetch(API + path, { headers: { "Content-Type": "application/json" }, ...options });
  if (res.status === 204) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join("; ") : body.detail;
    throw new Error(detail || res.statusText);
  }
  return body;
}

let toastTimer;
function toast(message, kind = "ok") {
  const el = $("#toast");
  el.textContent = message;
  el.className = `toast ${kind === "ok" ? "" : kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), kind === "ok" ? 3000 : 7000);
}

function formData(form) {
  const data = {};
  for (const [k, v] of new FormData(form).entries()) if (v !== "") data[k] = v;
  return data;
}

function rows(tbody, items, render, cols) {
  tbody.innerHTML = items.length ? items.map(render).join("") : `<tr><td colspan="${cols}" class="empty">Nothing here yet</td></tr>`;
}

// ---------- data loading ----------
async function loadAll() {
  const [organizations, users, venues, proposals, reservations] = await Promise.all([
    api("/organizations"), api("/users"), api("/venues"), api("/proposals"), api("/reservations"),
  ]);
  Object.assign(cache, { organizations, users, venues, proposals, reservations });
  fillSelects();
  renderAll();
}

function fillSelects() {
  const sources = {
    organizations: cache.organizations.map((o) => [o.id, o.name]),
    leaders: cache.users.filter((u) => u.role === "Leader").map((u) => [u.id, `${u.full_name} (${u.role})`]),
    reviewers: cache.users.filter((u) => u.role !== "Leader").map((u) => [u.id, `${u.full_name} (${u.role})`]),
    venues: cache.venues.map((v) => [v.id, `${v.name} · ${v.capacity} seats`]),
    approved: cache.proposals.filter((p) => p.status === "Approved" && !cache.reservations.some((r) => r.event_id === p.id))
      .map((p) => [p.id, `#${p.id} ${p.title}`]),
  };
  document.querySelectorAll("select[data-source]").forEach((sel) => {
    const keepBlank = sel.dataset.source === "reviewers";
    const opts = sources[sel.dataset.source].map(([id, label]) => `<option value="${id}">${esc(label)}</option>`).join("");
    sel.innerHTML = (keepBlank ? '<option value="">—</option>' : "") + opts;
  });
}

function renderAll() {
  renderDashboard();
  renderProposals();
  renderReservations();
  renderVenues();
  renderOrganizations();
}

// ---------- dashboard ----------
async function renderDashboard() {
  const count = (s) => cache.proposals.filter((p) => p.status === s).length;
  $("#stats").innerHTML = [
    [cache.organizations.length, "Organizations"], [cache.venues.length, "Venues"],
    [count("Submitted") + count("Under_Review"), "Proposals awaiting review"],
    [count("Approved"), "Approved events"], [cache.reservations.length, "Reservations"],
  ].map(([n, label]) => `<div class="stat"><b>${n}</b><span>${label}</span></div>`).join("");

  const overlaps = await api("/reports/audience-overlaps");
  rows($("#overlaps-table tbody"), overlaps, (o) => `<tr>
    <td><span class="badge Submitted">${esc(o.target_audience)}</span></td>
    <td>${esc(o.event_a_title)}<br><small class="muted">${esc(o.venue_a)}</small></td>
    <td>${esc(o.event_b_title)}<br><small class="muted">${esc(o.venue_b)}</small></td>
    <td>${fmt(o.event_a_start)} – ${fmt(o.event_a_end)}<br>${fmt(o.event_b_start)} – ${fmt(o.event_b_end)}</td></tr>`, 4);

  const now = new Date();
  const upcoming = cache.reservations.filter((r) => new Date(r.end_time) >= now).slice(0, 8);
  rows($("#upcoming-table tbody"), upcoming, (r) => `<tr>
    <td>${esc(byId(cache.proposals, r.event_id)?.title)}</td><td>${esc(byId(cache.venues, r.venue_id)?.name)}</td>
    <td>${fmt(r.start_time)}</td><td>${fmt(r.end_time)}</td></tr>`, 4);
}

// ---------- proposals ----------
function renderProposals() {
  const filter = $("#proposal-filter").value;
  const list = cache.proposals.filter((p) => !filter || p.status === filter);
  rows($("#proposals-table tbody"), list, (p) => `<tr>
    <td>${p.id}</td><td>${esc(p.title)}</td><td>${esc(p.target_audience)}</td>
    <td>${esc(byId(cache.organizations, p.organization_id)?.name)}</td>
    <td><span class="badge ${p.status}">${p.status.replace("_", " ")}</span></td>
    <td>${NEXT[p.status].length ? `<button class="small" data-status="${p.id}">Change…</button>` : ""}
        ${p.status === "Draft" ? `<button class="small danger" data-del-proposal="${p.id}">Delete</button>` : ""}</td></tr>`, 6);
}

$("#proposal-filter").addEventListener("change", renderProposals);

$("#proposal-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = formData(e.target);
  data.organization_id = Number(data.organization_id);
  data.submitter_id = Number(data.submitter_id);
  try {
    const p = await api("/proposals", { method: "POST", body: JSON.stringify(data) });
    toast(`Proposal #${p.id} created as ${p.status}`);
    e.target.reset();
    await loadAll();
  } catch (err) { toast(err.message, "error"); }
});

$("#proposals-table").addEventListener("click", async (e) => {
  const statusId = e.target.dataset.status;
  const delId = e.target.dataset.delProposal;
  if (statusId) openStatusDialog(Number(statusId));
  if (delId && confirm(`Delete draft proposal #${delId}?`)) {
    try { await api(`/proposals/${delId}`, { method: "DELETE" }); toast("Proposal deleted"); await loadAll(); }
    catch (err) { toast(err.message, "error"); }
  }
});

function openStatusDialog(id) {
  const p = byId(cache.proposals, id);
  const form = $("#status-form");
  form.proposal_id.value = id;
  $("#status-title").textContent = `#${p.id} ${p.title} (${p.status.replace("_", " ")})`;
  form.status.innerHTML = NEXT[p.status].map((s) => `<option value="${s}">${s.replace("_", " ")}</option>`).join("");
  form.comments.value = "";
  $("#status-dialog").showModal();
}

$("#status-dialog").addEventListener("close", async () => {
  if ($("#status-dialog").returnValue !== "ok") return;
  const data = formData($("#status-form"));
  const id = data.proposal_id;
  const body = { status: data.status, comments: data.comments ?? null };
  if (data.reviewer_id) body.reviewer_id = Number(data.reviewer_id);
  if (NEEDS_REVIEWER.includes(body.status) && !body.reviewer_id) {
    toast(`Choose a reviewer to set ${body.status.replace("_", " ")}`, "error");
    return;
  }
  try {
    const p = await api(`/proposals/${id}/status`, { method: "POST", body: JSON.stringify(body) });
    toast(`Proposal #${p.id} is now ${p.status.replace("_", " ")}`);
    await loadAll();
  } catch (err) { toast(err.message, "error"); }
});

// ---------- reservations ----------
function renderReservations() {
  rows($("#reservations-table tbody"), cache.reservations, (r) => `<tr>
    <td>${r.id}</td><td>${esc(byId(cache.proposals, r.event_id)?.title)}</td>
    <td>${esc(byId(cache.venues, r.venue_id)?.name)}</td><td>${fmt(r.start_time)}</td><td>${fmt(r.end_time)}</td>
    <td><button class="small danger" data-del-reservation="${r.id}">Delete</button></td></tr>`, 6);
}

$("#reservation-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = formData(e.target);
  const body = { event_id: Number(data.event_id), venue_id: Number(data.venue_id), start_time: data.start_time, end_time: data.end_time };
  try {
    const res = await api("/reservations", { method: "POST", body: JSON.stringify(body) });
    if (res.warnings.length) toast(`Reserved, but: ${res.warnings.map((w) => w.message).join(" | ")}`, "warn");
    else toast(`Reservation #${res.reservation.id} confirmed`);
    e.target.reset();
    await loadAll();
  } catch (err) {
    toast(err.message.includes("VENUE_CONFLICT") ? "That venue is already booked in that time range." : err.message, "error");
  }
});

$("#reservations-table").addEventListener("click", async (e) => {
  const id = e.target.dataset.delReservation;
  if (id && confirm(`Delete reservation #${id}?`)) {
    try { await api(`/reservations/${id}`, { method: "DELETE" }); toast("Reservation deleted"); await loadAll(); }
    catch (err) { toast(err.message, "error"); }
  }
});

// ---------- venues ----------
function renderVenues() {
  rows($("#venues-table tbody"), cache.venues, (v) => `<tr>
    <td>${v.id}</td><td>${esc(v.name)}</td><td>${esc(v.building)}</td><td>${v.capacity}</td>
    <td>${esc(v.built_in_equipment)}</td><td><button class="small danger" data-del-venue="${v.id}">Delete</button></td></tr>`, 6);
}

$("#venue-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = formData(e.target);
  data.capacity = Number(data.capacity);
  try { await api("/venues", { method: "POST", body: JSON.stringify(data) }); toast("Venue added"); e.target.reset(); await loadAll(); }
  catch (err) { toast(err.message, "error"); }
});

$("#venues-table").addEventListener("click", async (e) => {
  const id = e.target.dataset.delVenue;
  if (id && confirm(`Delete venue #${id}?`)) {
    try { await api(`/venues/${id}`, { method: "DELETE" }); toast("Venue deleted"); await loadAll(); }
    catch (err) { toast(err.message, "error"); }
  }
});

// ---------- organizations ----------
function renderOrganizations() {
  rows($("#organizations-table tbody"), cache.organizations, (o) => `<tr>
    <td>${o.id}</td><td>${esc(o.name)}</td><td>${esc(o.category)}</td><td>${fmt(o.created_at)}</td>
    <td><button class="small danger" data-del-org="${o.id}">Delete</button></td></tr>`, 5);
}

$("#organization-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try { await api("/organizations", { method: "POST", body: JSON.stringify(formData(e.target)) }); toast("Organization added"); e.target.reset(); await loadAll(); }
  catch (err) { toast(err.message, "error"); }
});

$("#organizations-table").addEventListener("click", async (e) => {
  const id = e.target.dataset.delOrg;
  if (id && confirm(`Delete organization #${id}?`)) {
    try { await api(`/organizations/${id}`, { method: "DELETE" }); toast("Organization deleted"); await loadAll(); }
    catch (err) { toast(err.message, "error"); }
  }
});

// ---------- tabs ----------
$("#tabs").addEventListener("click", (e) => {
  const tab = e.target.dataset.tab;
  if (!tab) return;
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("hidden", s.id !== `tab-${tab}`));
  history.replaceState(null, "", `#${tab}`);
});

const initial = location.hash.slice(1);
if (initial) document.querySelector(`#tabs button[data-tab="${initial}"]`)?.click();
loadAll().catch((err) => toast(`Cannot reach the API: ${err.message}`, "error"));
