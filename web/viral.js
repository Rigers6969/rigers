(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  async function api(url, body) {
    const r = await fetch(url, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || "Request failed");
    return d;
  }
  const err = (m) => { $("v-error").textContent = m || ""; $("v-error").classList.toggle("hidden", !m); };
  const num = (n) => n == null ? "?" : n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? (n / 1e3).toFixed(1) + "K" : String(n);
  let history = [], current = null, timer = null, lastKind = null;

  function show(a) {
    current = a;
    const s = a.stats, f = a.formula, m = a.meta || {};
    const tile = (v, l) => `<div class="v-stat"><b>${esc(v)}</b><span>${esc(l)}</span></div>`;
    $("v-result").innerHTML = `
      <h3>${esc(m.title || a.url)}</h3>
      <p class="hint">${esc(m.channel || "")}${m.view_count ? " · " + num(m.view_count) + " views" : ""} · <a href="${esc(a.url)}" target="_blank" rel="noopener">open</a></p>
      <div class="v-stats">
        ${tile(s.duration + "s", s.short ? "long (Short)" : "long")}
        ${tile(s.words_per_sec, "words per second")}
        ${tile(s.sec_per_cut + "s", "per shot")}
        ${tile(s.first_word_at == null ? "-" : s.first_word_at + "s", "until the first word")}
        ${tile(s.loop_guess ? "yes" : "no", "loops back to start")}
      </div>
      <span class="v-tag">${esc(f.hook_type || "hook")}</span><span class="v-tag">ending: ${esc(f.ending_type || "?")}</span>
      <div class="v-hook">"${esc(s.hook_3s || s.first_sentence || "(no words in the first 3 seconds)")}"</div>
      <p>${esc(f.hook_why || "")}</p>
      <h3 style="margin-top:18px">Why it went viral</h3><p>${esc(f.why_viral || "")}</p>
      <h3 style="margin-top:18px">The structure</h3><ol class="v-list">${(f.structure || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ol>
      <h3 style="margin-top:18px">Tricks that keep people watching</h3><ul class="v-list">${(f.retention_tricks || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      <p class="hint" style="margin-top:12px">Title template: <b>${esc(f.title_pattern || "-")}</b> · Works best for: ${esc(f.best_for || "-")}</p>
      <details style="margin-top:12px"><summary class="hint">Every word, with time</summary><div class="v-trans">${(a.transcript || []).map((t) => `<div><b>${t.start.toFixed(1)}s</b> ${esc(t.text)}</div>`).join("")}</div></details>
      <h3 style="margin-top:22px">2. Make my version</h3>
      <p class="hint">Same formula, your topic, new words. It writes the script, gets free photos, records the voice and builds the Short. It shows up in Autopilot → My videos (Play / Download / Post).</p>
      <div class="v-row">
        <select id="v-chan"><option>Paper Trail</option><option>History</option><option>The Forgotten Lab</option></select>
        <input id="v-topic" placeholder="Your topic, e.g. The Enron scandal">
        <button id="v-make" class="btn-primary">Make my version</button>
      </div>`;
    $("v-result").classList.remove("hidden");
    $("v-make").onclick = async () => {
      err(""); $("v-done").innerHTML = "";
      try { await api(`/api/viral/${encodeURIComponent(a.id)}/make`, { topic: $("v-topic").value, channel: $("v-chan").value }); poll(); }
      catch (e) { err(e.message); }
    };
  }

  function renderHistory() {
    $("v-history").innerHTML = history.length ? history.map((h, i) => `<div class="v-hist" data-i="${i}"><span>${esc((h.meta || {}).title || h.url)}</span><span class="hint">${esc(h.stats.duration)}s</span></div>`).join("")
      : '<p class="hint">Nothing yet.</p>';
    document.querySelectorAll(".v-hist").forEach((el) => el.onclick = () => { show(history[+el.dataset.i]); window.scrollTo({ top: 0, behavior: "smooth" }); });
  }

  async function poll() {
    clearTimeout(timer);
    try {
      const d = await api("/api/viral");
      history = d.history; renderHistory();
      const st = d.status;
      $("v-job").classList.toggle("hidden", !st.running);
      $("v-msg").textContent = st.message || "";
      $("v-go").disabled = st.running;
      if (st.error) err(st.error);
      if (st.running) { lastKind = st.kind; timer = setTimeout(poll, 2000); return; }
      if (lastKind && st.result) {
        if (lastKind === "analyze") show(st.result);
        else $("v-msg").textContent = "";
        if (lastKind === "version") {
          $("v-done").innerHTML = `<p>✅ Done: <b>${esc(st.result.title)}</b>. Open <a href="/autopilot.html">Autopilot → My videos</a> to watch it and post it.</p>`;
        }
      }
      lastKind = null;
      if (!current && history.length) show(history[0]);
    } catch (e) { err(e.message); }
  }

  $("v-go").onclick = async () => {
    err(""); $("v-done").innerHTML = "";
    try { await api("/api/viral/analyze", { url: $("v-url").value }); lastKind = "analyze"; poll(); }
    catch (e) { err(e.message); }
  };
  poll();
})();
