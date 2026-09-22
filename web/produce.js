// ---------------------------------------------------------------------
// Clock
// ---------------------------------------------------------------------
const TIMEZONE = "Europe/Tirane";
function tickClock() {
  document.getElementById("header-clock").innerText = new Intl.DateTimeFormat("en-GB", {
    timeZone: TIMEZONE, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(new Date());
}
tickClock();
setInterval(tickClock, 1000);

function escapeHtml(s) {
  const div = document.createElement("div");
  div.innerText = s == null ? "" : String(s);
  return div.innerHTML;
}

function pollJob(jobId, { onProgress, onDone, onError }) {
  const interval = setInterval(async () => {
    const resp = await fetch(`/api/jobs/${jobId}`);
    if (!resp.ok) {
      clearInterval(interval);
      onError("Lost track of the job.");
      return;
    }
    const job = await resp.json();
    if (job.progress) onProgress(job.progress);
    if (job.status === "done") {
      clearInterval(interval);
      onDone(job.result);
    } else if (job.status === "error") {
      clearInterval(interval);
      onError(job.error || "Job failed.");
    }
  }, 1500);
}

// ---------------------------------------------------------------------
// Engine toggle + voices
// ---------------------------------------------------------------------
document.getElementById("engine-select").addEventListener("change", (e) => {
  const isClaude = e.target.value === "claude";
  document.getElementById("anthropic-key").classList.toggle("hidden", !isClaude);
  document.getElementById("ollama-host").classList.toggle("hidden", isClaude);
});

async function loadVoices() {
  const resp = await fetch("/api/studio/voices");
  const data = await resp.json();
  const select = document.getElementById("voice-select");
  select.innerHTML = data.voices.map((v) => `<option value="${v.id}">${escapeHtml(v.label)}</option>`).join("");
}
loadVoices();

// ---------------------------------------------------------------------
// Produce
// ---------------------------------------------------------------------
document.getElementById("produce-btn").addEventListener("click", async () => {
  const topic = document.getElementById("topic-text").value.trim();
  const channel = document.getElementById("channel-input").value.trim() || "Paper Trail";
  const engine = document.getElementById("engine-select").value;
  const target_words = parseInt(document.getElementById("words-input").value, 10) || 1500;
  const voice = document.getElementById("voice-select").value;
  const ollama_host = document.getElementById("ollama-host").value.trim();
  const anthropic_key = document.getElementById("anthropic-key").value.trim();

  const progressEl = document.getElementById("produce-progress");
  const resultEl = document.getElementById("produce-result");
  const btn = document.getElementById("produce-btn");

  if (!topic) { progressEl.innerText = "Enter a topic first."; return; }

  btn.disabled = true;
  resultEl.innerHTML = "";
  progressEl.innerText = "Starting...";

  const resp = await fetch("/api/auto/produce", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, channel, engine, target_words, voice, ollama_host, anthropic_key }),
  });
  const data = await resp.json();
  if (!resp.ok) {
    progressEl.innerText = data.error || "Failed to start.";
    btn.disabled = false;
    return;
  }

  pollJob(data.job_id, {
    onProgress: (msg) => { progressEl.innerText = msg; },
    onDone: (result) => {
      progressEl.innerText = "Done.";
      resultEl.innerHTML = `<p style="margin-top:10px; color:var(--text-dim);">
        Produced <b style="color:var(--gold);">${escapeHtml(result.slug)}</b> -
        ${result.word_count} words, ${result.shots} shots, ${result.media_kept} media file(s) kept.
      </p>`;
      btn.disabled = false;
      loadVideos();
      selectVideo(result.slug);
    },
    onError: (err) => {
      progressEl.innerText = "Error: " + err;
      btn.disabled = false;
    },
  });
});

// ---------------------------------------------------------------------
// Video list + detail
// ---------------------------------------------------------------------
async function loadVideos() {
  const resp = await fetch("/api/auto/videos");
  const data = await resp.json();
  const listEl = document.getElementById("video-list");
  listEl.innerHTML = "";

  if (!data.videos || data.videos.length === 0) {
    listEl.innerHTML = '<p class="empty-note">No videos produced yet.</p>';
    return;
  }

  for (const v of data.videos) {
    const card = document.createElement("div");
    card.className = "project-card";
    card.innerHTML = `
      <h4>${escapeHtml(v.title)}</h4>
      <div class="channel">${v.slug}</div>
      <div class="dots">
        <span class="stage-dot ${v.has_script ? "done" : ""}" title="Script"></span>
        <span class="stage-dot ${v.has_voiceover ? "done" : ""}" title="Voiceover"></span>
        <span class="stage-dot ${v.has_media ? "done" : ""}" title="Media"></span>
      </div>
    `;
    card.addEventListener("click", () => selectVideo(v.slug));
    listEl.appendChild(card);
  }
}

async function selectVideo(slug) {
  const resp = await fetch(`/api/auto/videos/${encodeURIComponent(slug)}`);
  if (!resp.ok) return;
  const data = await resp.json();

  document.getElementById("detail").classList.remove("hidden");
  document.getElementById("detail-title").innerText = slug;

  const yt = (data.metadata && data.metadata.youtube) || {};
  const ig = (data.metadata && data.metadata.instagram) || {};
  const fb = (data.metadata && data.metadata.facebook) || {};

  const mediaByShot = {};
  for (const row of data.manifest || []) {
    (mediaByShot[row.shot_id] = mediaByShot[row.shot_id] || []).push(row);
  }
  const mediaHtml = Object.entries(mediaByShot).map(([shotId, group]) => `
    <div class="media-shot">
      <h5>${escapeHtml(shotId)}: ${escapeHtml(group[0].shot_description || "")}</h5>
      <div class="media-thumbs">
        ${group.map((r) => `
          <figure>
            ${r.image_url ? `<img src="${r.image_url}" loading="lazy">` : ""}
            <figcaption>${escapeHtml(r.source || "")} &middot; ${parseFloat(r.final_score || 0).toFixed(2)}</figcaption>
          </figure>
        `).join("")}
      </div>
    </div>
  `).join("") || "<p class='hint'>No media found yet.</p>";

  document.getElementById("detail-body").innerHTML = `
    ${data.voiceover_url ? `<h4>Voiceover</h4><audio controls src="${data.voiceover_url}" style="width:100%; margin-bottom:20px;"></audio>` : ""}

    <h4>YouTube</h4>
    <p><b>${escapeHtml(yt.title)}</b></p>
    <p style="white-space:pre-wrap; color:var(--text-dim);">${escapeHtml(yt.description)}</p>
    <p class="hint">Tags: ${escapeHtml((yt.tags || []).join(", "))}</p>

    <h4 style="margin-top:20px;">Instagram</h4>
    <p style="white-space:pre-wrap; color:var(--text-dim);">${escapeHtml(ig.caption)}</p>
    <p class="hint">${escapeHtml((ig.hashtags || []).map((t) => "#" + t).join(" "))}</p>

    <h4 style="margin-top:20px;">Facebook</h4>
    <p style="white-space:pre-wrap; color:var(--text-dim);">${escapeHtml(fb.text)}</p>
    <p class="hint">${escapeHtml((fb.hashtags || []).map((t) => "#" + t).join(" "))}</p>

    <h4 style="margin-top:20px;">Script</h4>
    <textarea rows="10" readonly style="width:100%;">${escapeHtml(data.script)}</textarea>

    <h4 style="margin-top:20px;">Media</h4>
    ${mediaHtml}
  `;
}

loadVideos();
