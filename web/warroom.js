(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  async function api(url, body) {
    const r = await fetch(url, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || "Request failed");
    return d;
  }
  const LINES = ["Nobody is coming to save you.", "Discipline beats motivation.", "Your competition is working right now.",
    "Comfort is the enemy.", "Excuses don't pay.", "Do it tired. Do it anyway.", "Train. Work. Learn. Repeat.",
    "Small daily wins. Big future.", "Talk less. Post more.", "Be the hardest worker in the room."];
  let st = null, photos = [], pi = 0;

  function render(d) {
    st = d;
    const n = d.done.filter(Boolean).length;
    $("wr-streak").textContent = d.streak;
    $("wr-count").textContent = `Today: ${n} / ${d.tasks.length}` + (n === d.tasks.length ? "  - DONE. That's a Top G day." : "");
    $("wr-bar").style.width = `${(100 * n) / d.tasks.length}%`;
    $("wr-tasks").innerHTML = d.tasks.map((t, i) => `<div class="wr-task${d.done[i] ? " done" : ""}" data-i="${i}"><div class="wr-box"></div><span>${esc(t)}</span></div>`).join("");
    document.querySelectorAll(".wr-task").forEach((el) => el.onclick = async () => {
      const i = +el.dataset.i;
      render(await api("/api/topg/check", { i, on: !st.done[i] }));
    });
    if (JSON.stringify(photos) !== JSON.stringify(d.photos)) {
      photos = d.photos;
      const box = $("wr-photo");
      box.querySelectorAll("img").forEach((x) => x.remove());
      $("wr-empty").classList.toggle("hidden", photos.length > 0);
      photos.forEach((p, i) => box.insertAdjacentHTML("afterbegin", `<img src="/topg-photos/${encodeURIComponent(p)}" alt="" class="${i === 0 ? "on" : ""}">`));
    }
  }
  setInterval(() => {  // rotate photo + line
    const imgs = [...document.querySelectorAll("#wr-photo img")];
    if (imgs.length > 1) { imgs.forEach((x) => x.classList.remove("on")); pi = (pi + 1) % imgs.length; imgs[pi].classList.add("on"); }
    $("wr-line").textContent = LINES[Math.floor(Math.random() * LINES.length)];
  }, 6000);
  $("wr-quote").textContent = LINES[new Date().getDate() % LINES.length] + " Do the work.";
  $("wr-edit-btn").onclick = () => { $("wr-edit").classList.toggle("hidden"); $("wr-text").value = st.tasks.join("\n"); };
  $("wr-save").onclick = async () => {
    try { render(await api("/api/topg/tasks", { tasks: $("wr-text").value.split("\n") })); $("wr-edit").classList.add("hidden"); }
    catch (e) { alert(e.message); }
  };
  api("/api/topg").then(render).catch(() => {});
})();
