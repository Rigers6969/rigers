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

// A small stagger so a freshly-loaded list of cards eases in one after
// another instead of all popping in at once - capped so a long list
// doesn't drag the entrance out.
function staggerDelay(index) {
  return `${Math.min(index * 40, 400)}ms`;
}

// ---------------------------------------------------------------------
// Headlines-by-source bar chart. Single series (one measure - count per
// source), so one hue (the site's gold accent) carries it and no legend
// is needed - the chart title already says what's plotted. See the
// dataviz skill's mark spec: bars capped at 24px thick, rounded top
// corners only (square at the baseline), hairline baseline, value
// labeled at the bar's tip, category label below.
// ---------------------------------------------------------------------
function roundedTopBarPath(x, yTop, w, h, r) {
  const rr = Math.max(0, Math.min(r, h, w / 2));
  if (rr <= 0) return `M${x},${yTop} h${w} v${h} h${-w} Z`;
  return `M${x},${yTop + rr}
    a${rr},${rr} 0 0 1 ${rr},${-rr}
    h${w - 2 * rr}
    a${rr},${rr} 0 0 1 ${rr},${rr}
    v${h - rr}
    h${-w}
    Z`;
}

function renderSourceChart(items) {
  const container = document.getElementById("source-chart");
  const counts = {};
  for (const item of items) counts[item.source] = (counts[item.source] || 0) + 1;
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);

  if (!entries.length) {
    container.innerHTML = '<div class="chart-title">Headlines by Source</div><p class="empty-note">No data yet.</p>';
    return;
  }

  const barW = 30;
  const gap = 34;
  const chartH = 90;
  // topPad clears the value label above the tallest bar (it was clipping
  // outside the viewBox at the top edge); bottomPad clears the category
  // labels, which are long ("CNBC - US Top News") and rotated (labelAngle)
  // rather than overlapping horizontally at this bar spacing. leftPad
  // specifically clears the first bar's rotated label, which
  // (text-anchor="end", rotated) extends up-and-left from its anchor and
  // was running off the left edge of the viewBox at a shallower angle.
  const topPad = 22;
  const bottomPad = 85;
  const leftPad = 95;
  const rightPad = 20;
  const labelAngle = -40;
  const maxCount = Math.max(...entries.map(([, c]) => c));
  const svgW = leftPad + entries.length * barW + Math.max(0, entries.length - 1) * gap + rightPad;
  const svgH = topPad + chartH + bottomPad;
  const baselineY = topPad + chartH;

  const bars = entries.map(([source, count], i) => {
    const x = leftPad + i * (barW + gap);
    const h = maxCount > 0 ? (count / maxCount) * chartH : 0;
    const y = topPad + (chartH - h);
    const labelX = x + barW / 2;
    const labelY = baselineY + 14;
    return `
      <path d="${roundedTopBarPath(x, y, barW, h, 4)}" fill="var(--gold)"></path>
      <text x="${labelX}" y="${y - 8}" text-anchor="middle" font-size="12" fill="var(--text)" class="source-chart-bar-value">${count}</text>
      <text x="${labelX}" y="${labelY}" text-anchor="end" font-size="10.5" fill="var(--text-dim)" transform="rotate(${labelAngle} ${labelX} ${labelY})">${escapeHtml(source)}</text>
    `;
  }).join("");

  container.innerHTML = `
    <div class="chart-title">Headlines by Source</div>
    <svg viewBox="0 0 ${svgW} ${svgH}" class="source-chart-svg fade-in-up" role="img" aria-label="Bar chart of headline counts by source">
      <line x1="0" y1="${baselineY}" x2="${svgW}" y2="${baselineY}" stroke="var(--border)" stroke-width="1"></line>
      ${bars}
    </svg>
  `;
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

  renderSourceChart(data.items || []);

  if (!data.items || data.items.length === 0) {
    listEl.innerHTML = '<p class="empty-note">No headlines yet.</p>';
    return;
  }

  listEl.innerHTML = data.items.map((item, i) => `
    <div class="headline-card fade-in-up" style="animation-delay:${staggerDelay(i)}">
      ${item.image_url ? `<img class="headline-thumb" src="${item.image_url}" loading="lazy" alt="" onload="this.classList.add('loaded')">` : ""}
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

  listEl.innerHTML = data.videos.map((v, i) => `
    <div class="video-card fade-in-up" style="animation-delay:${staggerDelay(i)}">
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
