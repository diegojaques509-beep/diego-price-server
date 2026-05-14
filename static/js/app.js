/* ── State ────────────────────────────────────────────────────────────────── */
let deleteTargetId = null;
let chart = null;
let searchTimer = null;

/* ── Init ─────────────────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  loadHoldings();
  loadHistory();
});

/* ── Holdings ─────────────────────────────────────────────────────────────── */
async function loadHoldings() {
  const btn = document.getElementById("refreshBtn");
  btn.disabled = true;
  btn.textContent = "Loading…";

  try {
    const res = await fetch("/api/holdings");
    const data = await res.json();

    document.getElementById("totalValue").textContent =
      data.total_value != null ? fmt(data.total_value) : "–";
    document.getElementById("holdingsCount").textContent = data.holdings.length;
    document.getElementById("updatedTime").textContent = data.updated || "";
    document.getElementById("statusBadge").innerHTML =
      `<span class="badge badge--live">Live</span>`;

    renderTable(data.holdings);
    loadHistory();
  } catch (e) {
    console.error(e);
    document.getElementById("statusBadge").innerHTML =
      `<span class="badge badge--error">Error</span>`;
    toast("Failed to load holdings", "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
      </svg>Refresh`;
  }
}

function renderTable(holdings) {
  const tbody = document.getElementById("holdingsBody");
  if (!holdings.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="table-empty">No holdings yet. Add one above.</td></tr>`;
    return;
  }
  tbody.innerHTML = holdings.map(h => `
    <tr>
      <td><span class="ticker-chip">${esc(h.ticker)}</span></td>
      <td><span class="holding-name">${esc(h.name)}</span></td>
      <td class="text-right">${fmtNum(h.shares)}</td>
      <td class="text-right">${h.price != null ? "$" + fmtNum(h.price, 4) : "–"}</td>
      <td class="text-right">${h.value != null ? fmt(h.value) : "–"}</td>
      <td class="text-right">
        <button class="btn btn-icon" title="Edit" onclick="openEditModal(${h.id}, '${esc(h.ticker)}', '${esc(h.name)}', ${h.shares})">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
          </svg>
        </button>
        <button class="btn btn-icon btn-icon--danger" title="Remove" onclick="openDeleteModal(${h.id}, '${esc(h.ticker)}')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
            <path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/>
          </svg>
        </button>
      </td>
    </tr>
  `).join("");
}

/* ── History chart ────────────────────────────────────────────────────────── */
async function loadHistory() {
  try {
    const res = await fetch("/api/history");
    const data = await res.json();

    const labels = data.map(d => {
      const [y, m, day] = d.date.split("-");
      return `${m}/${day}`;
    });
    const values = data.map(d => d.value);

    const ctx = document.getElementById("historyChart").getContext("2d");

    if (chart) chart.destroy();

    chart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "Portfolio Value",
          data: values,
          borderColor: "#00d26a",
          backgroundColor: "rgba(0,210,106,.08)",
          borderWidth: 2,
          pointRadius: 3,
          pointBackgroundColor: "#00d26a",
          fill: true,
          tension: .35,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => " " + fmt(ctx.parsed.y),
            },
            backgroundColor: "#141420",
            borderColor: "#252538",
            borderWidth: 1,
            titleColor: "#7878a8",
            bodyColor: "#e8e8f8",
            padding: 10,
          }
        },
        scales: {
          x: {
            grid: { color: "#1e1e2e" },
            ticks: { color: "#7878a8", font: { size: 11 } },
          },
          y: {
            grid: { color: "#1e1e2e" },
            ticks: {
              color: "#7878a8",
              font: { size: 11 },
              callback: v => "$" + v.toLocaleString(),
            },
          }
        }
      }
    });
  } catch (e) {
    console.error("Chart error:", e);
  }
}

/* ── Add Modal ────────────────────────────────────────────────────────────── */
function openAddModal() {
  document.getElementById("tickerSearch").value = "";
  document.getElementById("addTicker").value = "";
  document.getElementById("addName").value = "";
  document.getElementById("addShares").value = "";
  document.getElementById("searchResults").innerHTML = "";
  document.getElementById("searchResults").classList.remove("open");
  openModal("addModal");
}

async function submitAdd() {
  const ticker = document.getElementById("addTicker").value.trim().toUpperCase();
  const name   = document.getElementById("addName").value.trim();
  const shares = parseFloat(document.getElementById("addShares").value);

  if (!ticker) { toast("Enter a ticker symbol", "error"); return; }
  if (!shares || shares <= 0) { toast("Enter a valid number of shares", "error"); return; }

  try {
    const res = await fetch("/api/holdings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker, name: name || ticker, shares }),
    });
    if (!res.ok) throw new Error();
    closeModal("addModal");
    toast("Holding added!", "success");
    loadHoldings();
  } catch {
    toast("Failed to add holding", "error");
  }
}

/* ── Edit Modal ───────────────────────────────────────────────────────────── */
function openEditModal(id, ticker, name, shares) {
  document.getElementById("editId").value = id;
  document.getElementById("editTicker").value = ticker;
  document.getElementById("editName").value = name;
  document.getElementById("editShares").value = shares;
  openModal("editModal");
}

async function submitEdit() {
  const id     = document.getElementById("editId").value;
  const name   = document.getElementById("editName").value.trim();
  const shares = parseFloat(document.getElementById("editShares").value);

  if (!shares || shares <= 0) { toast("Enter a valid number of shares", "error"); return; }

  try {
    const res = await fetch(`/api/holdings/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, shares }),
    });
    if (!res.ok) throw new Error();
    closeModal("editModal");
    toast("Holding updated!", "success");
    loadHoldings();
  } catch {
    toast("Failed to update holding", "error");
  }
}

/* ── Delete Modal ─────────────────────────────────────────────────────────── */
function openDeleteModal(id, ticker) {
  deleteTargetId = id;
  document.getElementById("deleteName").textContent = ticker;
  openModal("deleteModal");
}

async function confirmDelete() {
  if (!deleteTargetId) return;
  try {
    const res = await fetch(`/api/holdings/${deleteTargetId}`, { method: "DELETE" });
    if (!res.ok) throw new Error();
    closeModal("deleteModal");
    toast("Holding removed", "success");
    loadHoldings();
  } catch {
    toast("Failed to remove holding", "error");
  } finally {
    deleteTargetId = null;
  }
}

/* ── Ticker Search ────────────────────────────────────────────────────────── */
function onTickerSearch(val) {
  clearTimeout(searchTimer);
  const el = document.getElementById("searchResults");
  if (!val.trim()) { el.innerHTML = ""; el.classList.remove("open"); return; }
  searchTimer = setTimeout(async () => {
    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(val)}`);
      const results = await res.json();
      if (!results.length) { el.innerHTML = ""; el.classList.remove("open"); return; }
      el.innerHTML = results.map(r => `
        <div class="search-result-item" onclick="selectTicker('${esc(r.ticker)}', '${esc(r.name)}')">
          <span class="search-result-ticker">${esc(r.ticker)}</span>
          <span class="search-result-name">${esc(r.name)}</span>
          <span class="search-result-type">${esc(r.type)}</span>
        </div>
      `).join("");
      el.classList.add("open");
    } catch { /* silent */ }
  }, 300);
}

function selectTicker(ticker, name) {
  document.getElementById("addTicker").value = ticker;
  document.getElementById("addName").value = name;
  document.getElementById("tickerSearch").value = `${ticker} – ${name}`;
  const el = document.getElementById("searchResults");
  el.innerHTML = "";
  el.classList.remove("open");
  document.getElementById("addShares").focus();
}

/* ── Modal helpers ────────────────────────────────────────────────────────── */
function openModal(id)  { document.getElementById(id).classList.add("open"); }
function closeModal(id) { document.getElementById(id).classList.remove("open"); }

document.addEventListener("click", e => {
  if (e.target.classList.contains("modal-overlay")) {
    document.querySelectorAll(".modal-overlay.open").forEach(m => m.classList.remove("open"));
  }
  if (!e.target.closest("#addModal")) {
    const el = document.getElementById("searchResults");
    if (el) { el.innerHTML = ""; el.classList.remove("open"); }
  }
});

/* ── Toast ────────────────────────────────────────────────────────────────── */
let toastTimer = null;
function toast(msg, type = "success") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = `toast toast--${type} show`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3000);
}

/* ── Formatters ───────────────────────────────────────────────────────────── */
function fmt(n) {
  return "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtNum(n, decimals = 3) {
  return Number(n).toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: decimals });
}
function esc(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}
