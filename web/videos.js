// ---------------------------------------------------------------------
// Clock (same Tirana time convention as the main dashboard)
// ---------------------------------------------------------------------
const TIMEZONE = "Europe/Tirane";

function tickClock() {
  const timeStr = new Intl.DateTimeFormat("en-GB", {
    timeZone: TIMEZONE, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(new Date());
  document.getElementById("header-clock").innerText = timeStr;
}
tickClock();
setInterval(tickClock, 1000);

// ---------------------------------------------------------------------
// State + stage metadata
// ---------------------------------------------------------------------
const STAGE_NAMES = ["script", "media", "transcribe", "cut", "meta"];
const STAGE_LABELS = { script: "Script", media: "Media", transcribe: "Transcribe", cut: "Cut", meta: "Meta" };
let currentSlug = null;

function showError(elId, message) {
  const el = document.getElementById(elId);
  if (!message) {
    el.classList.add("hidden");
    el.innerText = "";
    return;
  }
  el.classList.remove("hidden");
  el.innerText = message;
}

// ---------------------------------------------------------------------
// Project list
// ---------------------------------------------------------------------
async function loadProjects() {
  const resp = await fetch("/api/videos");
  const data = await resp.json();
  const listEl = document.getElementById("project-list");
  listEl.innerHTML = "";

  if (!data.videos || data.videos.length === 0) {
    listEl.innerHTML = '<p class="empty-note">No projects yet - create one above.</p>';
    return;
  }

  for (const p of data.videos) {
    const card = document.createElement("div");
    card.className = "project-card" + (p.slug === currentSlug ? " active" : "");
    const dots = STAGE_NAMES.map((name) => {
      const cls = p.error && p.error.stage === name ? "error" : (p.stages_done.includes(name) ? "done" : "");
      return `<span class="stage-dot ${cls}" title="${STAGE_LABELS[name]}"></span>`;
    }).join("");
    card.innerHTML = `
      <h4>${escapeHtml(p.title || p.slug)}</h4>
      <div class="channel">${escapeHtml(p.channel || "")}</div>
      <div class="dots">${dots}</div>
    `;
    card.addEventListener("click", () => selectProject(p.slug));
    listEl.appendChild(card);
  }
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.innerText = s;
  return div.innerHTML;
}

// ---------------------------------------------------------------------
// Create project
// ---------------------------------------------------------------------
document.getElementById("create-btn").addEventListener("click", async () => {
  showError("create-error", "");
  const slug = document.getElementById("new-slug").value.trim().toLowerCase();
  const channel = document.getElementById("new-channel").value.trim();
  const title = document.getElementById("new-title").value.trim();

  const resp = await fetch("/api/videos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slug, channel, title }),
  });
  const data = await resp.json();
  if (!resp.ok) {
    showError("create-error", data.error || "Failed to create project.");
    return;
  }
  document.getElementById("new-slug").value = "";
  document.getElementById("new-channel").value = "";
  document.getElementById("new-title").value = "";
  await loadProjects();
  selectProject(slug);
});

// ---------------------------------------------------------------------
// Project detail
// ---------------------------------------------------------------------
async function selectProject(slug) {
  currentSlug = slug;
  const resp = await fetch(`/api/videos/${encodeURIComponent(slug)}`);
  if (!resp.ok) return;
  const data = await resp.json();

  document.getElementById("detail").classList.remove("hidden");
  document.getElementById("detail-title").innerText = data.project.title || slug;
  document.getElementById("detail-channel").innerText = data.project.channel || "";
  document.getElementById("script-editor").value = data.script || "";
  document.getElementById("audio-status").innerText = data.audio_uploaded ? "vo.wav uploaded" : "no voiceover yet";
  document.getElementById("run-log").innerText = "";
  document.getElementById("script-save-status").innerText = "";

  renderStageRow(data.project);
  renderResults(data);

  document.querySelectorAll(".project-card").forEach((card) => {
    card.classList.toggle("active", card.querySelector("h4").innerText === (data.project.title || slug));
  });
}

function renderStageRow(project) {
  const stages = project.stages || {};
  const row = document.getElementById("stage-row");
  row.innerHTML = "";
  for (const name of STAGE_NAMES) {
    const done = stages[name] && stages[name].done;
    const errored = project.error && project.error.stage === name;
    const pill = document.createElement("div");
    pill.className = "stage-pill" + (done ? " done" : "") + (errored ? " error" : "");
    pill.innerHTML = `
      <span>${STAGE_LABELS[name]} ${done ? "✓" : errored ? "✗" : ""}</span>
      <button data-stage="${name}" data-force="${done}">${done ? "Rerun" : "Run"}</button>
    `;
    row.appendChild(pill);
  }
  row.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => runStage(btn.dataset.stage, btn.dataset.force === "true"));
  });
}

function renderResults(data) {
  const el = document.getElementById("results");
  const parts = [];

  const shots = (data.project.shots || []);
  if (shots.length) {
    parts.push("<h4>Shots</h4><ul class='shot-list'>" + shots.map(
      (s) => `<li><b>${s.n}</b>${escapeHtml(s.description)}</li>`
    ).join("") + "</ul>");
  }

  if (data.manifest && data.manifest.length) {
    parts.push("<h4>Media Manifest</h4><table><tr><th>Shot</th><th>Provider</th><th>Licence</th><th>Attribution</th></tr>" +
      data.manifest.map((r) => `<tr><td>${escapeHtml(r.shot || "")}</td><td>${escapeHtml(r.provider || "")}</td><td>${escapeHtml(r.licence || "")}</td><td>${escapeHtml(r.attribution || "")}</td></tr>`).join("") +
      "</table>");
  }

  if (data.edit_plan && data.edit_plan.length) {
    parts.push("<h4>Edit Plan</h4><table><tr><th>Shot</th><th>Start</th><th>End</th></tr>" +
      data.edit_plan.map((r) => `<tr><td>${r.shot}</td><td>${r.start}s</td><td>${r.end}s</td></tr>`).join("") +
      "</table>");
  }

  if (data.metadata) {
    const chapters = (data.metadata.chapters || []).join("<br>");
    const credits = (data.metadata.credits || []).join("<br>") || "&mdash;";
    parts.push(`<h4>Metadata</h4><p>${chapters}</p><h4>Credits</h4><p>${credits}</p>`);
  }

  el.innerHTML = parts.join("");
}

// ---------------------------------------------------------------------
// Script save
// ---------------------------------------------------------------------
document.getElementById("save-script-btn").addEventListener("click", async () => {
  if (!currentSlug) return;
  const content = document.getElementById("script-editor").value;
  const resp = await fetch(`/api/videos/${encodeURIComponent(currentSlug)}/script`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  document.getElementById("script-save-status").innerText = resp.ok ? "Saved." : "Failed to save.";
  setTimeout(() => { document.getElementById("script-save-status").innerText = ""; }, 2500);
});

// ---------------------------------------------------------------------
// Voiceover upload
// ---------------------------------------------------------------------
document.getElementById("upload-audio-btn").addEventListener("click", async () => {
  if (!currentSlug) return;
  const fileInput = document.getElementById("audio-file");
  if (!fileInput.files.length) {
    document.getElementById("audio-status").innerText = "Pick a file first.";
    return;
  }
  const form = new FormData();
  form.append("audio", fileInput.files[0]);
  const resp = await fetch(`/api/videos/${encodeURIComponent(currentSlug)}/audio`, { method: "POST", body: form });
  document.getElementById("audio-status").innerText = resp.ok ? "vo.wav uploaded" : "Upload failed.";
});

// ---------------------------------------------------------------------
// Running the pipeline
// ---------------------------------------------------------------------
async function runStage(stage, force) {
  if (!currentSlug) return;
  const logEl = document.getElementById("run-log");
  logEl.innerText = `Running ${stage}...\n`;
  setButtonsDisabled(true);

  try {
    const resp = await fetch(`/api/videos/${encodeURIComponent(currentSlug)}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stage, force }),
    });
    const data = await resp.json();
    logEl.innerText = data.log || (data.ok ? "Done." : "Failed.");
  } catch (exc) {
    logEl.innerText = "Request failed: " + exc;
  } finally {
    setButtonsDisabled(false);
    selectProject(currentSlug);
    loadProjects();
  }
}

document.getElementById("run-all-btn").addEventListener("click", async () => {
  if (!currentSlug) return;
  const logEl = document.getElementById("run-log");
  logEl.innerText = "Running all remaining stages (this can take a while for media search / transcription)...\n";
  setButtonsDisabled(true);

  try {
    const resp = await fetch(`/api/videos/${encodeURIComponent(currentSlug)}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await resp.json();
    logEl.innerText = data.log || (data.ok ? "Done." : "Failed.");
  } catch (exc) {
    logEl.innerText = "Request failed: " + exc;
  } finally {
    setButtonsDisabled(false);
    selectProject(currentSlug);
    loadProjects();
  }
});

function setButtonsDisabled(disabled) {
  document.querySelectorAll("#run-all-btn, .stage-pill button").forEach((b) => { b.disabled = disabled; });
}

loadProjects();
