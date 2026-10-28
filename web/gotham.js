// Gotham look: a live night-city wallpaper behind every page, plus the bat logo
// and the open page marked in the menu.
(function () {
  const BAT_PATH = "M50 8c-1.6 3.2-3.4 3.6-5.2 1.2L43 4.5 41.2 13C35 8.6 24.8 6.8 12 9.5c8.4 3.4 10.6 9 8.6 16 7-4.2 14.6-2.6 18.8 4 1.4-3.6 3.6-5.6 5.6-6.2 1.6 3.8 3.2 7.6 5 12.2 1.8-4.6 3.4-8.4 5-12.2 2 .6 4.2 2.6 5.6 6.2 4.2-6.6 11.8-8.2 18.8-4-2-7 .2-12.6 8.6-16C75.2 6.8 65 8.6 58.8 13L57 4.5l-1.8 4.7C53.4 11.6 51.6 11.2 50 8z";
  const BAT = `<svg viewBox="0 0 100 46" aria-hidden="true"><path d="${BAT_PATH}"/></svg>`;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- live wallpaper ----------
  function wallpaper() {
    const cv = document.createElement("canvas");
    cv.id = "g-wall";
    document.body.prepend(cv);
    document.body.classList.add("g-live");
    const ctx = cv.getContext("2d");
    const bat = new Path2D(BAT_PATH);
    let W, H, sky, far, near, windows = [], drops = [], clouds = [], bats = [];
    let mx = 0, my = 0, flash = 0, nextFlash = performance.now() + 15000 + Math.random() * 20000;
    let seed = 11;
    const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280;

    function layer(draw) {
      const c = document.createElement("canvas");
      c.width = W + 80; c.height = H;
      draw(c.getContext("2d"));
      return c;
    }
    function city(g, base, minH, maxH, color, winChance, collect) {
      let x = -40;
      g.fillStyle = color;
      while (x < W + 80) {
        const w = 40 + rnd() * 90, h = minH + rnd() * (maxH - minH), top = H - h;
        g.fillRect(x, top, w, h);
        if (rnd() < 0.3) g.fillRect(x + w / 2 - 2, top - 18 - rnd() * 20, 4, 40);  // antenna
        if (rnd() < 0.2) { g.beginPath(); g.moveTo(x, top); g.lineTo(x + w / 2, top - 22); g.lineTo(x + w, top); g.fill(); }
        for (let wy = top + 10; wy < H - 10; wy += 13) {
          for (let wx = x + 7; wx < x + w - 9; wx += 11) {
            if (rnd() < winChance) collect.push({ x: wx, y: wy, on: rnd() < 0.8, warm: rnd() < 0.85, base });
          }
        }
        x += w + (base === "far" ? 3 : 1);
      }
    }
    function build() {
      W = cv.width = window.innerWidth;
      H = cv.height = window.innerHeight;
      seed = 11;
      sky = layer((g) => {
        const gr = g.createLinearGradient(0, 0, 0, H);
        gr.addColorStop(0, "#04060a"); gr.addColorStop(0.55, "#0a0e16"); gr.addColorStop(1, "#141015");
        g.fillStyle = gr; g.fillRect(0, 0, W + 80, H);
        const glow = g.createRadialGradient(W * 0.5, H * 1.05, 10, W * 0.5, H * 1.05, H * 0.8);
        glow.addColorStop(0, "rgba(201,140,60,0.20)"); glow.addColorStop(1, "transparent");
        g.fillStyle = glow; g.fillRect(0, 0, W + 80, H);
        for (let i = 0; i < 120; i++) {  // a few stars between the clouds
          g.fillStyle = `rgba(220,225,240,${0.15 + rnd() * 0.35})`;
          g.fillRect(rnd() * (W + 80), rnd() * H * 0.5, 1, 1);
        }
      });
      windows = [];
      const farWins = [], nearWins = [];
      far = layer((g) => city(g, "far", H * 0.12, H * 0.32, "#0b0e15", 0.06, farWins));
      near = layer((g) => city(g, "near", H * 0.06, H * 0.2, "#05070b", 0.12, nearWins));
      windows = farWins.concat(nearWins);
      drops = Array.from({ length: Math.round(W / 7) }, () => ({ x: Math.random() * W, y: Math.random() * H, l: 10 + Math.random() * 16, v: 9 + Math.random() * 8 }));
      clouds = Array.from({ length: 7 }, (_, i) => ({ x: Math.random() * W, y: H * (0.05 + Math.random() * 0.45), r: 160 + Math.random() * 260, v: 0.05 + Math.random() * 0.12, a: 0.05 + Math.random() * 0.07 }));
    }

    function spawnBats() {
      const n = 3 + Math.floor(Math.random() * 5), dir = Math.random() < 0.5 ? 1 : -1, y = H * (0.15 + Math.random() * 0.4);
      for (let i = 0; i < n; i++) {
        bats.push({ x: dir > 0 ? -40 - i * 35 : W + 40 + i * 35, y: y + (Math.random() - 0.5) * 60, v: dir * (2.2 + Math.random() * 1.2),
                    s: 0.12 + Math.random() * 0.12, ph: Math.random() * 6, wob: Math.random() * 6 });
      }
    }
    let nextBats = performance.now() + 4000;

    function drawSignal(t) {
      // the bat-signal drifts slowly across the clouds, its beam from a rooftop
      const sx = W * (0.72 + 0.08 * Math.sin(t / 9000)) - mx * 12;
      const sy = H * (0.2 + 0.04 * Math.cos(t / 7000)) - my * 8;
      const bx = W * 0.86 - mx * 25, by = H;
      const r = Math.min(W, H) * 0.11;
      ctx.save();
      const beam = ctx.createLinearGradient(bx, by, sx, sy);
      beam.addColorStop(0, "rgba(255,214,120,0.22)"); beam.addColorStop(1, "rgba(255,214,120,0.04)");
      ctx.fillStyle = beam;
      ctx.beginPath();
      ctx.moveTo(bx - 8, by); ctx.lineTo(sx - r * 0.95, sy); ctx.lineTo(sx + r * 0.95, sy); ctx.lineTo(bx + 8, by);
      ctx.fill();
      const glow = ctx.createRadialGradient(sx, sy, r * 0.2, sx, sy, r * 2.2);
      glow.addColorStop(0, "rgba(255,220,140,0.30)"); glow.addColorStop(1, "transparent");
      ctx.fillStyle = glow; ctx.fillRect(sx - r * 2.2, sy - r * 2.2, r * 4.4, r * 4.4);
      const disc = ctx.createRadialGradient(sx, sy, 0, sx, sy, r);
      disc.addColorStop(0, "rgba(255,232,160,0.85)"); disc.addColorStop(0.75, "rgba(255,214,120,0.55)"); disc.addColorStop(1, "rgba(255,214,120,0)");
      ctx.fillStyle = disc; ctx.beginPath(); ctx.arc(sx, sy, r, 0, Math.PI * 2); ctx.fill();
      ctx.translate(sx - r * 0.72, sy - r * 0.33);
      ctx.scale(r * 1.44 / 100, r * 1.44 / 100);
      ctx.fillStyle = "rgba(6,8,12,0.88)";
      ctx.fill(bat);
      ctx.restore();
    }

    function frame(t) {
      ctx.drawImage(sky, -mx * 6 - 40, 0);
      if (flash > 0) { ctx.fillStyle = `rgba(200,210,255,${flash})`; ctx.fillRect(0, 0, W, H); flash *= 0.86; if (flash < 0.01) flash = 0; }
      if (t > nextFlash) { flash = 0.35; nextFlash = t + 20000 + Math.random() * 30000; }
      for (const c of clouds) {  // slow fog clouds
        c.x += c.v; if (c.x - c.r > W) c.x = -c.r;
        const g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, c.r);
        g.addColorStop(0, `rgba(130,140,165,${c.a})`); g.addColorStop(1, "rgba(130,140,165,0)");
        ctx.fillStyle = g; ctx.fillRect(c.x - c.r, c.y - c.r, c.r * 2, c.r * 2);
      }
      drawSignal(t);
      if (t > nextBats) { spawnBats(); nextBats = t + 9000 + Math.random() * 14000; }
      ctx.fillStyle = "#020305";
      bats = bats.filter((b) => b.x > -80 && b.x < W + 80);
      for (const b of bats) {
        b.x += b.v; b.ph += 0.35; b.y += Math.sin(t / 300 + b.wob) * 0.4;
        ctx.save(); ctx.translate(b.x, b.y);
        ctx.scale(b.s * (b.v < 0 ? -1 : 1), b.s * (0.45 + 0.55 * Math.abs(Math.sin(b.ph))));
        ctx.translate(-50, -23); ctx.fill(bat); ctx.restore();
      }
      ctx.drawImage(far, -mx * 14 - 40, 0);
      for (const w of windows) {  // windows switch on and off now and then
        if (Math.random() < 0.0004) w.on = !w.on;
        if (!w.on) continue;
        const off = w.base === "far" ? -mx * 14 - 40 : -mx * 30 - 40;
        ctx.fillStyle = w.warm ? (w.base === "far" ? "rgba(255,196,110,0.35)" : "rgba(255,205,120,0.6)") : "rgba(160,200,255,0.45)";
        if (w.base === "near") continue;
        ctx.fillRect(w.x + off, w.y, 4, 5);
      }
      ctx.drawImage(near, -mx * 30 - 40, 0);
      for (const w of windows) {
        if (w.base !== "near" || !w.on) continue;
        ctx.fillStyle = w.warm ? "rgba(255,205,120,0.6)" : "rgba(160,200,255,0.45)";
        ctx.fillRect(w.x - mx * 30 - 40, w.y, 4, 5);
      }
      ctx.strokeStyle = "rgba(170,185,215,0.28)"; ctx.lineWidth = 1; ctx.beginPath();
      for (const d of drops) {
        ctx.moveTo(d.x, d.y); ctx.lineTo(d.x - 3, d.y + d.l);
        d.y += d.v; d.x -= 0.8;
        if (d.y > H) { d.y = -d.l; d.x = Math.random() * (W + 40); }
      }
      ctx.stroke();
    }

    build();
    window.addEventListener("resize", () => { clearTimeout(build.t); build.t = setTimeout(build, 150); });
    window.addEventListener("mousemove", (e) => { mx = e.clientX / W - 0.5; my = e.clientY / H - 0.5; });
    if (reduce) { frame(0); return; }
    let last = 0;
    (function loop(t) {
      if (!document.hidden && t - last > 33) { frame(t); last = t; }  // ~30 fps is plenty
      requestAnimationFrame(loop);
    })(0);
  }
  wallpaper();

  // ---------- small touches ----------
  const gate = document.querySelector("#gate .gate-content");
  if (gate) gate.insertAdjacentHTML("afterbegin", `<div class="g-gate-signal">${BAT}</div>`);

  const logoSvg = document.querySelector(".logo > svg");
  if (logoSvg) logoSvg.outerHTML = BAT.replace("<svg ", '<svg class="g-bat" ');

  // phone button + a menu button for small screens
  const nav = document.querySelector("header nav");
  if (nav && !nav.querySelector(".g-phone")) {
    const right = nav.querySelector(".nav-right") || nav;
    right.insertAdjacentHTML("afterbegin",
      `<a class="g-phone" href="/phone.html" title="Open on your phone" aria-label="Phone"><svg viewBox="0 0 24 24"><rect x="6" y="2" width="12" height="20" rx="3"/><circle cx="12" cy="18" r="1.2"/></svg></a>
       <button class="g-burger" aria-label="Menu"><span></span><span></span><span></span></button>`);
    nav.querySelector(".g-burger").onclick = () => document.body.classList.toggle("g-menu");
    document.querySelectorAll(".navlinks a").forEach((a) => a.addEventListener("click", () => document.body.classList.remove("g-menu")));
  }

  const here = location.pathname === "/" ? "/" : location.pathname;
  document.querySelectorAll(".navlinks a").forEach((a) => {
    if (a.getAttribute("href") === here) a.classList.add("g-here");
  });
})();
