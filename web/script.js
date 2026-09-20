// ---------------------------------------------------------------------
// Canvas bat swarm - a real boid flocking simulation (cohesion, separation,
// alignment), not just CSS drift. This needs the real page canvas, which
// is exactly why this is a plain HTML/CSS/JS site instead of embedding it
// inside a Streamlit component (those render in a sandboxed iframe that
// can't be sized to the whole page reliably and adds real overhead for
// something this animation-heavy).
// ---------------------------------------------------------------------

const canvas = document.getElementById("bat-canvas");
const ctx = canvas.getContext("2d");

let bats = [];
const BAT_COUNT = 22;
const NEIGHBOR_RADIUS = 90;
const SEPARATION_RADIUS = 28;
const MAX_SPEED = 1.6;

function resizeCanvas() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}
window.addEventListener("resize", resizeCanvas);
resizeCanvas();

function initBats() {
  bats = [];
  for (let i = 0; i < BAT_COUNT; i++) {
    bats.push({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * MAX_SPEED,
      vy: (Math.random() - 0.5) * MAX_SPEED,
      size: 14 + Math.random() * 12,
      flapPhase: Math.random() * Math.PI * 2,
      flapSpeed: 4 + Math.random() * 3,
    });
  }
}
initBats();

function limitSpeed(bat) {
  const speed = Math.hypot(bat.vx, bat.vy);
  if (speed > MAX_SPEED) {
    bat.vx = (bat.vx / speed) * MAX_SPEED;
    bat.vy = (bat.vy / speed) * MAX_SPEED;
  }
}

function stepFlock() {
  for (const bat of bats) {
    let cohesionX = 0, cohesionY = 0, cohesionCount = 0;
    let alignX = 0, alignY = 0;
    let separateX = 0, separateY = 0;

    for (const other of bats) {
      if (other === bat) continue;
      const dx = other.x - bat.x;
      const dy = other.y - bat.y;
      const dist = Math.hypot(dx, dy);
      if (dist < NEIGHBOR_RADIUS) {
        cohesionX += other.x;
        cohesionY += other.y;
        cohesionCount++;
        alignX += other.vx;
        alignY += other.vy;
      }
      if (dist < SEPARATION_RADIUS && dist > 0) {
        separateX -= dx / dist;
        separateY -= dy / dist;
      }
    }

    if (cohesionCount > 0) {
      cohesionX = cohesionX / cohesionCount - bat.x;
      cohesionY = cohesionY / cohesionCount - bat.y;
      bat.vx += cohesionX * 0.0006;
      bat.vy += cohesionY * 0.0006;
      bat.vx += (alignX / cohesionCount - bat.vx) * 0.02;
      bat.vy += (alignY / cohesionCount - bat.vy) * 0.02;
    }
    bat.vx += separateX * 0.03;
    bat.vy += separateY * 0.03;

    // Gentle wander so the flock doesn't freeze into a static formation.
    bat.vx += (Math.random() - 0.5) * 0.04;
    bat.vy += (Math.random() - 0.5) * 0.04;

    limitSpeed(bat);
    bat.x += bat.vx;
    bat.y += bat.vy;

    // Wrap around edges.
    if (bat.x < -30) bat.x = canvas.width + 30;
    if (bat.x > canvas.width + 30) bat.x = -30;
    if (bat.y < -30) bat.y = canvas.height + 30;
    if (bat.y > canvas.height + 30) bat.y = -30;
  }
}

function drawBats(time) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (const bat of bats) {
    const angle = Math.atan2(bat.vy, bat.vx);
    const flap = 1 + 0.25 * Math.sin(time * 0.001 * bat.flapSpeed + bat.flapPhase);
    ctx.save();
    ctx.translate(bat.x, bat.y);
    ctx.rotate(angle);
    ctx.scale(1, flap);
    ctx.globalAlpha = 0.35;
    ctx.font = `${bat.size}px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("\u{1F987}", 0, 0);
    ctx.restore();
  }
}

function animate(time) {
  stepFlock();
  drawBats(time);
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
  const hour = parseInt(
    new Intl.DateTimeFormat("en-GB", { timeZone: TIMEZONE, hour: "numeric", hour12: false }).format(now),
    10
  );

  let greeting;
  if (hour < 5) greeting = `Good Night, ${APP_NAME}`;
  else if (hour < 12) greeting = `Good Morning, ${APP_NAME}`;
  else if (hour < 18) greeting = `Good Afternoon, ${APP_NAME}`;
  else greeting = `Good Evening, ${APP_NAME}`;

  document.getElementById("greeting").innerText = greeting;
  document.getElementById("splash-clock").innerText = timeStr;
  const headerClock = document.getElementById("header-clock");
  if (headerClock) headerClock.innerText = timeStr;
}
tickClock();
setInterval(tickClock, 1000);

// ---------------------------------------------------------------------
// Splash gate
// ---------------------------------------------------------------------

document.getElementById("enter-btn").addEventListener("click", () => {
  document.getElementById("splash").classList.add("hidden");
  document.getElementById("main").classList.remove("hidden");
  loadStats();
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
    }
    if (data.instagram) {
      setCard("card-followers", data.instagram.followers_count, `@${data.instagram.username}`);
      setCard("card-posts", data.instagram.media_count, "");
    }
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
