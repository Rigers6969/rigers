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

// A "Produce Video" link from the News page (see news.js) arrives as
// /produce.html?topic=... - prefill the topic box from it so a headline
// can become a video without retyping it.
const prefillTopic = new URLSearchParams(window.location.search).get("topic");
if (prefillTopic) {
  document.getElementById("topic-text").value = prefillTopic;
}

// ---------------------------------------------------------------------
// Pipeline tracker - maps producer.py's plain-text progress messages to
// one of the 6 stages it always reports in order (see produce_video() in
// producer.py), so the page shows a live stepper instead of just a
// changing line of text.
// ---------------------------------------------------------------------
const PIPELINE_STAGES = ["script", "shots", "metadata", "voiceover", "media", "assemble"];
const PIPELINE_MATCHERS = {
  script: (m) => m.startsWith("Writing script") || m.startsWith("Script:"),
  shots: (m) => m.startsWith("Planning shots"),
  metadata: (m) => m.startsWith("Writing YouTube"),
  voiceover: (m) => m.startsWith("Generating voiceover") || m.startsWith("Voiceover:"),
  media: (m) => m.startsWith("Searching stock media") || m.startsWith("Media:"),
  assemble: (m) => m.startsWith("Assembling final video") || m.startsWith("Video:"),
};

function resetPipeline() {
  document.getElementById("pipeline-tracker").classList.remove("hidden");
  for (const stage of PIPELINE_STAGES) {
    const el = document.querySelector(`.pipeline-step[data-stage="${stage}"]`);
    el.classList.remove("done", "active", "error");
  }
}

function updatePipeline(message) {
  const stageIndex = PIPELINE_STAGES.findIndex((stage) => PIPELINE_MATCHERS[stage](message));
  if (stageIndex === -1) return; // sub-message that doesn't map cleanly - leave current state as-is
  PIPELINE_STAGES.forEach((stage, i) => {
    const el = document.querySelector(`.pipeline-step[data-stage="${stage}"]`);
    el.classList.remove("done", "active");
    if (i < stageIndex) el.classList.add("done");
    else if (i === stageIndex) el.classList.add("active");
  });
}

function finishPipeline(hasError) {
  for (const stage of PIPELINE_STAGES) {
    const el = document.querySelector(`.pipeline-step[data-stage="${stage}"]`);
    if (hasError) {
      // Whichever stage was mid-flight when the job failed becomes the
      // error marker; everything before it stays "done" since it did
      // complete successfully.
      if (el.classList.contains("active")) {
        el.classList.remove("active");
        el.classList.add("error");
      }
    } else {
      el.classList.remove("active");
      el.classList.add("done");
    }
  }
}

// ---------------------------------------------------------------------
// Batch mode toggle - swaps the single topic box for "one per line" and
// the pipeline tracker (which only makes sense for one video) for a
// simple per-video status list.
// ---------------------------------------------------------------------
document.getElementById("batch-toggle").addEventListener("change", (e) => {
  const isBatch = e.target.checked;
  const topicEl = document.getElementById("topic-text");
  document.getElementById("topic-label").innerText = isBatch ? "Topics (one per line)" : "Topic";
  topicEl.rows = isBatch ? 8 : 3;
  topicEl.placeholder = isBatch
    ? "One topic per line, e.g.\nThe collapse of a company that faked its own revenue\nA hedge fund that hid losses for a decade\n..."
    : "e.g. The collapse of a company that faked its own revenue for a decade";
  document.getElementById("produce-btn").innerText = isBatch ? "Produce Batch" : "Produce Video";
});

// ---------------------------------------------------------------------
// Produce
// ---------------------------------------------------------------------
// Editing style (pacing measured from a reference video via
// style_analyzer.py) is applied automatically server-side using your most
// recently saved profile - no page control for it; see producer.py's
// default_style_slug() and POST /api/style/analyze if you want to analyze
// a different reference video from a script instead.
document.getElementById("produce-btn").addEventListener("click", async () => {
  const isBatch = document.getElementById("batch-toggle").checked;
  const channel = document.getElementById("channel-input").value.trim();
  const engine = document.getElementById("engine-select").value;
  const length = document.getElementById("length-select").value;
  const voice = document.getElementById("voice-select").value;
  const ollama_host = document.getElementById("ollama-host").value.trim();
  const anthropic_key = document.getElementById("anthropic-key").value.trim();

  const progressEl = document.getElementById("produce-progress");
  if (!channel) { progressEl.innerText = "Enter a channel name first (e.g. History, Science)."; return; }
  const resultEl = document.getElementById("produce-result");
  const batchListEl = document.getElementById("batch-list");
  const btn = document.getElementById("produce-btn");

  btn.disabled = true;
  resultEl.innerHTML = "";

  if (isBatch) {
    const topics = document.getElementById("topic-text").value
      .split("\n").map((t) => t.trim()).filter(Boolean);
    if (!topics.length) { progressEl.innerText = "Enter at least one topic first."; btn.disabled = false; return; }

    document.getElementById("pipeline-tracker").classList.add("hidden");
    batchListEl.classList.remove("hidden");
    batchListEl.innerHTML = topics.map((t, i) => `<div class="save-status" id="batch-row-${i}">Queued: ${escapeHtml(t)}</div>`).join("");
    progressEl.innerText = "Starting batch...";

    const resp = await fetch("/api/auto/produce/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topics, channel, engine, length, voice, ollama_host, anthropic_key }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      progressEl.innerText = data.error || "Failed to start.";
      btn.disabled = false;
      return;
    }

    pollJob(data.job_id, {
      onProgress: (msg) => {
        progressEl.innerText = msg;
        const match = msg.match(/^Video (\d+)\/(\d+) \(([^)]*)\): (.*)$/);
        if (match) {
          const row = document.getElementById(`batch-row-${Number(match[1]) - 1}`);
          if (row) row.innerText = `${match[1]}/${match[2]} - ${match[3]}: ${match[4]}`;
        }
      },
      onDone: (result) => {
        progressEl.innerText = "Batch done.";
        (result.videos || []).forEach((v, i) => {
          const row = document.getElementById(`batch-row-${i}`);
          if (!row) return;
          row.innerText = v.error ? `Failed: ${v.topic} - ${v.error}` : `Done: ${v.slug}`;
          row.style.color = v.error ? "var(--red)" : "var(--gold)";
        });
        btn.disabled = false;
        loadVideos();
      },
      onError: (err) => {
        progressEl.innerText = "Error: " + err;
        btn.disabled = false;
      },
    });
    return;
  }

  const topic = document.getElementById("topic-text").value.trim();
  if (!topic) { progressEl.innerText = "Enter a topic first."; btn.disabled = false; return; }

  batchListEl.classList.add("hidden");
  progressEl.innerText = "Starting...";
  resetPipeline();

  const resp = await fetch("/api/auto/produce", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, channel, engine, length, voice, ollama_host, anthropic_key }),
  });
  const data = await resp.json();
  if (!resp.ok) {
    progressEl.innerText = data.error || "Failed to start.";
    btn.disabled = false;
    return;
  }

  pollJob(data.job_id, {
    onProgress: (msg) => { progressEl.innerText = msg; updatePipeline(msg); },
    onDone: (result) => {
      progressEl.innerText = "Done.";
      finishPipeline(false);
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
      finishPipeline(true);
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
        <span class="stage-dot ${v.has_video ? "done" : ""}" title="Final video"></span>
      </div>
      ${v.has_video ? `<a class="project-edit-btn" href="/edit.html?slug=${encodeURIComponent(v.slug)}">Edit &rarr;</a>` : ""}
    `;
    card.addEventListener("click", (e) => {
      if (e.target.closest(".project-edit-btn")) return;
      selectVideo(v.slug);
    });
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

  const review = data.review;
  const reviewHtml = review ? `
    <h4 style="margin-top:24px;">AI Review</h4>
    <p class="hint" style="margin-bottom:10px;">Feeds forward into this channel's future videos - see video_reviewer.py.</p>
    <div class="save-status" style="margin-bottom:8px;">
      <b>Script:</b> ${review.script_rating != null ? `${review.script_rating}/10` : "n/a"} &mdash; ${escapeHtml(review.script_notes || "")}
    </div>
    <div class="save-status" style="margin-bottom:8px;">
      <b>Title:</b> ${review.title_rating != null ? `${review.title_rating}/10` : "n/a"} &mdash; ${escapeHtml(review.title_notes || "")}
    </div>
    <div class="save-status" style="margin-bottom:8px;">
      <b>Photos:</b> ${review.visual_rating != null ? `${review.visual_rating}/10 average match` : "not reviewed"}
      ${(review.weak_shots || []).length ? `<br>${review.weak_shots.map((s) => `&middot; ${escapeHtml(s)}`).join("<br>")}` : ""}
    </div>
    ${(review.lessons || []).length ? `<div class="save-status"><b>Lessons carried into future videos:</b><br>${review.lessons.map((l) => `&middot; ${escapeHtml(l)}`).join("<br>")}</div>` : ""}
  ` : "";

  document.getElementById("detail-body").innerHTML = `
    <h4>Final Video</h4>
    ${data.video_url
      ? `<video controls src="${data.video_url}" style="width:100%; max-width:640px; background:#000; margin-bottom:10px;"></video>
         <div><a href="${data.video_url}" download class="btn-ghost" style="display:inline-block; margin:6px 0 20px;">Download .mp4</a>
         <button id="reassemble-btn" class="btn-ghost" style="margin-left:8px;">Re-assemble</button></div>
         ${yt.title ? `<p class="hint" style="margin:-8px 0 20px;">Suggested thumbnail headline: <b style="color:var(--gold);">${escapeHtml(yt.title)}</b> &mdash;
           <a href="/edit.html?slug=${encodeURIComponent(slug)}">generate it &rarr;</a></p>` : ""}`
      : `<p class="hint">Not assembled yet${data.manifest && data.manifest.length ? "" : " - no media found yet, so there's nothing to build a video from"}.</p>
         <button id="assemble-btn" class="btn-primary" ${data.manifest && data.manifest.length ? "" : "disabled"}>Assemble Video</button>
         <div id="assemble-progress" class="save-status"></div>`
    }

    ${reviewHtml}

    ${data.voiceover_url ? `<h4 style="margin-top:24px;">Voiceover</h4><audio controls src="${data.voiceover_url}" style="width:100%; margin-bottom:20px;"></audio>` : ""}

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

  const assembleBtn = document.getElementById("assemble-btn") || document.getElementById("reassemble-btn");
  if (assembleBtn) {
    assembleBtn.addEventListener("click", () => runAssemble(slug));
  }
}

async function runAssemble(slug) {
  const progressEl = document.getElementById("assemble-progress");
  const btn = document.getElementById("assemble-btn") || document.getElementById("reassemble-btn");
  if (btn) btn.disabled = true;
  if (progressEl) progressEl.innerText = "Starting...";

  const resp = await fetch(`/api/auto/videos/${encodeURIComponent(slug)}/assemble`, { method: "POST" });
  const data = await resp.json();
  if (!resp.ok) {
    if (progressEl) progressEl.innerText = data.error || "Failed to start.";
    if (btn) btn.disabled = false;
    return;
  }

  pollJob(data.job_id, {
    onProgress: (msg) => { if (progressEl) progressEl.innerText = msg; },
    onDone: () => { selectVideo(slug); loadVideos(); },
    onError: (err) => {
      if (progressEl) progressEl.innerText = "Error: " + err;
      if (btn) btn.disabled = false;
    },
  });
}

loadVideos();

// ---------------------------------------------------------------------
// Schedule panel - unattended per-channel daily production windows
// ---------------------------------------------------------------------
async function loadScheduleVoices() {
  const resp = await fetch("/api/studio/voices");
  const data = await resp.json();
  document.getElementById("sched-voice").innerHTML =
    data.voices.map((v) => `<option value="${v.id}">${escapeHtml(v.label)}</option>`).join("");
}
loadScheduleVoices();

document.getElementById("sched-engine").addEventListener("change", (e) => {
  const isClaude = e.target.value === "claude";
  document.getElementById("sched-anthropic-key").classList.toggle("hidden", !isClaude);
  document.getElementById("sched-ollama-host").classList.toggle("hidden", isClaude);
});

function isWindowActiveNow(entry) {
  const now = new Intl.DateTimeFormat("en-GB", {
    timeZone: TIMEZONE, hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date());
  return entry.start <= now && now < entry.end;
}

async function updateEntryStatus(entryId) {
  const statusEl = document.getElementById(`sched-status-${entryId}`);
  if (!statusEl) return;

  const jobResp = await fetch(`/api/schedule/${entryId}/job`);
  const jobData = await jobResp.json();
  if (!jobData.job_id) {
    statusEl.innerText = "Hasn't started today yet - waiting for the window to open.";
    return;
  }

  const resp = await fetch(`/api/jobs/${jobData.job_id}`);
  if (!resp.ok) {
    statusEl.innerText = "Lost track of today's job.";
    return;
  }
  const job = await resp.json();
  if (job.status === "running") {
    statusEl.innerHTML = `<span style="color:var(--gold);">&#9679; Producing:</span> ${escapeHtml(job.progress || "starting...")}`;
  } else if (job.status === "error") {
    statusEl.innerHTML = `<span style="color:var(--red, #e05252);">Failed:</span> ${escapeHtml(job.error || "unknown error")}`;
  } else if (job.status === "done") {
    const count = (job.result && job.result.videos || []).length;
    statusEl.innerText = `Done for today - produced ${count} video(s).`;
  }
}

async function loadSchedule() {
  const resp = await fetch("/api/schedule");
  const data = await resp.json();
  const listEl = document.getElementById("sched-list");

  if (!data.entries || data.entries.length === 0) {
    listEl.innerHTML = '<p class="empty-note">No scheduled windows yet.</p>';
    return;
  }

  listEl.innerHTML = data.entries.map((entry) => `
    <div class="save-status" style="margin-bottom:8px;">
      <div style="display:flex; align-items:center; justify-content:space-between; gap:12px;">
        <span>
          <b style="color:var(--gold);">${escapeHtml(entry.channel)}</b>
          &mdash; ${escapeHtml(entry.start)}&ndash;${escapeHtml(entry.end)}
          &middot; ${entry.engine === "claude" ? "Claude" : "Ollama"} &middot; ${entry.length === "short" ? "Short" : "Long"}
          ${isWindowActiveNow(entry) && entry.enabled ? '<span style="color:var(--gold);">&middot; window is open now</span>' : ""}
          ${entry.enabled ? "" : '<span style="opacity:0.6;"> &middot; disabled</span>'}
        </span>
        <span>
          <button class="btn-ghost sched-toggle-btn" data-id="${entry.id}" data-enabled="${entry.enabled}" style="padding:4px 10px; font-size:12px;">${entry.enabled ? "Disable" : "Enable"}</button>
          <button class="btn-ghost sched-delete-btn" data-id="${entry.id}" style="padding:4px 10px; font-size:12px;">Delete</button>
        </span>
      </div>
      ${entry.enabled ? `<div class="hint" id="sched-status-${entry.id}" style="margin-top:6px;">Checking status...</div>` : ""}
    </div>
  `).join("");

  listEl.querySelectorAll(".sched-toggle-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const entry = data.entries.find((e) => e.id === btn.dataset.id);
      await fetch(`/api/schedule/${btn.dataset.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...entry, enabled: btn.dataset.enabled !== "true" }),
      });
      loadSchedule();
    });
  });
  listEl.querySelectorAll(".sched-delete-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetch(`/api/schedule/${btn.dataset.id}`, { method: "DELETE" });
      loadSchedule();
    });
  });

  for (const entry of data.entries) {
    if (entry.enabled) updateEntryStatus(entry.id);
  }
}
loadSchedule();
setInterval(loadSchedule, 15000); // live-ish without needing a manual refresh

document.getElementById("sched-add-btn").addEventListener("click", async () => {
  const errorEl = document.getElementById("sched-error");
  errorEl.classList.add("hidden");

  const body = {
    channel: document.getElementById("sched-channel").value.trim(),
    start: document.getElementById("sched-start").value,
    end: document.getElementById("sched-end").value,
    engine: document.getElementById("sched-engine").value,
    length: document.getElementById("sched-length").value,
    voice: document.getElementById("sched-voice").value,
    ollama_host: document.getElementById("sched-ollama-host").value.trim(),
    anthropic_key: document.getElementById("sched-anthropic-key").value.trim(),
    enabled: true,
  };

  const resp = await fetch("/api/schedule", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json();
  if (!resp.ok) {
    errorEl.innerText = data.error || "Failed to add.";
    errorEl.classList.remove("hidden");
    return;
  }
  document.getElementById("sched-channel").value = "";
  loadSchedule();
});
