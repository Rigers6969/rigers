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

let chapters = [];
let activeIndex = -1;

function renderToc() {
  const toc = document.getElementById("toc-list");
  toc.innerHTML = "";
  let lastBook = null;
  chapters.forEach((ch, i) => {
    if (ch.book !== lastBook) {
      const heading = document.createElement("div");
      heading.className = "toc-book";
      heading.innerText = ch.book;
      toc.appendChild(heading);
      lastBook = ch.book;
    }
    const link = document.createElement("a");
    link.href = "#";
    link.className = "toc-chapter" + (i === activeIndex ? " active" : "");
    link.innerText = ch.chapter;
    link.addEventListener("click", (e) => {
      e.preventDefault();
      showChapter(i);
    });
    toc.appendChild(link);
  });
}

function showChapter(i) {
  activeIndex = i;
  renderToc();
  const ch = chapters[i];
  const reader = document.getElementById("reader-panel");
  const paragraphs = ch.text.split("\n").filter((p) => p.trim()).map((p) => `<p>${escapeHtml(p)}</p>`).join("");
  reader.innerHTML = `
    <div class="reader-book">${escapeHtml(ch.book)}</div>
    <div class="reader-chapter">${escapeHtml(ch.chapter)}</div>
    <div class="reader-text">${paragraphs}</div>
  `;
}

function renderAll() {
  document.getElementById("guide-empty").classList.toggle("hidden", chapters.length > 0);
  renderToc();
  if (chapters.length > 0 && activeIndex === -1) {
    showChapter(0);
  }
}

async function loadChapters() {
  const resp = await fetch("/api/english/chapters");
  const data = await resp.json();
  chapters = data.chapters || [];
  document.getElementById("guide-updated").innerText =
    chapters.length > 0 ? `${chapters.length} chapter(s) loaded.` : "No chapters yet.";
  renderAll();
}

document.getElementById("refresh-btn").addEventListener("click", async () => {
  const btn = document.getElementById("refresh-btn");
  const progressEl = document.getElementById("guide-progress");
  const errorEl = document.getElementById("guide-error");
  btn.disabled = true;
  errorEl.classList.add("hidden");
  progressEl.classList.remove("hidden");
  progressEl.innerText = "Starting...";

  const resp = await fetch("/api/english/refresh", { method: "POST" });
  if (!resp.ok) {
    btn.disabled = false;
    progressEl.classList.add("hidden");
    errorEl.classList.remove("hidden");
    errorEl.innerText = "Could not start the refresh job.";
    return;
  }
  const data = await resp.json();

  pollJob(data.job_id, {
    onProgress: (msg) => { progressEl.innerText = msg; },
    onDone: (result) => {
      btn.disabled = false;
      progressEl.classList.add("hidden");
      chapters = result.chapters || [];
      activeIndex = -1;
      document.getElementById("guide-updated").innerText = `${chapters.length} chapter(s) loaded.`;
      renderAll();
    },
    onError: (msg) => {
      btn.disabled = false;
      progressEl.classList.add("hidden");
      errorEl.classList.remove("hidden");
      errorEl.innerText = msg;
    },
  });
});

loadChapters();
