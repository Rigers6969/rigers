// Gotham look: adds the bat-signal, skyline and rain to the page hero, a bat logo, and marks the open page in the menu.
(function () {
  const BAT = '<svg class="g-batpath" viewBox="0 0 100 46" aria-hidden="true"><path d="M50 8c-1.6 3.2-3.4 3.6-5.2 1.2L43 4.5 41.2 13C35 8.6 24.8 6.8 12 9.5c8.4 3.4 10.6 9 8.6 16 7-4.2 14.6-2.6 18.8 4 1.4-3.6 3.6-5.6 5.6-6.2 1.6 3.8 3.2 7.6 5 12.2 1.8-4.6 3.4-8.4 5-12.2 2 .6 4.2 2.6 5.6 6.2 4.2-6.6 11.8-8.2 18.8-4-2-7 .2-12.6 8.6-16C75.2 6.8 65 8.6 58.8 13L57 4.5l-1.8 4.7C53.4 11.6 51.6 11.2 50 8z"/></svg>';

  function skyline() {
    // random but stable buildings (seeded), with lit windows
    let seed = 7;
    const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280;
    const W = 1600, H = 120;
    let x = 0, back = "", front = "", wins = "";
    while (x < W) {
      const w = 40 + rnd() * 70, h = 40 + rnd() * 70;
      back += `<rect x="${x.toFixed(0)}" y="${(H - h - 10).toFixed(0)}" width="${w.toFixed(0)}" height="${(h + 10).toFixed(0)}"/>`;
      x += w + 4;
    }
    x = -20;
    while (x < W) {
      const w = 50 + rnd() * 90, h = 25 + rnd() * 60;
      const top = H - h;
      front += `<rect x="${x.toFixed(0)}" y="${top.toFixed(0)}" width="${w.toFixed(0)}" height="${h.toFixed(0)}"/>`;
      if (rnd() < 0.35) front += `<rect x="${(x + w / 2 - 2).toFixed(0)}" y="${(top - 14).toFixed(0)}" width="4" height="14"/>`;
      for (let wy = top + 8; wy < H - 8; wy += 11) {
        for (let wx = x + 6; wx < x + w - 8; wx += 10) {
          if (rnd() < 0.18) wins += `<rect x="${wx.toFixed(0)}" y="${wy.toFixed(0)}" width="4" height="5"/>`;
        }
      }
      x += w + 2;
    }
    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
      <g fill="#0d1017">${back}</g><g fill="#06080c">${front}</g><g fill="rgba(255,205,120,0.55)">${wins}</g></svg>`;
  }

  function rain(canvas) {
    const ctx = canvas.getContext("2d");
    let drops = [];
    function size() {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
      drops = Array.from({ length: Math.round(canvas.width / 9) }, () => ({
        x: Math.random() * canvas.width, y: Math.random() * canvas.height,
        l: 8 + Math.random() * 14, v: 6 + Math.random() * 6,
      }));
    }
    size();
    window.addEventListener("resize", size);
    (function tick() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = "rgba(170,185,210,0.35)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (const d of drops) {
        ctx.moveTo(d.x, d.y);
        ctx.lineTo(d.x - 2, d.y + d.l);
        d.y += d.v; d.x -= 0.6;
        if (d.y > canvas.height) { d.y = -d.l; d.x = Math.random() * canvas.width; }
      }
      ctx.stroke();
      if (!document.hidden) requestAnimationFrame(tick); else setTimeout(tick, 500);
    })();
  }

  const hero = document.querySelector(".videos-hero, .hero");
  if (hero) {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    hero.insertAdjacentHTML("afterbegin",
      `<div class="g-sky"></div><div class="g-clouds"></div><div class="g-beam"></div>
       <div class="g-signal">${BAT}</div><canvas class="g-rain"></canvas>
       <div class="g-skyline">${skyline()}</div>`);
    if (!reduce) rain(hero.querySelector(".g-rain"));
  }

  // bat-signal on the Dashboard's start screen
  const gate = document.querySelector("#gate .gate-content");
  if (gate) gate.insertAdjacentHTML("afterbegin", `<div class="g-gate-signal">${BAT}</div>`);

  // bat logo in the menu
  const logoSvg = document.querySelector(".logo > svg");
  if (logoSvg) logoSvg.outerHTML = BAT.replace('class="g-batpath"', 'class="g-bat"');

  // mark the page you're on
  const here = location.pathname === "/" ? "/" : location.pathname;
  document.querySelectorAll(".navlinks a").forEach((a) => {
    if (a.getAttribute("href") === here) a.classList.add("g-here");
  });
})();
