// TOP G look: a live black-and-gold wallpaper behind every page (falling gold money code, gold dust,
// a slow-pulsing crown), the crown logo, and the open page marked in the menu.
(function () {
  const CROWN_PATH = "M8 38 L4 10 L26 26 L50 4 L74 26 L96 10 L92 38 Z M8 42 H92 V48 H8 Z";
  const BAT = `<svg viewBox="0 0 100 50" aria-hidden="true"><path d="${CROWN_PATH}"/></svg>`;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- live wallpaper ----------
  function wallpaper() {
    const cv = document.createElement("canvas");
    cv.id = "g-wall";
    document.body.prepend(cv);
    document.body.classList.add("g-live");
    const ctx = cv.getContext("2d");
    const crown = new Path2D(CROWN_PATH);
    const SYMBOLS = "$0123456789$€$";
    let W, H, cols = [], dust = [], mx = 0, my = 0;

    function build() {
      W = cv.width = window.innerWidth;
      H = cv.height = window.innerHeight;
      const n = Math.round(W / 26);
      cols = Array.from({ length: n }, (_, i) => ({ x: i * 26 + 8, y: Math.random() * H, v: 0.6 + Math.random() * 1.6,
                                                     len: 8 + Math.floor(Math.random() * 18), on: Math.random() < 0.55 }));
      dust = Array.from({ length: Math.round(W / 14) }, () => ({ x: Math.random() * W, y: Math.random() * H, r: 0.6 + Math.random() * 1.8,
                                                               v: 0.15 + Math.random() * 0.5, a: 0.15 + Math.random() * 0.5 }));
    }

    function frame(t) {
      const g = ctx.createLinearGradient(0, 0, 0, H);
      g.addColorStop(0, "#040404"); g.addColorStop(0.6, "#0a0806"); g.addColorStop(1, "#140f06");
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
      const glow = ctx.createRadialGradient(W * (0.7 - mx * 0.05), H * 0.3, 10, W * 0.7, H * 0.3, Math.max(W, H) * 0.7);
      glow.addColorStop(0, "rgba(232,180,70,0.14)"); glow.addColorStop(1, "transparent");
      ctx.fillStyle = glow; ctx.fillRect(0, 0, W, H);
      // falling gold money code
      ctx.font = "15px 'JetBrains Mono', Consolas, monospace";
      for (const c of cols) {
        if (!c.on) continue;
        for (let k = 0; k < c.len; k++) {
          const y = c.y - k * 18;
          if (y < -20 || y > H + 20) continue;
          const a = k === 0 ? 0.55 : 0.22 * (1 - k / c.len);
          ctx.fillStyle = k === 0 ? `rgba(255,230,160,${a})` : `rgba(232,180,70,${a})`;
          ctx.fillText(SYMBOLS[(Math.floor(t / 120) + k * 7 + c.x) % SYMBOLS.length], c.x - mx * 10, y);
        }
        c.y += c.v;
        if (c.y - c.len * 18 > H) { c.y = -20; c.on = Math.random() < 0.6; }
      }
      // big slow-pulsing crown
      const pulse = 0.05 + 0.03 * Math.sin(t / 1800);
      const s = Math.min(W, H) * 0.0042;
      ctx.save();
      ctx.translate(W * 0.72 - 50 * s - mx * 20, H * 0.32 - 25 * s - my * 12);
      ctx.scale(s, s);
      ctx.shadowColor = "rgba(255,200,90,0.6)"; ctx.shadowBlur = 40;
      ctx.fillStyle = `rgba(232,180,70,${pulse})`; ctx.fill(crown);
      ctx.restore();
      // rising gold dust
      for (const d of dust) {
        d.y -= d.v; d.x += Math.sin((t / 1000) + d.y / 50) * 0.15;
        if (d.y < -5) { d.y = H + 5; d.x = Math.random() * W; }
        ctx.fillStyle = `rgba(255,214,120,${d.a})`;
        ctx.beginPath(); ctx.arc(d.x - mx * 6, d.y, d.r, 0, Math.PI * 2); ctx.fill();
      }
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
