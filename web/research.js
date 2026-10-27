// Research page: runs researcher.py, shows ranked topics per channel, keeps saved ideas.
(function () {
  const $ = (id) => document.getElementById(id);
  let result = null;
  let tab = 0;
  let polling = null;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function fmt(n) {
    if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
    if (n >= 1e3) return Math.round(n / 1e3) + "K";
    return String(n);
  }
  function ago(iso) {
    if (!iso) return "";
    const h = (Date.now() - new Date(iso).getTime()) / 36e5;
    if (h < 1) return "just now";
    if (h < 48) return Math.round(h) + " h ago";
    return Math.round(h / 24) + " days ago";
  }
  async function api(url, body) {
    const opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    const r = await fetch(url, opts);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || "Request failed");
    return data;
  }
  function showError(msg) {
    $("r-error").textContent = msg || "";
    $("r-error").classList.toggle("hidden", !msg);
  }

  function renderTabs() {
    const chans = (result && result.channels) || [];
    $("r-tabs").innerHTML = chans.map((c, i) =>
      `<button class="r-tab${i === tab ? " on" : ""}" data-i="${i}">${esc(c.name)} (${c.topics.length})</button>`).join("");
    $("r-tabs").querySelectorAll(".r-tab").forEach((b) => b.onclick = () => { tab = +b.dataset.i; render(); });
  }

  function ytLine(yt) {
    if (!yt) return "";
    if (yt.error) return `<div class="topic-yt">YouTube check failed (${esc(yt.error)}).</div>`;
    const crowd = yt.videos_30d < 50 ? "few videos - a gap" : yt.videos_30d < 500 ? "some competition" : "crowded";
    const best = yt.best ? ` Best: <a href="${esc(yt.best.url)}" target="_blank" rel="noopener">${esc(yt.best.title)}</a> (${esc(yt.best.channel)}, <b>${fmt(yt.best.views)}</b> views)` : "";
    return `<div class="topic-yt">YouTube, last 30 days: <b>~${fmt(yt.videos_30d)}</b> videos (${crowd}).${best}</div>`;
  }

  function render() {
    renderTabs();
    const ch = result && result.channels && result.channels[tab];
    if (!ch) { $("r-topics").innerHTML = `<p class="hint">Click "Research now".</p>`; $("r-failed").textContent = ""; return; }
    $("r-failed").textContent = ch.failed.length ? "Could not read: " + ch.failed.join(", ") : "";
    if (!ch.topics.length) { $("r-topics").innerHTML = `<p class="hint">No topics found - check the words in "Channels & words".</p>`; return; }
    $("r-topics").innerHTML = ch.topics.map((t, i) => {
      const links = t.items.map((it) =>
        `<li>${it.link ? `<a href="${esc(it.link)}" target="_blank" rel="noopener">${esc(it.title)}</a>` : esc(it.title)} <span class="hint">${esc(it.source)} ${ago(it.time)}</span></li>`).join("");
      return `<div class="topic">
        <div class="topic-head">
          <div><div class="topic-title">${esc(t.title)}</div>
            <div class="topic-meta">${t.count} source${t.count > 1 ? "s" : ""}: ${esc(t.sources.join(", "))}</div></div>
          <div class="topic-score" title="Higher = better topic right now">${Math.round(t.score)}</div>
        </div>
        <div class="topic-angle"><b>Video idea:</b> ${esc(t.angle)}</div>
        ${ytLine(t.youtube)}
        <details><summary>Sources</summary><ul>${links}</ul></details>
        <div class="topic-actions"><button class="btn-ghost" data-save="${i}">Save idea</button></div>
      </div>`;
    }).join("");
    $("r-topics").querySelectorAll("[data-save]").forEach((b) => b.onclick = async () => {
      const t = ch.topics[+b.dataset.save];
      try {
        const d = await api("/api/research/ideas", { channel: ch.name, title: t.title, angle: t.angle, link: (t.items[0] || {}).link || "" });
        renderIdeas(d.ideas);
        b.textContent = "Saved";
        b.disabled = true;
      } catch (e) { showError(e.message); }
    });
  }

  function renderIdeas(ideas) {
    if (!ideas.length) { $("r-ideas").innerHTML = `<p class="hint">No saved ideas yet.</p>`; return; }
    $("r-ideas").innerHTML = ideas.map((x, i) => `<div class="idea${x.done ? " done" : ""}">
      <input type="checkbox" data-done="${i}" ${x.done ? "checked" : ""}>
      <div style="flex:1"><div class="idea-chan">${esc(x.channel)}</div>
        <div class="idea-title">${x.link ? `<a href="${esc(x.link)}" target="_blank" rel="noopener">${esc(x.title)}</a>` : esc(x.title)}</div>
        <div class="hint">${esc(x.angle)}</div></div>
      <button class="btn-ghost" data-del="${i}" title="Delete">&times;</button></div>`).join("");
    $("r-ideas").querySelectorAll("[data-done]").forEach((c) => c.onchange = () =>
      api("/api/research/ideas", { index: +c.dataset.done, done: c.checked }).then((d) => renderIdeas(d.ideas)).catch((e) => showError(e.message)));
    $("r-ideas").querySelectorAll("[data-del]").forEach((b) => b.onclick = () =>
      api("/api/research/ideas", { index: +b.dataset.del, delete: true }).then((d) => renderIdeas(d.ideas)).catch((e) => showError(e.message)));
  }

  async function refresh() {
    const s = await api("/api/research");
    if (s.result) {
      result = s.result;
      $("r-updated").textContent = "Updated " + ago(result.updated) +
        (result.youtube_checked ? "" : " - add YOUTUBE_API_KEY to config.json to see YouTube competition");
    }
    $("r-status").textContent = s.status === "running" ? s.message : "";
    $("r-run").disabled = s.status === "running";
    if (s.status === "error") showError("Research failed: " + s.error);
    render();
    if (s.status === "running" && !polling) polling = setInterval(refresh, 2000);
    if (s.status !== "running" && polling) { clearInterval(polling); polling = null; }
  }

  // ----- channel setup -----
  function chanBox(c) {
    const d = document.createElement("div");
    d.className = "chan";
    d.innerHTML = `<label>Channel name<input data-k="name" value="${esc(c.name || "")}"></label>
      <label>Search words (news)<textarea data-k="searches" rows="2">${esc((c.searches || []).join(", "))}</textarea></label>
      <label>Subreddits<input data-k="subreddits" value="${esc((c.subreddits || []).join(", "))}"></label>
      <label>Strong words<input data-k="strong" value="${esc((c.strong || []).join(", "))}"></label>
      <label><input type="checkbox" data-k="wiki" ${c.wiki ? "checked" : ""} style="width:auto"> Wikipedia (history)</label>
      <label><input type="checkbox" data-k="sq" ${c.lang === "sq" ? "checked" : ""} style="width:auto"> Albanian news</label>
      <button class="btn-ghost" data-remove>Remove channel</button>`;
    d.querySelector("[data-remove]").onclick = () => d.remove();
    return d;
  }
  async function openSetup() {
    const box = $("r-setup");
    box.classList.toggle("hidden");
    if (box.classList.contains("hidden")) return;
    const d = await api("/api/research/channels");
    $("r-setup-list").innerHTML = "";
    d.channels.forEach((c) => $("r-setup-list").appendChild(chanBox(c)));
  }
  async function saveSetup() {
    const channels = [...$("r-setup-list").querySelectorAll(".chan")].map((d) => {
      const v = (k) => d.querySelector(`[data-k="${k}"]`);
      return { name: v("name").value, searches: v("searches").value, subreddits: v("subreddits").value,
               strong: v("strong").value, wiki: v("wiki").checked, lang: v("sq").checked ? "sq" : "en" };
    });
    try {
      await api("/api/research/channels", { channels });
      $("r-setup").classList.add("hidden");
      showError("");
    } catch (e) { showError(e.message); }
  }

  $("r-run").onclick = () => api("/api/research/run", {}).then(refresh).catch((e) => showError(e.message));
  $("r-setup-btn").onclick = () => openSetup().catch((e) => showError(e.message));
  $("r-add").onclick = () => $("r-setup-list").appendChild(chanBox({ name: "", lang: "en" }));
  $("r-save").onclick = saveSetup;
  refresh().catch((e) => showError(e.message));
  api("/api/research/ideas").then((d) => renderIdeas(d.ideas)).catch(() => {});
})();
