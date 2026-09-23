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

function timeAgo(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

// ---------------------------------------------------------------------
// Headlines - self-refreshing: the server caches for 10 minutes and
// refetches the RSS feeds itself when that goes stale, so this page just
// has to ask again periodically to always show current headlines.
// ---------------------------------------------------------------------
async function loadHeadlines(force) {
  const updatedEl = document.getElementById("news-updated");
  const sourcesEl = document.getElementById("news-sources");
  const errorsEl = document.getElementById("news-errors");
  const listEl = document.getElementById("headline-list");

  const resp = await fetch(`/api/news/headlines${force ? "?force=1" : ""}`);
  const data = await resp.json();

  updatedEl.innerText = data.fetched_at
    ? `Updated ${timeAgo(new Date(data.fetched_at * 1000).toISOString())}`
    : "Not yet fetched.";
  sourcesEl.innerText = data.sources && data.sources.length ? `· Sources: ${data.sources.join(", ")}` : "";

  if (data.errors && data.errors.length) {
    errorsEl.innerText = data.errors.join(" | ");
    errorsEl.classList.remove("hidden");
  } else {
    errorsEl.classList.add("hidden");
  }

  if (!data.items || data.items.length === 0) {
    listEl.innerHTML = '<p class="empty-note">No headlines yet.</p>';
    return;
  }

  listEl.innerHTML = data.items.map((item) => `
    <div class="headline-card">
      ${item.image_url ? `<img class="headline-thumb" src="${item.image_url}" loading="lazy" alt="">` : ""}
      <div class="headline-body">
        <div class="headline-source">${escapeHtml(item.source)}<span class="time">${timeAgo(item.published)}</span></div>
        <div class="headline-title"><a href="${item.link}" target="_blank" rel="noopener">${escapeHtml(item.title)}</a></div>
        <div class="headline-snippet">${escapeHtml(item.snippet)}</div>
        <div class="headline-actions">
          <a class="headline-link" href="${item.link}" target="_blank" rel="noopener">Read full article on ${escapeHtml(item.source)} &rarr;</a>
          <a class="headline-produce-btn" href="/produce.html?topic=${encodeURIComponent(item.title)}">Produce Video &rarr;</a>
        </div>
      </div>
    </div>
  `).join("");
}

document.getElementById("refresh-btn").addEventListener("click", () => loadHeadlines(true));
loadHeadlines(false);
// Self-updating: re-check every 5 minutes. The server-side 10-minute
// cache means this won't necessarily pull fresh data every single poll,
// but it never shows headlines older than the cache TTL for long.
setInterval(() => loadHeadlines(false), 5 * 60 * 1000);

// ---------------------------------------------------------------------
// Video coverage - real YouTube videos, embedded via YouTube's own
// player (an iframe pointed at youtube.com), never downloaded.
// ---------------------------------------------------------------------
async function loadVideos(query) {
  const errorEl = document.getElementById("video-error");
  const listEl = document.getElementById("video-list");
  listEl.innerHTML = '<p class="empty-note">Searching...</p>';

  const resp = await fetch(`/api/news/videos?q=${encodeURIComponent(query)}`);
  const data = await resp.json();

  if (data.error) {
    errorEl.innerText = data.error;
    errorEl.classList.remove("hidden");
  } else {
    errorEl.classList.add("hidden");
  }

  if (!data.videos || data.videos.length === 0) {
    listEl.innerHTML = '<p class="empty-note">No videos found.</p>';
    return;
  }

  listEl.innerHTML = data.videos.map((v) => `
    <div class="video-card">
      <iframe src="https://www.youtube.com/embed/${v.video_id}" title="${escapeHtml(v.title)}" loading="lazy" allowfullscreen></iframe>
      <div class="video-title">${escapeHtml(v.title)}</div>
      <div class="video-channel">${escapeHtml(v.channel)} &middot; ${timeAgo(v.published)}</div>
    </div>
  `).join("");
}

document.getElementById("video-search-btn").addEventListener("click", () => {
  loadVideos(document.getElementById("video-query").value.trim() || "stock market news today");
});
loadVideos("stock market news today");
