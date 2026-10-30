// Autopilot page: on/off, nightly time, channels, YouTube connect, log.
(function () {
  const $ = (id) => document.getElementById(id);
  const VOICES = [["en-GB-RyanNeural", "Ryan (British)"], ["en-GB-ThomasNeural", "Thomas (British)"]];
  let st = null, poll = null, dirty = false;

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  async function api(url, body) {
    const r = await fetch(url, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || "Request failed");
    return d;
  }
  const err = (m) => { $("ap-error").textContent = m || ""; $("ap-error").classList.toggle("hidden", !m); };
  const when = (iso) => iso ? new Date(iso).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "never";

  function chanRow(c, i) {
    const opt = (v, l, cur) => `<option value="${v}"${String(v) === String(cur) ? " selected" : ""}>${l}</option>`;
    return `<div class="ap-chan" data-i="${i}">
      <div class="ap-switch${c.enabled ? " on" : ""}" data-k="enabled"><i></i></div>
      <div>
        <div class="ap-name"><input data-k="name" value="${esc(c.name)}" style="background:transparent;border:none;color:inherit;font:inherit;width:100%"></div>
        <div class="ap-meta">Last video: ${when(c.last_made)} &middot; ${c.used || 0} topics used
          &middot; <span class="ap-pill ${c.connected ? "ok" : "no"}">${c.connected ? "YouTube connected" : "YouTube not connected"}</span></div>
        <div class="ap-row">
          <select data-k="per_week">${[1, 2, 3, 4, 5, 6, 7].map((n) => opt(n, n + " video" + (n > 1 ? "s" : "") + " / week", c.per_week)).join("")}</select>
          <select data-k="length">${opt("long", "Long video (16:9)", c.length)}${opt("short", "Short (9:16)", c.length)}</select>
          <select data-k="voice">${VOICES.map(([v, l]) => opt(v, l, c.voice)).join("")}</select>
          <select data-k="publish">${opt("review", "I review it first (safest)", c.publish)}${opt("schedule", "Goes public by itself", c.publish)}${opt("private", "Uploads as private", c.publish)}</select>
          <select data-k="publish_hour">${Array.from({ length: 24 }, (_, h) => opt(h, "at " + String(h).padStart(2, "0") + ":00", c.publish_hour)).join("")}</select>
        </div>
      </div>
      <div class="ap-btns">
        <button class="btn-ghost" data-connect>${c.connected ? "Reconnect" : "Connect YouTube"}</button>
        <button class="btn-ghost" data-make>Make one now</button>
        <button class="btn-ghost" data-remove title="Remove">Remove</button>
      </div></div>`;
  }

  function readChans() {
    return [...document.querySelectorAll(".ap-chan")].map((row) => {
      const v = (k) => row.querySelector(`[data-k="${k}"]`);
      return { name: v("name").value, enabled: v("enabled").classList.contains("on"), per_week: +v("per_week").value,
               length: v("length").value, voice: v("voice").value, publish: v("publish").value, publish_hour: +v("publish_hour").value };
    });
  }

  function render() {
    const s = st.settings;
    $("ap-switch").classList.toggle("on", s.enabled);
    $("ap-state").innerHTML = s.enabled
      ? `On<small>Next run tonight at ${esc(s.run_time)}${st.last_run_day ? " &middot; last run " + esc(st.last_run_day) : ""}</small>`
      : "Off<small>Nothing runs until you switch it on.</small>";
    if (document.activeElement !== $("ap-time")) $("ap-time").value = s.run_time;
    if (!dirty) {
      $("ap-chans").innerHTML = s.channels.map(chanRow).join("") || '<p class="hint">No channels - add one.</p>';
      $("ap-engine").value = s.engine; $("ap-model").value = s.model || ""; $("ap-host").value = s.ollama_host || "";
      $("ap-key").placeholder = s.has_anthropic_key ? "Anthropic key saved (type to change)" : "Anthropic API key";
      wireChans();
    }
    renderProgress();
    const sel = $("mk-chan");
    if (document.activeElement !== sel) {
      const cur = sel.value;
      sel.innerHTML = s.channels.map((c) => `<option>${esc(c.name)}</option>`).join("");
      if (cur) sel.value = cur;
    }
    $("ap-run").disabled = st.running;
    $("ap-secret").textContent = st.client_secret ? "client_secret.json found - step 1 is done." : "client_secret.json not found yet - do step 1 before connecting channels.";
    $("ap-log").innerHTML = st.log.length ? st.log.map((l) => `<div><time>${when(l.time)}</time>
      <span><b>${esc(l.channel)}</b> &middot; <span class="${l.ok ? "" : "bad"}">${esc(l.msg)}</span>
      ${l.url ? ` &middot; <a href="${esc(l.url)}" target="_blank" rel="noopener">open</a>` : ""}</span></div>`).join("")
      : '<p class="hint">Nothing yet.</p>';
    if (st.running && !poll) poll = setInterval(load, 2500);
    if (!st.running && poll) { clearInterval(poll); poll = null; }
  }

  function wireChans() {
    document.querySelectorAll(".ap-chan").forEach((row) => {
      const name = () => row.querySelector('[data-k="name"]').value;
      row.querySelector('[data-k="enabled"]').onclick = (e) => { e.currentTarget.classList.toggle("on"); dirty = true; };
      row.querySelectorAll("select,input").forEach((el) => el.onchange = () => { dirty = true; });
      row.querySelector("[data-remove]").onclick = () => { row.remove(); dirty = true; };
      row.querySelector("[data-make]").onclick = async () => {
        try { await saveAll(); await api("/api/autopilot/run", { channel: name() }); load(); } catch (e) { err(e.message); }
      };
      row.querySelector("[data-connect]").onclick = async (e) => {
        const b = e.currentTarget; b.textContent = "Finish in the browser..."; b.disabled = true;
        try { await saveAll(); st = await api("/api/autopilot/connect", { channel: name() }); err(""); render(); }
        catch (ex) { err(ex.message); b.textContent = "Connect YouTube"; b.disabled = false; }
      };
    });
  }

  async function saveAll(extra) {
    const body = Object.assign({ channels: readChans(), run_time: $("ap-time").value, engine: $("ap-engine").value,
      model: $("ap-model").value, ollama_host: $("ap-host").value }, extra || {});
    if ($("ap-key").value) body.anthropic_key = $("ap-key").value;
    st = await api("/api/autopilot/settings", body);
    dirty = false; err(""); render();
  }

  function renderProgress() {
    const j = st.job || {};
    $("pg").classList.toggle("hidden", !st.running);
    $("mk-go").disabled = st.running;
    if (!st.running) return;
    const total = j.steps.length, step = Math.min(j.step || 0, total - 1);
    const pct = Math.round((step + 0.5) / total * 100);
    $("pg-title").textContent = j.channel ? `${j.channel} - ${j.length === "short" ? "Short" : "Long video"}` : "Starting...";
    const mins = j.started ? Math.max(0, Math.round((Date.now() - new Date(j.started)) / 60000)) : 0;
    $("pg-sub").textContent = (j.topic ? j.topic + " · " : "") + `${mins} min so far`;
    $("pg-pct").textContent = pct + "%";
    $("pg-bar").style.width = pct + "%";
    $("pg-steps").innerHTML = j.steps.map((label, i) =>
      `<li class="${i < step ? "done" : i === step ? "now" : ""}"><i>${i < step ? "✓" : ""}</i>${esc(label)}</li>`).join("");
    $("pg-msg").textContent = j.message || "";
  }

  let vids = [], vfilter = "all";
  const VLABEL = { review: "Waiting for review", uploaded: "On YouTube", skipped: "Skipped", failed: "Failed", made: "Made" };
  async function loadVideos() {
    try { vids = (await api("/api/autopilot/videos")).videos; renderVideos(); } catch (e) { err(e.message); }
  }
  function renderVideos() {
    const tabs = [["all", "All"], ["review", "To review"], ["uploaded", "On YouTube"], ["short", "Shorts"], ["long", "Long"]];
    $("vg-filters").innerHTML = tabs.map(([k, l]) => `<button data-f="${k}" class="${k === vfilter ? "on" : ""}">${l}</button>`).join("");
    $("vg-filters").querySelectorAll("button").forEach((b) => b.onclick = () => { vfilter = b.dataset.f; renderVideos(); });
    const list = vids.filter((v) => vfilter === "all" || (vfilter === "short" ? v.short : vfilter === "long" ? !v.short : v.state === vfilter));
    $("vg-grid").innerHTML = list.length ? list.map((v) => `<div class="vg-card" data-slug="${esc(v.slug)}">
        <div class="vg-pic" style="${v.thumb ? `background-image:url('/api/autopilot/review/${esc(v.slug)}/thumb/1')` : ""}">
          ${v.has_video ? '<div class="play"></div>' : ""}
          <span class="vg-tag ${v.state}">${VLABEL[v.state] || v.state}</span>
          <span class="vg-len">${v.short ? "Short" : "Long"}</span>
        </div>
        <div class="vg-info"><b>${esc(v.title)}</b><span>${esc(v.channel || "")}${v.channel ? " · " : ""}${when(v.made)}</span></div>
      </div>`).join("") : '<p class="hint">No videos here yet.</p>';
    $("vg-grid").querySelectorAll(".vg-card").forEach((c) => c.onclick = () => openVideo(vids.find((v) => v.slug === c.dataset.slug)));
  }
  function openVideo(v) {
    if (!v || !v.has_video) return;
    $("vg-title").textContent = v.title;
    $("vg-player").src = `/api/autopilot/videos/${encodeURIComponent(v.slug)}/file`;
    $("vg-dl").href = `/api/autopilot/videos/${encodeURIComponent(v.slug)}/file?download=1`;
    $("vg-yt").classList.toggle("hidden", !v.url);
    if (v.url) $("vg-yt").href = v.url;
    $("vg-modal").classList.remove("hidden");
    $("vg-player").play().catch(() => {});
  }
  $("vg-close").onclick = () => { $("vg-player").pause(); $("vg-player").removeAttribute("src"); $("vg-modal").classList.add("hidden"); };

  async function loadReview() {
    try {
      const d = await api("/api/autopilot/review");
      $("ap-review").innerHTML = d.review.length ? d.review.map((r) => `<div class="rv" data-slug="${esc(r.slug)}">
        <video controls preload="metadata" src="/api/autopilot/review/${esc(r.slug)}/video"></video>
        <div>
          <div class="ap-meta">${esc(r.channel)} &middot; made ${when(r.made)}</div>
          <input type="text" value="${esc(r.title)}" maxlength="100">
          ${r.thumbs && r.thumbs.length ? `<div class="hint" style="margin-top:10px">Pick the thumbnail:</div><div class="rv-thumbs">${r.thumbs.map((n, k) =>
            `<img data-thumb="${n}" class="${k === 0 ? "on" : ""}" src="/api/autopilot/review/${esc(r.slug)}/thumb/${n}?t=${Date.now()}" alt="Thumbnail ${n}">`).join("")}</div>` : ""}
          ${r.hooks.length ? `<div class="rv-hooks">Opening hooks the AI tried (gold = used):<ol>${r.hooks.map((h) =>
            `<li class="${h.text === r.chosen_hook ? "on" : ""}">${esc(h.text)} <span class="hint">(${h.score})</span></li>`).join("")}</ol></div>` : ""}
          <div class="rv-checks">
            <label><input type="checkbox"> I watched it all, it's good</label>
            <label><input type="checkbox"> The facts and numbers are right</label>
            <label><input type="checkbox"> The title and thumbnail are mine / checked</label>
          </div>
          <div class="ap-row"><button class="btn-primary" data-ok disabled>Approve &amp; schedule</button><button class="btn-ghost" data-no>Skip it</button></div>
        </div></div>`).join("") : '<p class="hint">Nothing waiting.</p>';
      document.querySelectorAll(".rv").forEach((row) => {
        const slug = row.dataset.slug, ok = row.querySelector("[data-ok]");
        const boxes = [...row.querySelectorAll(".rv-checks input")];
        row.querySelectorAll("[data-thumb]").forEach((img) => img.onclick = () => {
          row.querySelectorAll("[data-thumb]").forEach((x) => x.classList.remove("on")); img.classList.add("on");
        });
        boxes.forEach((b) => b.onchange = () => { ok.disabled = !boxes.every((x) => x.checked); });
        ok.onclick = async () => {
          ok.disabled = true; ok.textContent = "Uploading...";
          try { await api(`/api/autopilot/review/${slug}`, { title: row.querySelector("input[type=text]").value,
            thumb: +((row.querySelector("[data-thumb].on") || {}).dataset || {}).thumb || 1 }); load(); loadReview(); loadVideos(); }
          catch (e) { err(e.message); ok.textContent = "Approve & schedule"; ok.disabled = false; }
        };
        row.querySelector("[data-no]").onclick = async () => {
          if (!confirm("Skip this video? It won't be uploaded.")) return;
          try { await api(`/api/autopilot/review/${slug}`, { action: "reject" }); load(); loadReview(); loadVideos(); } catch (e) { err(e.message); }
        };
      });
    } catch (e) { err(e.message); }
  }

  async function load() {
    const wasRunning = st && st.running;
    try { st = await api("/api/autopilot"); render(); } catch (e) { err(e.message); }
    if (wasRunning && st && !st.running) { loadReview(); loadVideos(); }
  }

  $("ap-switch").onclick = () => saveAll({ enabled: !st.settings.enabled }).catch((e) => err(e.message));
  $("ap-time").onchange = () => saveAll().catch((e) => err(e.message));
  $("ap-save").onclick = () => saveAll().catch((e) => err(e.message));
  $("ap-run").onclick = async () => { try { await saveAll(); await api("/api/autopilot/run", {}); load(); } catch (e) { err(e.message); } };
  $("ap-add").onclick = () => {
    $("ap-chans").insertAdjacentHTML("beforeend", chanRow({ name: "New channel", enabled: false, per_week: 1, length: "long",
      voice: "en-GB-RyanNeural", publish: "review", publish_hour: 17 }, document.querySelectorAll(".ap-chan").length));
    dirty = true; wireChans();
  };
  ["ap-engine", "ap-model", "ap-host", "ap-key"].forEach((id) => $(id).onchange = () => saveAll().catch((e) => err(e.message)));
  document.querySelectorAll("#mk-len button").forEach((b) => b.onclick = () => {
    document.querySelectorAll("#mk-len button").forEach((x) => x.classList.remove("on")); b.classList.add("on");
  });
  $("mk-go").onclick = async () => {
    const length = document.querySelector("#mk-len button.on").dataset.len;
    try {
      await api("/api/autopilot/run", { channel: $("mk-chan").value, length, brief: $("mk-brief").value });
      $("mk-brief").value = "";
      load();
      $("pg").scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (e) { err(e.message); }
  };
  load();
  loadReview();
  loadVideos();
  setInterval(() => { if (!poll) load(); }, 15000);  // notices runs started on another device or at night
})();
