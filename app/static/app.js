/* Time Tracker UI */

const $ = (id) => document.getElementById(id);

function setMsg(el, text, ok) {
  el.textContent = text || "";
  el.className = "msg" + (text ? (ok ? " ok" : " error") : "");
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  let data = null;
  const text = await res.text();
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
  if (!res.ok) {
    const detail = data && data.detail != null ? data.detail : res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function fmtLocal(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function toDatetimeLocalValue(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function fromDatetimeLocal(value) {
  if (!value) return null;
  // Treat as local wall time → ISO with offset
  const d = new Date(value);
  return d.toISOString();
}

/** Assign stable color class index per duplicate-name groups. */
function nameColorMap(employees) {
  const byName = {};
  for (const e of employees) {
    const key = e.name.trim().toLowerCase();
    (byName[key] ||= []).push(e.id);
  }
  const map = {};
  let colorIdx = 0;
  for (const ids of Object.values(byName)) {
    if (ids.length < 2) continue;
    const c = colorIdx % 5;
    colorIdx += 1;
    for (const id of ids) map[id] = c;
  }
  return map;
}

let employeesCache = [];

async function loadEmployees() {
  employeesCache = await api("/api/employees");
  const colors = nameColorMap(employeesCache);
  const tbody = $("emp-table");
  tbody.innerHTML = "";
  const sel = $("timer-emp");
  const prev = sel.value;
  sel.innerHTML = "";

  for (const e of employeesCache) {
    const tr = document.createElement("tr");
    if (colors[e.id] != null) tr.className = `emp-color-${colors[e.id]}`;
    tr.innerHTML = `
      <td>${escapeHtml(e.name)}</td>
      <td>${escapeHtml(e.title || "—")}</td>
      <td class="actions">
        <button type="button" class="danger" data-del="${e.id}">Удалить</button>
      </td>`;
    tbody.appendChild(tr);

    const opt = document.createElement("option");
    opt.value = e.id;
    opt.textContent = e.title ? `${e.name} — ${e.title}` : e.name;
    sel.appendChild(opt);
  }
  if (prev) sel.value = prev;

  tbody.querySelectorAll("[data-del]").forEach((btn) => {
    btn.addEventListener("click", () => openDeleteModal(Number(btn.dataset.del)));
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function loadActive() {
  const rows = await api("/api/timers/active");
  const tbody = $("active-table");
  tbody.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(r.employee_display_name)} <span class="badge running">идёт</span></td>
      <td>${escapeHtml(r.description)}</td>
      <td>${fmtLocal(r.start)}</td>`;
    tbody.appendChild(tr);
  }
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="3" style="color:var(--muted)">Нет активных таймеров</td></tr>`;
  }
}

$("btn-add-emp").addEventListener("click", async () => {
  const name = $("emp-name").value;
  const title = $("emp-title").value;
  try {
    await api("/api/employees", {
      method: "POST",
      body: JSON.stringify({ name, title: title || null }),
    });
    $("emp-name").value = "";
    $("emp-title").value = "";
    setMsg($("emp-msg"), "Добавлен", true);
    await loadEmployees();
  } catch (err) {
    setMsg($("emp-msg"), err.message, false);
  }
});

$("btn-start").addEventListener("click", async () => {
  const employee_id = Number($("timer-emp").value);
  const description = $("timer-desc").value;
  try {
    await api("/api/timers/start", {
      method: "POST",
      body: JSON.stringify({ employee_id, description }),
    });
    setMsg($("timer-msg"), "Таймер запущен", true);
    $("timer-desc").value = "";
    await loadActive();
  } catch (err) {
    setMsg($("timer-msg"), err.message, false);
  }
});

$("btn-stop").addEventListener("click", async () => {
  const employee_id = Number($("timer-emp").value);
  try {
    const entry = await api("/api/timers/stop", {
      method: "POST",
      body: JSON.stringify({ employee_id }),
    });
    setMsg($("timer-msg"), `Остановлен · ${entry.duration_seconds} сек`, true);
    await loadActive();
  } catch (err) {
    setMsg($("timer-msg"), err.message, false);
  }
});

function defaultPeriod() {
  const now = new Date();
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  $("rep-from").value = toDatetimeLocalValue(start.toISOString()).slice(0, 16);
  $("rep-to").value = toDatetimeLocalValue(now.toISOString()).slice(0, 16);
}

$("btn-report").addEventListener("click", runReport);

async function runReport() {
  const from = fromDatetimeLocal($("rep-from").value);
  const to = fromDatetimeLocal($("rep-to").value);
  if (!from || !to) {
    setMsg($("report-msg"), "Укажите период from–to", false);
    return;
  }
  try {
    const q = new URLSearchParams({ from, to });
    const data = await api(`/api/reports/period?${q}`);
    renderReport(data);
    setMsg($("report-msg"), `Записей: ${data.entries.length}`, true);
  } catch (err) {
    setMsg($("report-msg"), err.message, false);
  }
}

function renderReport(data) {
  const tbody = $("report-table");
  tbody.innerHTML = "";
  for (const e of data.entries) {
    const tr = document.createElement("tr");
    const endCell = e.running
      ? `<span class="badge running">идёт</span>`
      : fmtLocal(e.end);
    const clipped = e.running
      ? "—"
      : `${(e.clipped_hours ?? 0).toFixed(2)} ч`;
    const name = e.employee_deleted
      ? `${escapeHtml(e.employee_name)} <span class="badge deleted">удалён</span>`
      : escapeHtml(e.employee_name);
    const editBtn = e.running
      ? ""
      : `<button type="button" class="secondary" data-edit="${e.id}">Изменить</button>`;
    tr.innerHTML = `
      <td>${name}</td>
      <td>${escapeHtml(e.description)}</td>
      <td>${fmtLocal(e.start)}</td>
      <td>${endCell}</td>
      <td>${clipped}</td>
      <td class="actions">${editBtn}</td>`;
    tbody.appendChild(tr);
  }
  if (!data.entries.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="color:var(--muted)">Нет записей за период</td></tr>`;
  }
  tbody.querySelectorAll("[data-edit]").forEach((btn) => {
    btn.addEventListener("click", () => openEditModal(Number(btn.dataset.edit), data.entries));
  });

  const lines = data.per_employee.map(
    (p) =>
      `${escapeHtml(p.employee_name)}${p.employee_deleted ? " (удалён)" : ""}: <strong>${p.total_hours.toFixed(2)} ч</strong>`
  );
  $("report-totals").innerHTML =
    (lines.length ? lines.join("<br>") + "<br>" : "") +
    `Итого: <strong>${data.total_hours.toFixed(2)} ч</strong>`;
}

function openEditModal(id, entries) {
  const e = entries.find((x) => x.id === id);
  if (!e || e.running) return;
  $("edit-id").value = String(id);
  $("edit-desc").value = e.description;
  $("edit-start").value = toDatetimeLocalValue(e.start);
  $("edit-end").value = toDatetimeLocalValue(e.end);
  setMsg($("edit-msg"), "", true);
  $("edit-modal").classList.add("open");
}

$("btn-edit-cancel").addEventListener("click", () => {
  $("edit-modal").classList.remove("open");
});

$("btn-edit-save").addEventListener("click", async () => {
  const id = Number($("edit-id").value);
  const body = {
    description: $("edit-desc").value,
    start: fromDatetimeLocal($("edit-start").value),
    end: fromDatetimeLocal($("edit-end").value),
  };
  try {
    await api(`/api/entries/${id}`, { method: "PATCH", body: JSON.stringify(body) });
    $("edit-modal").classList.remove("open");
    await runReport();
  } catch (err) {
    setMsg($("edit-msg"), err.message, false);
  }
});

function openDeleteModal(id) {
  const e = employeesCache.find((x) => x.id === id);
  if (!e) return;
  $("del-id").value = String(id);
  $("del-text").textContent =
    `Сотрудник «${e.name}». «Без истории» — мягкое удаление (записи остаются, в отчёте пометка «удалён»). «С историей» — удалить сотрудника и все его записи.`;
  setMsg($("del-msg"), "", true);
  $("del-modal").classList.add("open");
}

$("btn-del-cancel").addEventListener("click", () => {
  $("del-modal").classList.remove("open");
});

async function doDelete(withHistory) {
  const id = Number($("del-id").value);
  try {
    await api(`/api/employees/${id}?with_history=${withHistory}`, { method: "DELETE" });
    $("del-modal").classList.remove("open");
    setMsg($("emp-msg"), "Удалён", true);
    await loadEmployees();
    await loadActive();
  } catch (err) {
    setMsg($("del-msg"), err.message, false);
  }
}

$("btn-del-soft").addEventListener("click", () => doDelete(false));
$("btn-del-hard").addEventListener("click", () => doDelete(true));

(async function init() {
  defaultPeriod();
  try {
    await loadEmployees();
    await loadActive();
  } catch (err) {
    setMsg($("emp-msg"), err.message, false);
  }
})();
