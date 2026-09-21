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
const APP_NAME = "Bruce";

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

function setCard(cardId, value, note) {
  const card = document.getElementById(cardId);
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

async function loadStats() {
  const errorsEl = document.getElementById("errors");
  errorsEl.innerHTML = "";
  try {
    const resp = await fetch("/api/stats");
    const data = await resp.json();

    if (data.youtube) {
      setCard(
        "card-subscribers",
        data.youtube.subscriber_count_hidden ? null : data.youtube.subscriber_count,
        data.youtube.subscriber_count_hidden ? "hidden by channel owner" : ""
      );
      setCard("card-views", data.youtube.view_count, "");
      setCard("card-videos", data.youtube.video_count, "");
      setTicker("ticker-subs", data.youtube.subscriber_count_hidden ? null : data.youtube.subscriber_count);
      setTicker("ticker-views", data.youtube.view_count);
    }
    if (data.instagram) {
      setCard("card-followers", data.instagram.followers_count, `@${data.instagram.username}`);
      setCard("card-posts", data.instagram.media_count, "");
      setTicker("ticker-followers", data.instagram.followers_count);
    }

    document.getElementById("ticker-updated").innerText = new Intl.DateTimeFormat("en-GB", {
      timeZone: TIMEZONE, hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(new Date());

    for (const err of data.errors || []) {
      const div = document.createElement("div");
      div.className = "error-line";
      div.innerText = err;
      errorsEl.appendChild(div);
    }

    const statusTile = document.getElementById("status-tile");
    const statusNote = document.getElementById("status-note");
    const connected = [data.youtube ? "YouTube" : null, data.instagram ? "Instagram" : null].filter(Boolean);
    if (connected.length === 0) {
      statusTile.innerText = "Not configured";
      statusNote.innerText = "add credentials to config.json";
    } else if ((data.errors || []).length > 0) {
      statusTile.innerText = "Partial";
      statusNote.innerText = `${connected.join(" + ")} connected`;
    } else {
      statusTile.innerText = "Live";
      statusNote.innerText = `${connected.join(" + ")} connected`;
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
