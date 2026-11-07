/* Time Tracker UI */

const $ = (id) => document.getElementById(id);

function setMsg(el, text, ok) {
  el.textContent = text || "";
  el.className = "msg" + (text ? (ok ? " ok" : " error") : "");
}

async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      ...opts,
    });
  } catch {
    throw new Error("Нет связи с сервером. Проверьте, что приложение запущено.");
  }
  let data = null;
  const text = await res.text();
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
  if (!res.ok) {
    const detail = data && data.detail != null ? data.detail : null;
    throw new Error(typeof detail === "string" && detail ? detail : "Ошибка сервера (" + res.status + "). Попробуйте ещё раз.");
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
const board = { page: 1, perPage: Number(localStorage.getItem("tt.perPage")) || 10, pages: 1, total: 0, editMode: false, clockSkew: 0 };

function fmtDuration(sec) {
  sec = Math.max(0, Math.floor(sec));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

function elapsedSince(iso) {
  return (Date.now() + board.clockSkew - new Date(iso).getTime()) / 1000;
}

async function loadEmployees() {
  const q = new URLSearchParams({ page: board.page, per_page: board.perPage });
  const data = await api(`/api/employees/board?${q}`);
  board.clockSkew = new Date(data.server_time).getTime() - Date.now();
  board.page = data.page;
  board.pages = data.pages;
  board.total = data.total;
  employeesCache = data.items;
  renderBoard();
}

function renderBoard() {
  const colors = nameColorMap(employeesCache);
  const tbody = $("emp-table");
  tbody.innerHTML = "";
  const edit = board.editMode;

  employeesCache.forEach((e, i) => {
    const t = e.active_timer;
    const tr = document.createElement("tr");
    tr.dataset.id = e.id;
    tr.dataset.index = e.index;
    if (colors[e.id] != null) tr.className = `emp-color-${colors[e.id]}`;
    const timeCell = t
      ? `<span class="timer running" data-start="${escapeHtml(t.start)}">${fmtDuration(elapsedSince(t.start))}</span>`
      : `<span class="timer">00:00:00</span>`;
    const isFirst = e.index === 0;
    const isLast = e.index === board.total - 1;
    const actions = edit
      ? `<button type="button" class="secondary icon-btn" data-up="${e.id}" ${isFirst ? "disabled" : ""} title="Выше">↑</button>
         <button type="button" class="secondary icon-btn" data-down="${e.id}" ${isLast ? "disabled" : ""} title="Ниже">↓</button>
         <button type="button" class="danger" data-del="${e.id}">Удалить</button>`
      : t
        ? `<button type="button" class="secondary" data-stop="${e.id}">Стоп</button>`
        : `<button type="button" data-start="${e.id}">Старт</button>`;
    tr.innerHTML = `
      <td class="col-handle">${edit ? '<span class="handle" title="Перетащить">⠿</span>' : ""}</td>
      <td>${escapeHtml(e.name)}<span class="emp-title">${escapeHtml(e.title || "")}</span></td>
      <td class="task" title="${t ? escapeHtml(t.description) : ""}">${t ? escapeHtml(t.description) : "—"}</td>
      <td>${timeCell}</td>
      <td class="actions">${actions}</td>`;
    if (edit) setupDrag(tr);
    tbody.appendChild(tr);
  });

  if (!employeesCache.length) {
    tbody.innerHTML = `<tr><td colspan="5" style="color:var(--muted)">Сотрудников пока нет — добавьте первого</td></tr>`;
  }

  tbody.querySelectorAll("[data-start]").forEach((btn) => {
    if (btn.tagName === "BUTTON") btn.addEventListener("click", () => openStartModal(Number(btn.dataset.start)));
  });
  tbody.querySelectorAll("[data-stop]").forEach((btn) => btn.addEventListener("click", () => stopTimer(Number(btn.dataset.stop))));
  tbody.querySelectorAll("[data-del]").forEach((btn) => btn.addEventListener("click", () => openDeleteModal(Number(btn.dataset.del))));
  tbody.querySelectorAll("[data-up]").forEach((btn) => btn.addEventListener("click", () => moveEmployee(Number(btn.dataset.up), -1)));
  tbody.querySelectorAll("[data-down]").forEach((btn) => btn.addEventListener("click", () => moveEmployee(Number(btn.dataset.down), 1)));

  renderPager();
}

function renderPager() {
  $("per-page").value = String(board.perPage);
  $("pg-prev").disabled = board.page <= 1;
  $("pg-next").disabled = board.page >= board.pages;
  const box = $("pg-pages");
  box.innerHTML = "";
  for (let p = 1; p <= board.pages; p++) {
    // compact: first, last, current ±2
    if (p !== 1 && p !== board.pages && Math.abs(p - board.page) > 2) {
      if (!box.lastChild || box.lastChild.textContent !== "…") {
        const dots = document.createElement("span");
        dots.textContent = "…";
        box.appendChild(dots);
      }
      continue;
    }
    const b = document.createElement("button");
    b.type = "button";
    b.className = "secondary page-btn" + (p === board.page ? " current" : "");
    b.textContent = String(p);
    b.addEventListener("click", () => goPage(p));
    box.appendChild(b);
  }
  const from = board.total ? (board.page - 1) * board.perPage + 1 : 0;
  const to = Math.min(board.total, board.page * board.perPage);
  $("pg-info").textContent = `${from}–${to} из ${board.total}`;
}

async function goPage(p) {
  board.page = p;
  try { await loadEmployees(); } catch (err) { setMsg($("emp-msg"), err.message, false); }
}

$("pg-prev").addEventListener("click", () => goPage(board.page - 1));
$("pg-next").addEventListener("click", () => goPage(board.page + 1));
$("per-page").addEventListener("change", () => {
  board.perPage = Number($("per-page").value);
  localStorage.setItem("tt.perPage", String(board.perPage));
  goPage(1);
});

$("btn-edit-mode").addEventListener("click", () => {
  board.editMode = !board.editMode;
  $("btn-edit-mode").textContent = board.editMode ? "Готово" : "Редактировать";
  $("btn-edit-mode").className = board.editMode ? "" : "secondary";
  $("edit-hint").hidden = !board.editMode;
  setMsg($("emp-msg"), "", true);
  renderBoard();
});

async function moveTo(id, toIndex) {
  try {
    await api(`/api/employees/${id}/move`, { method: "POST", body: JSON.stringify({ to_index: toIndex }) });
    // follow the moved row if it left the current page
    board.page = Math.floor(toIndex / board.perPage) + 1;
    await loadEmployees();
  } catch (err) {
    setMsg($("emp-msg"), err.message, false);
  }
}

function moveEmployee(id, delta) {
  const e = employeesCache.find((x) => x.id === id);
  if (!e) return;
  const to = e.index + delta;
  if (to < 0 || to >= board.total) return;
  moveTo(id, to);
}

let dragId = null;
function setupDrag(tr) {
  tr.draggable = true;
  tr.addEventListener("dragstart", (ev) => {
    dragId = Number(tr.dataset.id);
    tr.classList.add("dragging");
    ev.dataTransfer.effectAllowed = "move";
    ev.dataTransfer.setData("text/plain", tr.dataset.id);
  });
  tr.addEventListener("dragend", () => {
    tr.classList.remove("dragging");
    document.querySelectorAll(".drop-target").forEach((x) => x.classList.remove("drop-target"));
  });
  tr.addEventListener("dragover", (ev) => {
    if (dragId == null) return;
    ev.preventDefault();
    document.querySelectorAll(".drop-target").forEach((x) => x.classList.remove("drop-target"));
    tr.classList.add("drop-target");
  });
  tr.addEventListener("drop", (ev) => {
    ev.preventDefault();
    const id = dragId;
    dragId = null;
    const target = Number(tr.dataset.index);
    if (id == null || id === Number(tr.dataset.id)) return;
    moveTo(id, target);
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// live ticking of running timers
setInterval(() => {
  document.querySelectorAll(".timer.running[data-start]").forEach((el) => {
    el.textContent = fmtDuration(elapsedSince(el.dataset.start));
  });
}, 1000);

$("emp-name").addEventListener("input", () => {
  $("btn-add-emp").disabled = !$("emp-name").value.trim();
});

$("btn-add-emp").addEventListener("click", async () => {
  const name = $("emp-name").value.trim();
  const title = $("emp-title").value.trim();
  if (!name) {
    setMsg($("emp-msg"), "Укажите имя сотрудника", false);
    return;
  }
  try {
    await api("/api/employees", {
      method: "POST",
      body: JSON.stringify({ name, title: title || null }),
    });
    $("emp-name").value = "";
    $("emp-title").value = "";
    $("btn-add-emp").disabled = true;
    setMsg($("emp-msg"), "Сотрудник добавлен", true);
    // jump to the last page where the new employee is
    board.page = Math.max(1, Math.ceil((board.total + 1) / board.perPage));
    await loadEmployees();
  } catch (err) {
    setMsg($("emp-msg"), err.message, false);
  }
});

function openStartModal(id) {
  const e = employeesCache.find((x) => x.id === id);
  if (!e) return;
  $("start-id").value = String(id);
  $("start-who").textContent = e.title ? `${e.name} — ${e.title}` : e.name;
  $("start-desc").value = "";
  $("btn-start-go").disabled = true;
  setMsg($("start-msg"), "", true);
  $("start-modal").classList.add("open");
  setTimeout(() => $("start-desc").focus(), 0);
}

$("start-desc").addEventListener("input", () => {
  $("btn-start-go").disabled = !$("start-desc").value.trim();
});
$("start-desc").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey) && !$("btn-start-go").disabled) $("btn-start-go").click();
});
$("btn-start-cancel").addEventListener("click", () => $("start-modal").classList.remove("open"));

$("btn-start-go").addEventListener("click", async () => {
  const employee_id = Number($("start-id").value);
  const description = $("start-desc").value.trim();
  if (!description) {
    $("btn-start-go").disabled = true;
    return;
  }
  $("btn-start-go").disabled = true;
  try {
    await api("/api/timers/start", {
      method: "POST",
      body: JSON.stringify({ employee_id, description }),
    });
    $("start-modal").classList.remove("open");
    setMsg($("emp-msg"), "Таймер запущен", true);
    await loadEmployees();
  } catch (err) {
    setMsg($("start-msg"), err.message, false);
    $("btn-start-go").disabled = !$("start-desc").value.trim();
  }
});

async function stopTimer(employee_id) {
  try {
    const entry = await api("/api/timers/stop", {
      method: "POST",
      body: JSON.stringify({ employee_id }),
    });
    setMsg($("emp-msg"), `Таймер остановлен · ${fmtDuration(entry.duration_seconds)}`, true);
    await loadEmployees();
  } catch (err) {
    setMsg($("emp-msg"), err.message, false);
  }
}

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
    setMsg($("report-msg"), "Укажите период: дату «С» и «По»", false);
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
  const running = e.active_timer ? " У сотрудника идёт таймер — он будет остановлен." : "";
  $("del-text").textContent =
    `Сотрудник «${e.name}».${running} «Без истории» — мягкое удаление (записи остаются, в отчёте пометка «удалён»). «С историей» — удалить сотрудника и все его записи.`;
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
    setMsg($("emp-msg"), "Сотрудник удалён", true);
    await loadEmployees();
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
  } catch (err) {
    setMsg($("emp-msg"), err.message, false);
  }
})();
