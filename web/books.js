// Books page: the 100-book list, downloads, reading progress and the reader.
(function () {
  const $ = (id) => document.getElementById(id);
  const BAT = '<svg viewBox="0 0 100 46"><path d="M50 8c-1.6 3.2-3.4 3.6-5.2 1.2L43 4.5 41.2 13C35 8.6 24.8 6.8 12 9.5c8.4 3.4 10.6 9 8.6 16 7-4.2 14.6-2.6 18.8 4 1.4-3.6 3.6-5.6 5.6-6.2 1.6 3.8 3.2 7.6 5 12.2 1.8-4.6 3.4-8.4 5-12.2 2 .6 4.2 2.6 5.6 6.2 4.2-6.6 11.8-8.2 18.8-4-2-7 .2-12.6 8.6-16C75.2 6.8 65 8.6 58.8 13L57 4.5l-1.8 4.7C53.4 11.6 51.6 11.2 50 8z"/></svg>';
  // cover colours per category (dark, Gotham-like)
  const COLORS = {
    "Fraud & money": ["#3a0d0d", "#7a1d1d"], "History": ["#2a1f0d", "#6b4f1d"], "Science": ["#0d1f2a", "#1d4f6b"],
    "Story": ["#1f0d2a", "#4f1d6b"], "Editing": ["#0d2a1f", "#1d6b4f"], "Business": ["#1a1a1a", "#4a4232"], "Mind": ["#0d0f2a", "#262e6b"],
  };
  const PLAN_START = new Date("2026-11-02T00:00:00");
  let data = null, filter = "All", reading = null;

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  async function api(url, body) {
    const r = await fetch(url, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || "Request failed");
    return d;
  }
  function err(m) { $("b-error").textContent = m || ""; $("b-error").classList.toggle("hidden", !m); }

  function renderTop() {
    $("b-done").textContent = data.done;
    $("b-reading").textContent = data.reading;
    $("b-down").textContent = `${data.downloaded}/${data.free}`;
    $("b-ring-fg").style.strokeDashoffset = 327 * (1 - data.done / 100);
    const day = Math.floor((Date.now() - PLAN_START) / 864e5) + 1;
    const left = Math.max(1, 400 - Math.max(0, day));
    const need = (100 - data.done) / left * 7;
    $("b-pace").textContent = data.done >= 100 ? "Done!" : need.toFixed(1) + "/week";
    const j = data.job || {};
    $("b-job").textContent = j.status === "running" ? j.message : (j.message || "") +
      (j.failed && j.failed.length ? " Not found: " + j.failed.join("; ") : "");
    $("b-all").disabled = j.status === "running";
  }

  function renderFilters() {
    const cats = ["All", "Free", "Reading", "Finished", ...Object.keys(COLORS)];
    $("b-filters").innerHTML = cats.map((c) => `<button class="b-filter${c === filter ? " on" : ""}">${esc(c)}</button>`).join("");
    $("b-filters").querySelectorAll("button").forEach((b) => b.onclick = () => { filter = b.textContent; render(); });
  }

  function card(b) {
    const [c1, c2] = COLORS[b.category] || ["#111", "#333"];
    const badge = b.status === "done" ? '<span class="b-badge done">Read</span>'
      : b.kind === "gutenberg" ? '<span class="b-badge">Free</span>'
      : b.kind === "link" ? '<span class="b-badge">Free online</span>' : "";
    const pct = b.pages ? Math.round((b.page + 1) / b.pages * 100) : 0;
    let btns = "";
    if (b.kind === "gutenberg") {
      btns += b.downloaded
        ? `<button data-read="${b.n}">${b.status === "reading" ? "Continue" : "Read"}</button>` +
          (b.has_epub ? `<a href="/api/books/${b.n}/epub">E-book</a>` : "")
        : `<button data-dl="${b.n}">Download</button>`;
    } else if (b.kind === "link") {
      btns += `<a href="${esc(b.links.site)}" target="_blank" rel="noopener">Open free</a>`;
    } else {
      btns += `<a href="${esc(b.links.openlibrary)}" target="_blank" rel="noopener">Borrow</a>` +
              `<a href="${esc(b.links.buy)}" target="_blank" rel="noopener">Find</a>`;
    }
    btns += `<select data-status="${b.n}">${["todo", "reading", "done"].map((s) =>
      `<option value="${s}"${s === b.status ? " selected" : ""}>${{ todo: "To read", reading: "Reading", done: "Finished" }[s]}</option>`).join("")}</select>`;
    return `<div class="b-card">
      <div class="b-cover" style="background:linear-gradient(160deg, ${c2}, ${c1} 70%)">
        ${BAT}${badge}
        <div class="b-num">No. ${String(b.n).padStart(3, "0")} &middot; ${esc(b.category.toUpperCase())}</div>
        <div><div class="b-ctitle">${esc(b.title)}</div><div class="b-cauthor">${esc(b.author)}</div></div>
      </div>
      <div class="b-body">
        ${b.downloaded ? `<div class="b-meta">Page ${b.page + 1} of ${b.pages}</div><div class="b-bar"><i style="width:${pct}%"></i></div>` : ""}
        <div class="b-btns">${btns}</div>
      </div></div>`;
  }

  function render() {
    renderTop();
    renderFilters();
    const list = data.books.filter((b) => filter === "All" ||
      (filter === "Free" && b.kind !== "buy") || (filter === "Reading" && b.status === "reading") ||
      (filter === "Finished" && b.status === "done") || b.category === filter);
    $("b-grid").innerHTML = list.map(card).join("") || '<p class="hint">Nothing here yet.</p>';
    $("b-grid").querySelectorAll("[data-dl]").forEach((b) => b.onclick = async () => {
      b.textContent = "Downloading..."; b.disabled = true;
      try { await api(`/api/books/${b.dataset.dl}/download`, {}); err(""); } catch (e) { err(e.message); }
      load();
    });
    $("b-grid").querySelectorAll("[data-read]").forEach((b) => b.onclick = () => openReader(+b.dataset.read));
    $("b-grid").querySelectorAll("[data-status]").forEach((s) => s.onchange = async () => {
      try { data = await api(`/api/books/${s.dataset.status}/status`, { status: s.value }); render(); } catch (e) { err(e.message); }
    });
  }

  async function load() {
    try { data = await api("/api/books"); render(); } catch (e) { err(e.message); }
    if (data && data.job && data.job.status === "running") setTimeout(load, 2500);
  }

  async function openReader(n, page) {
    try {
      const p = await api(`/api/books/${n}/read` + (page != null ? `?page=${page}` : ""));
      reading = p;
      $("r-title").textContent = p.title;
      $("r-author").textContent = p.author;
      $("r-text").textContent = p.text;
      $("r-text").scrollTop = 0;
      $("r-page").textContent = `Page ${p.page + 1} of ${p.pages} (${Math.round((p.page + 1) / p.pages * 100)}%)`;
      $("r-prev").disabled = p.page <= 0;
      $("r-next").textContent = p.page >= p.pages - 1 ? "Finish book" : "Next →";
      $("b-reader").classList.remove("hidden");
    } catch (e) { err(e.message); }
  }
  $("r-prev").onclick = () => reading && openReader(reading.n, reading.page - 1);
  $("r-next").onclick = async () => {
    if (!reading) return;
    if (reading.page >= reading.pages - 1) {
      await api(`/api/books/${reading.n}/status`, { status: "done" }).catch(() => {});
      $("b-reader").classList.add("hidden");
      load();
    } else openReader(reading.n, reading.page + 1);
  };
  $("r-close").onclick = () => { $("b-reader").classList.add("hidden"); load(); };
  document.addEventListener("keydown", (e) => {
    if ($("b-reader").classList.contains("hidden")) return;
    if (e.key === "ArrowRight") $("r-next").click();
    if (e.key === "ArrowLeft" && !$("r-prev").disabled) $("r-prev").click();
    if (e.key === "Escape") $("r-close").click();
  });
  $("b-all").onclick = async () => {
    try { await api("/api/books/download-all", {}); load(); } catch (e) { err(e.message); }
  };
  load();
})();
