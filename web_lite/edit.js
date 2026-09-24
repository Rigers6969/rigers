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

// Appends a cache-busting param without producing a malformed double "?"
// when the URL already has a query string (e.g. thumbnail URLs carry
// ?aspect=... - naively appending another "?t=..." after that makes the
// whole "aspect=9:16?t=..." string get parsed as one mangled query value
// server-side, which 404s).
function cacheBust(url) {
  return `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`;
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

const slug = new URLSearchParams(window.location.search).get("slug");
if (!slug) {
  document.body.innerHTML = '<p style="padding:40px; color:var(--text-dim);">No video specified - go back to <a href="/produce.html" style="color:var(--gold);">Produce</a> and click "Edit" on a video.</p>';
  throw new Error("no slug");
}
document.getElementById("edit-title").innerText = `Edit: ${slug}`;

let selectedMusic = null; // filename, or null for "no music"

// ---------------------------------------------------------------------
// Preview + state
// ---------------------------------------------------------------------
async function loadState() {
  const resp = await fetch(`/api/editor/${encodeURIComponent(slug)}/state`);
  const data = await resp.json();
  if (!resp.ok) {
    document.getElementById("preview-note").innerText = data.error || "Could not load this video.";
    return;
  }

  const videoEl = document.getElementById("preview-video");
  const downloadLink = document.getElementById("download-link");
  const noteEl = document.getElementById("preview-note");

  const url = data.edited_video_url || data.base_video_url;
  if (url) {
    videoEl.src = cacheBust(url); // cache-bust after re-applying edits
    downloadLink.href = url;
    downloadLink.classList.remove("hidden");
  }
  noteEl.innerText = data.has_edited
    ? "Showing the edited version (music/captions applied)."
    : "Showing the original assembled video - no edits applied yet.";

  const headlineInput = document.getElementById("thumb-headline");
  if (!headlineInput.value && data.youtube_title) {
    headlineInput.value = data.youtube_title;
  }
  if (data.thumbnail_url) {
    showThumbnail(cacheBust(data.thumbnail_url));
  }
}
loadState();

// ---------------------------------------------------------------------
// Thumbnail
// ---------------------------------------------------------------------
function showThumbnail(url) {
  document.getElementById("thumb-preview").src = url;
  document.getElementById("thumb-download-link").href = url;
  document.getElementById("thumb-preview-wrap").classList.remove("hidden");
}

document.getElementById("thumb-generate-btn").addEventListener("click", async () => {
  const btn = document.getElementById("thumb-generate-btn");
  const progressEl = document.getElementById("thumb-progress");
  const headline = document.getElementById("thumb-headline").value.trim();
  if (!headline) {
    progressEl.innerText = "Enter a headline first.";
    return;
  }

  btn.disabled = true;
  progressEl.innerText = "Generating...";

  const aspect = document.getElementById("thumb-aspect").value;
  const resp = await fetch(`/api/editor/${encodeURIComponent(slug)}/thumbnail`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      headline,
      kicker: document.getElementById("thumb-kicker").value.trim(),
      tag: document.getElementById("thumb-tag").value.trim(),
      brand: document.getElementById("thumb-brand").value.trim(),
      aspect,
    }),
  });
  const data = await resp.json();
  btn.disabled = false;

  if (!resp.ok) {
    progressEl.innerText = data.error || "Failed to generate.";
    return;
  }
  progressEl.innerText = "Done.";
  showThumbnail(cacheBust(data.thumbnail_url));
});

// ---------------------------------------------------------------------
// Music library
// ---------------------------------------------------------------------
async function loadMusicLibrary() {
  const resp = await fetch("/api/editor/music");
  const data = await resp.json();
  const listEl = document.getElementById("music-library");

  const tracks = data.tracks || [];
  const rows = [`
    <div class="music-track ${selectedMusic === null ? "selected" : ""}">
      <label><input type="radio" name="music-pick" value="" ${selectedMusic === null ? "checked" : ""}> No music</label>
    </div>
  `];
  for (const name of tracks) {
    rows.push(`
      <div class="music-track ${selectedMusic === name ? "selected" : ""}">
        <label><input type="radio" name="music-pick" value="${escapeHtml(name)}" ${selectedMusic === name ? "checked" : ""}> ${escapeHtml(name)}</label>
        <audio controls src="/api/editor/music/file/${encodeURIComponent(name)}"></audio>
      </div>
    `);
  }
  listEl.innerHTML = tracks.length ? rows.join("") : rows[0] + '<p class="hint">No tracks uploaded yet.</p>';

  listEl.querySelectorAll('input[name="music-pick"]').forEach((input) => {
    input.addEventListener("change", (e) => {
      selectedMusic = e.target.value || null;
      listEl.querySelectorAll(".music-track").forEach((el) => el.classList.remove("selected"));
      e.target.closest(".music-track").classList.add("selected");
    });
  });
}
loadMusicLibrary();

document.getElementById("music-upload-btn").addEventListener("click", async () => {
  const input = document.getElementById("music-upload-input");
  const statusEl = document.getElementById("music-upload-status");
  if (!input.files || !input.files[0]) {
    statusEl.innerText = "Choose a file first.";
    return;
  }
  statusEl.innerText = "Uploading...";
  const formData = new FormData();
  formData.append("file", input.files[0]);
  const resp = await fetch("/api/editor/music/upload", { method: "POST", body: formData });
  const data = await resp.json();
  if (!resp.ok) {
    statusEl.innerText = data.error || "Upload failed.";
    return;
  }
  statusEl.innerText = `Uploaded ${data.filename}.`;
  selectedMusic = data.filename;
  input.value = "";
  loadMusicLibrary();
});

// ---------------------------------------------------------------------
// Jamendo search - real, licensed tracks, already filtered server-side
// to commercial-safe licenses only (see music_finder.py).
// ---------------------------------------------------------------------
function formatDuration(seconds) {
  if (!seconds && seconds !== 0) return "";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

async function searchMusic() {
  const query = document.getElementById("music-search-input").value.trim();
  const resultsEl = document.getElementById("music-search-results");
  const errorEl = document.getElementById("music-search-error");
  if (!query) return;

  resultsEl.innerHTML = '<p class="empty-note">Searching...</p>';
  errorEl.classList.add("hidden");

  const resp = await fetch(`/api/editor/music/search?q=${encodeURIComponent(query)}`);
  const data = await resp.json();

  if (data.error) {
    errorEl.innerText = data.error;
    errorEl.classList.remove("hidden");
  }

  const tracks = data.tracks || [];
  if (!tracks.length) {
    resultsEl.innerHTML = data.error ? "" : '<p class="empty-note">No results.</p>';
    return;
  }

  resultsEl.innerHTML = tracks.map((t, i) => `
    <div class="music-track" data-index="${i}">
      <label style="flex:none; cursor:default;">${escapeHtml(t.title)} <span class="hint">by ${escapeHtml(t.artist)} (${formatDuration(t.duration)})</span></label>
      <audio controls src="${t.preview_url}"></audio>
      <button class="btn-ghost music-add-btn" style="font-size:11px; padding:4px 10px;">Add to Library</button>
    </div>
  `).join("");

  resultsEl.querySelectorAll(".music-add-btn").forEach((btn, i) => {
    btn.addEventListener("click", async () => {
      const track = tracks[i];
      btn.disabled = true;
      btn.innerText = "Adding...";
      const resp = await fetch("/api/editor/music/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: track.id, title: track.title, artist: track.artist, download_url: track.download_url,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        btn.innerText = data.error || "Failed";
        btn.disabled = false;
        return;
      }
      btn.innerText = "Added";
      selectedMusic = data.filename;
      loadMusicLibrary();
    });
  });
}

document.getElementById("music-search-btn").addEventListener("click", searchMusic);
document.getElementById("music-search-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") searchMusic();
});

// ---------------------------------------------------------------------
// Captions
// ---------------------------------------------------------------------
async function loadCaptionStyles() {
  const resp = await fetch("/api/editor/caption-styles");
  const data = await resp.json();
  const select = document.getElementById("caption-style-select");
  select.innerHTML = (data.styles || []).map((s) => `<option value="${s.id}">${escapeHtml(s.label)}</option>`).join("");
  if (data.default) select.value = data.default;
}
loadCaptionStyles();

document.getElementById("captions-toggle").addEventListener("change", (e) => {
  document.getElementById("caption-style-select").classList.toggle("hidden", !e.target.checked);
});

// ---------------------------------------------------------------------
// Apply
// ---------------------------------------------------------------------
document.getElementById("apply-btn").addEventListener("click", async () => {
  const btn = document.getElementById("apply-btn");
  const progressEl = document.getElementById("apply-progress");
  const addCaptions = document.getElementById("captions-toggle").checked;
  const captionStyle = document.getElementById("caption-style-select").value;

  btn.disabled = true;
  progressEl.innerText = "Starting...";

  const resp = await fetch(`/api/editor/${encodeURIComponent(slug)}/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      add_captions: addCaptions,
      caption_style: captionStyle,
      music_filename: selectedMusic,
    }),
  });
  const data = await resp.json();
  if (!resp.ok) {
    progressEl.innerText = data.error || "Failed to start.";
    btn.disabled = false;
    return;
  }

  pollJob(data.job_id, {
    onProgress: (msg) => { progressEl.innerText = msg; },
    onDone: () => {
      progressEl.innerText = "Done.";
      btn.disabled = false;
      loadState();
    },
    onError: (err) => {
      progressEl.innerText = "Error: " + err;
      btn.disabled = false;
    },
  });
});
