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
  div.innerText = s;
  return div.innerHTML;
}

// ---------------------------------------------------------------------
// Generic job polling - POST returns {job_id}; poll GET /api/studio/jobs/<id>
// every 1.5s until status is "done" or "error".
// ---------------------------------------------------------------------
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
// Script source toggle
// ---------------------------------------------------------------------
document.querySelectorAll('input[name="script-source"]').forEach((radio) => {
  radio.addEventListener("change", () => {
    document.getElementById("ai-controls").classList.toggle(
      "hidden", document.querySelector('input[name="script-source"]:checked').value !== "ai"
    );
  });
});

document.getElementById("script-engine").addEventListener("change", (e) => {
  const isClaude = e.target.value === "claude";
  document.getElementById("anthropic-key").classList.toggle("hidden", !isClaude);
  document.getElementById("ollama-host").classList.toggle("hidden", isClaude);
});

// ---------------------------------------------------------------------
// Voices
// ---------------------------------------------------------------------
async function loadVoices() {
  const resp = await fetch("/api/studio/voices");
  const data = await resp.json();
  const select = document.getElementById("voice-select");
  select.innerHTML = data.voices.map((v) => `<option value="${v.id}">${escapeHtml(v.label)}</option>`).join("");
}
loadVoices();

// ---------------------------------------------------------------------
// Script generation
// ---------------------------------------------------------------------
document.getElementById("generate-script-btn").addEventListener("click", async () => {
  const topic = document.getElementById("script-topic").value.trim();
  const engine = document.getElementById("script-engine").value;
  const target_words = parseInt(document.getElementById("script-words").value, 10) || 2000;
  const ollama_host = document.getElementById("ollama-host").value.trim();
  const anthropic_key = document.getElementById("anthropic-key").value.trim();
  const progressEl = document.getElementById("script-progress");
  const btn = document.getElementById("generate-script-btn");

  if (!topic) { progressEl.innerText = "Enter a topic first."; return; }

  btn.disabled = true;
  progressEl.innerText = "Starting...";

  const resp = await fetch("/api/studio/script", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, engine, target_words, ollama_host, anthropic_key }),
  });
  const data = await resp.json();
  if (!resp.ok) {
    progressEl.innerText = data.error || "Failed to start.";
    btn.disabled = false;
    return;
  }

  pollJob(data.job_id, {
    onProgress: (msg) => { progressEl.innerText = msg; },
    onDone: (script) => {
      progressEl.innerText = "Done.";
      document.getElementById("script-text").value = script;
      btn.disabled = false;
    },
    onError: (err) => {
      progressEl.innerText = "Error: " + err;
      btn.disabled = false;
    },
  });
});

// ---------------------------------------------------------------------
// Voiceover synthesis
// ---------------------------------------------------------------------
document.getElementById("generate-voiceover-btn").addEventListener("click", async () => {
  const script = document.getElementById("script-text").value.trim();
  const voice = document.getElementById("voice-select").value;
  const progressEl = document.getElementById("voiceover-progress");
  const resultEl = document.getElementById("voiceover-result");
  const btn = document.getElementById("generate-voiceover-btn");

  if (!script) { progressEl.innerText = "Write or generate a script first."; return; }

  btn.disabled = true;
  resultEl.innerHTML = "";
  progressEl.innerText = "Starting...";

  const resp = await fetch("/api/studio/voiceover", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ script, voice }),
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
      const url = `/api/studio/voiceover/file/${encodeURIComponent(result.filename)}`;
      resultEl.innerHTML = `<audio controls src="${url}" style="width:100%; margin-top:10px;"></audio>
        <a href="${url}" download class="btn-ghost" style="display:inline-block; margin-top:10px;">Download MP3</a>`;
      btn.disabled = false;
    },
    onError: (err) => {
      progressEl.innerText = "Error: " + err;
      btn.disabled = false;
    },
  });
});

// ---------------------------------------------------------------------
// Media finder
// ---------------------------------------------------------------------
document.getElementById("find-media-btn").addEventListener("click", async () => {
  const shots = document.getElementById("shots-text").value.trim();
  const progressEl = document.getElementById("media-progress");
  const resultEl = document.getElementById("media-results");
  const btn = document.getElementById("find-media-btn");

  if (!shots) { progressEl.innerText = "Enter at least one shot description."; return; }

  btn.disabled = true;
  resultEl.innerHTML = "";
  progressEl.innerText = "Starting...";

  const resp = await fetch("/api/studio/media", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ shots }),
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
      btn.disabled = false;
      const rows = result.manifest || [];
      if (rows.length === 0) {
        progressEl.innerText = "Done - nothing survived the quality filter.";
        return;
      }
      progressEl.innerText = `Done - kept ${rows.length} file(s).`;

      const byShot = {};
      for (const row of rows) {
        (byShot[row.shot_id] = byShot[row.shot_id] || []).push(row);
      }
      resultEl.innerHTML = Object.entries(byShot).map(([shotId, group]) => `
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
      `).join("");
    },
    onError: (err) => {
      progressEl.innerText = "Error: " + err;
      btn.disabled = false;
    },
  });
});
