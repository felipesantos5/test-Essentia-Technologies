// Appointments panel: a read-only view of the clinic agenda by period, doctor and status.
// Data comes from the API through nginx, which adds the API key server-side (see nginx.conf.template).

const API_URL = "/api/v1";
const REQUEST_TIMEOUT_MS = 15_000;
const DEFAULT_DAYS = 7;

const elements = {
  form: document.querySelector("#filters"),
  dateFrom: document.querySelector("#date-from"),
  dateTo: document.querySelector("#date-to"),
  doctor: document.querySelector("#doctor"),
  status: document.querySelector("#status"),
  chips: document.querySelectorAll(".chip"),
  scheduled: document.querySelector("#stat-scheduled"),
  cancelled: document.querySelector("#stat-cancelled"),
  revenue: document.querySelector("#stat-revenue"),
  state: document.querySelector("#state"),
  days: document.querySelector("#days"),
  dayTemplate: document.querySelector("#day-template"),
  rowTemplate: document.querySelector("#row-template"),
};

const currency = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const dayFormat = new Intl.DateTimeFormat("pt-BR", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });
const timeFormat = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" });

// ------------------------------------------------------------------- helpers

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

function localDateFromIso(value) {
  // "2026-09-17" as a local calendar day, not UTC midnight (which would shift the weekday).
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function setState(text) {
  elements.state.textContent = text ?? "";
  elements.state.hidden = !text;
}

async function fetchJson(path, params = {}) {
  const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== ""));
  const url = query.size ? `${API_URL}${path}?${query}` : `${API_URL}${path}`;
  let response;
  try {
    response = await fetch(url, { signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
  } catch (error) {
    throw new Error(error.name === "TimeoutError" ? "a API demorou demais para responder" : "sem conexão com a API");
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.error?.message ?? `HTTP ${response.status}`);
  }
  return payload;
}

// --------------------------------------------------------------------- render

function renderSummary(appointments) {
  const scheduled = appointments.filter((item) => item.status === "scheduled");
  const total = scheduled.reduce((sum, item) => sum + Number(item.price.amount), 0);
  elements.scheduled.textContent = String(scheduled.length);
  elements.cancelled.textContent = String(appointments.length - scheduled.length);
  elements.revenue.textContent = currency.format(total);
}

function renderRow(appointment, now) {
  const row = elements.rowTemplate.content.firstElementChild.cloneNode(true);
  const starts = new Date(appointment.starts_at);
  const ends = new Date(appointment.ends_at);
  row.classList.toggle("is-cancelled", appointment.status === "cancelled");
  row.classList.toggle("is-past", starts < now && appointment.status === "scheduled");
  row.querySelector(".cell-time").textContent = `${timeFormat.format(starts)} – ${timeFormat.format(ends)}`;
  row.querySelector(".patient__name").textContent = appointment.patient.full_name;
  row.querySelector(".patient__contact").textContent = `${appointment.patient.email} · ${appointment.patient.phone}`;
  row.querySelector(".cell-doctor").textContent = appointment.doctor.full_name;
  row.querySelector(".cell-specialty").textContent = appointment.doctor.specialty;
  row.querySelector(".cell-price").textContent = appointment.price.formatted;
  const badge = row.querySelector(".badge");
  badge.textContent = appointment.status === "cancelled" ? "Cancelada" : "Agendada";
  badge.classList.add(`badge--${appointment.status}`);
  if (appointment.cancellation_reason) badge.title = `Motivo: ${appointment.cancellation_reason}`;
  return row;
}

function renderDays(appointments) {
  const now = new Date();
  const byDay = new Map();
  for (const appointment of appointments) {
    const key = appointment.starts_at.slice(0, 10);
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key).push(appointment);
  }
  const sections = [...byDay.entries()].map(([day, items]) => {
    const section = elements.dayTemplate.content.firstElementChild.cloneNode(true);
    section.querySelector(".day__title").textContent = capitalize(dayFormat.format(localDateFromIso(day)));
    section.querySelector("tbody").replaceChildren(...items.map((item) => renderRow(item, now)));
    return section;
  });
  elements.days.replaceChildren(...sections);
}

// ----------------------------------------------------------------------- load

async function loadDoctors() {
  try {
    const doctors = await fetchJson("/doctors");
    const options = doctors.map((doctor) => {
      const option = document.createElement("option");
      option.value = String(doctor.id);
      option.textContent = `${doctor.full_name} · ${doctor.specialty.name}`;
      return option;
    });
    elements.doctor.append(...options);
  } catch {
    // The doctor filter is optional; the listing still works without it.
  }
}

async function loadAppointments() {
  const filters = {
    date_from: elements.dateFrom.value,
    date_to: elements.dateTo.value,
    doctor_id: elements.doctor.value,
    status: elements.status.value,
  };
  elements.form.classList.add("is-loading");
  setState("Carregando consultas…");
  elements.days.replaceChildren();
  try {
    const period = await fetchJson("/appointments", filters);
    renderSummary(period.appointments);
    renderDays(period.appointments);
    setState(period.appointments.length ? null : "Nenhuma consulta no período com esses filtros.");
  } catch (error) {
    renderSummary([]);
    setState(`Não foi possível carregar as consultas (${error.message}).`);
  } finally {
    elements.form.classList.remove("is-loading");
  }
}

function setRange(days) {
  const from = new Date();
  const to = new Date();
  to.setDate(from.getDate() + days - 1);
  elements.dateFrom.value = isoDate(from);
  elements.dateTo.value = isoDate(to);
}

// --------------------------------------------------------------------- wiring

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadAppointments();
});

elements.chips.forEach((chip) => {
  chip.addEventListener("click", () => {
    setRange(Number(chip.dataset.days));
    loadAppointments();
  });
});

setRange(DEFAULT_DAYS);
loadDoctors().then(loadAppointments);
