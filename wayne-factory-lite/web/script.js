// ---------------------------------------------------------------------
// Ember particle drift - a light ambient background animation (fixed
// full-page canvas, so it needs the real DOM rather than a sandboxed
// Streamlit component). Deliberately not a literal bat animation this
// time - just slow-drifting gold embers behind the grid texture.
// ---------------------------------------------------------------------

const canvas = document.getElementById("ember-canvas");
const ctx = canvas.getContext("2d");

let embers = [];
const EMBER_COUNT = 46;

function resizeCanvas() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}
window.addEventListener("resize", resizeCanvas);
resizeCanvas();

function initEmbers() {
  embers = [];
  for (let i = 0; i < EMBER_COUNT; i++) {
    embers.push({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      r: 0.6 + Math.random() * 1.8,
      speed: 0.15 + Math.random() * 0.35,
      sway: Math.random() * Math.PI * 2,
      swaySpeed: 0.2 + Math.random() * 0.4,
      alpha: 0.15 + Math.random() * 0.35,
    });
  }
}
initEmbers();

function stepEmbers(time) {
  for (const e of embers) {
    e.y -= e.speed;
    e.x += Math.sin(time * 0.0005 * e.swaySpeed + e.sway) * 0.3;
    if (e.y < -10) {
      e.y = canvas.height + 10;
      e.x = Math.random() * canvas.width;
    }
  }
}

function drawEmbers() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (const e of embers) {
    ctx.beginPath();
    ctx.arc(e.x, e.y, e.r, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(201, 162, 75, ${e.alpha})`;
    ctx.fill();
  }
}

function animate(time) {
  stepEmbers(time);
  drawEmbers();
  requestAnimationFrame(animate);
}
requestAnimationFrame(animate);

// ---------------------------------------------------------------------
// Clock + time-of-day greeting (Tirana / Albania time)
// ---------------------------------------------------------------------

const TIMEZONE = "Europe/Tirane";
const APP_NAME = "Rigers";

function tickClock() {
  const now = new Date();
  const timeStr = new Intl.DateTimeFormat("en-GB", {
    timeZone: TIMEZONE, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(now);
  const dateStr = new Intl.DateTimeFormat("en-GB", {
    timeZone: TIMEZONE, weekday: "long", day: "numeric", month: "long",
  }).format(now);
  const hour = parseInt(
    new Intl.DateTimeFormat("en-GB", { timeZone: TIMEZONE, hour: "numeric", hour12: false }).format(now),
    10
  );

  let greeting;
  if (hour < 5) greeting = "Good Night";
  else if (hour < 12) greeting = "Good Morning";
  else if (hour < 18) greeting = "Good Afternoon";
  else greeting = "Good Evening";

  document.getElementById("greeting").innerHTML = `${greeting}, <em>${APP_NAME}</em>.`;
  document.getElementById("eyebrow").innerText = `Gotham City · ${dateStr}`;
  document.getElementById("gate-greeting").innerHTML = `${greeting}, <em>${APP_NAME}</em>.`;
  document.getElementById("gate-eyebrow").innerText = `Gotham City · ${dateStr}`;
  document.getElementById("gate-clock").innerText = timeStr;
  document.getElementById("corner-clock").innerText = timeStr;
  const headerClock = document.getElementById("header-clock");
  if (headerClock) headerClock.innerText = timeStr;
}
tickClock();
setInterval(tickClock, 1000);

// ---------------------------------------------------------------------
// Entry gate - shows the time-aware greeting full-screen first, then
// reveals the dashboard. Stats are fetched in the background while the
// gate is up, so real numbers are already animating in the moment it's
// dismissed instead of the user waiting on a spinner.
// ---------------------------------------------------------------------

document.getElementById("enter-btn").addEventListener("click", () => {
  document.getElementById("gate").classList.add("gate-hidden");
  document.getElementById("site").classList.remove("hidden");
});

// ---------------------------------------------------------------------
// Stats: fetch from the Flask backend (never sees API keys directly) and
// animate each number counting up from 0 (ease-out cubic, 1.5s).
// ---------------------------------------------------------------------

function animateValue(el, target, duration = 1500) {
  const start = performance.now();
  function ease(t) { return 1 - Math.pow(1 - t, 3); }
  function tick(now) {
    const progress = Math.min((now - start) / duration, 1);
    el.innerText = Math.floor(ease(progress) * target).toLocaleString();
    if (progress < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

function setCard(card, value, note) {
  const valueEl = card.querySelector(".stat-value");
  const noteEl = card.querySelector(".stat-note");
  noteEl.innerText = note || "";
  if (value === null || value === undefined) {
    valueEl.classList.add("hidden-value");
    valueEl.innerText = "Hidden";
  } else {
    valueEl.classList.remove("hidden-value");
    animateValue(valueEl, value);
  }
}

function setTicker(elId, value) {
  const el = document.getElementById(elId);
  if (value === null || value === undefined) {
    el.innerText = "—";
  } else {
    animateValue(el, value);
  }
}

function makeStatCard(num, label) {
  const card = document.createElement("div");
  card.className = "div-card stat-card";
  card.innerHTML = `
    <div class="div-num">${num}</div>
    <h3 class="stat-value" data-target="0">0</h3>
    <p class="div-label"></p>
    <p class="stat-note"></p>
  `;
  card.querySelector(".div-label").innerText = label;
  return card;
}

function renderChannel(channel) {
  const block = document.createElement("div");
  block.className = "channel-block";

  const heading = document.createElement("h3");
  heading.className = "channel-heading";
  heading.innerText = channel.name;
  block.appendChild(heading);

  const grid = document.createElement("div");
  grid.className = "div-grid";

  const subsCard = makeStatCard("01 — YouTube", "Subscribers");
  const viewsCard = makeStatCard("02 — YouTube", "Total Views");
  const videosCard = makeStatCard("03 — YouTube", "Videos Published");
  const statusCard = makeStatCard("04 — Status", "Connection status");
  grid.append(subsCard, viewsCard, videosCard, statusCard);
  block.appendChild(grid);

  const yt = channel.youtube;
  if (yt) {
    setCard(subsCard, yt.subscriber_count_hidden ? null : yt.subscriber_count, yt.subscriber_count_hidden ? "hidden by channel owner" : "");
    setCard(viewsCard, yt.view_count, "");
    setCard(videosCard, yt.video_count, "");
    statusCard.querySelector(".stat-value").innerText = channel.error ? "Partial" : "Live";
    statusCard.querySelector(".stat-note").innerText = "YouTube connected";
  } else {
    statusCard.querySelector(".stat-value").innerText = "Error";
    statusCard.querySelector(".stat-note").innerText = channel.error || "";
  }

  return block;
}

async function loadStats() {
  const errorsEl = document.getElementById("errors");
  const sectionsEl = document.getElementById("channel-sections");
  errorsEl.innerHTML = "";
  sectionsEl.innerHTML = "";
  try {
    const resp = await fetch("/api/stats");
    const data = await resp.json();

    let totalSubs = 0, totalViews = 0, anyYoutube = false;
    for (const channel of data.channels || []) {
      sectionsEl.appendChild(renderChannel(channel));
      if (channel.youtube) {
        anyYoutube = true;
        totalViews += channel.youtube.view_count || 0;
        if (!channel.youtube.subscriber_count_hidden) {
          totalSubs += channel.youtube.subscriber_count || 0;
        }
      }
    }

    setTicker("ticker-subs", anyYoutube ? totalSubs : null);
    setTicker("ticker-views", anyYoutube ? totalViews : null);
    document.getElementById("ticker-updated").innerText = new Intl.DateTimeFormat("en-GB", {
      timeZone: TIMEZONE, hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(new Date());

    for (const err of data.errors || []) {
      const div = document.createElement("div");
      div.className = "error-line";
      div.innerText = err;
      errorsEl.appendChild(div);
    }
  } catch (exc) {
    const div = document.createElement("div");
    div.className = "error-line";
    div.innerText = "Could not reach the backend: " + exc;
    errorsEl.appendChild(div);
  }
}

document.getElementById("refresh-btn").addEventListener("click", loadStats);
document.getElementById("hero-refresh-btn").addEventListener("click", loadStats);
loadStats();

// ---------------------------------------------------------------------
// Revenue goal bar - real lifetime YouTube ad revenue vs. a $10,000 goal
// (see analytics.py's fetch_youtube_revenue / youtube_auth_setup.py).
// This is the first thing shown once the dashboard loads, per request.
// ---------------------------------------------------------------------

async function loadRevenue() {
  try {
    const resp = await fetch("/api/revenue");
    const data = await resp.json();

    const goal = data.goal || 10000;
    const current = data.current || 0;
    const pct = Math.max(0, Math.min(100, (current / goal) * 100));

    document.getElementById("goal-target").innerText = Math.round(goal).toLocaleString();
    animateValue(document.getElementById("goal-current"), Math.round(current));
    document.getElementById("goal-bar-fill").style.width = pct + "%";

    const noteEl = document.getElementById("goal-note");
    noteEl.innerText = data.note || "";
  } catch (exc) {
    document.getElementById("goal-note").innerText = "Could not reach the backend: " + exc;
  }
}
loadRevenue();
document.getElementById("refresh-btn").addEventListener("click", loadRevenue);
document.getElementById("hero-refresh-btn").addEventListener("click", loadRevenue);
