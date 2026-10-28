// Phone page: switch phone mode, show the address, QR code and PIN.
(function () {
  const $ = (id) => document.getElementById(id);
  let st = null;
  async function api(body) {
    const r = await fetch("/api/phone", body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || "Request failed");
    return d;
  }
  function render() {
    $("ph-switch").classList.toggle("on", st.enabled);
    $("ph-state").textContent = st.enabled ? "Phone mode is on" : "Phone mode is off";
    $("ph-sub").textContent = st.enabled ? "Your phone can open Wayne Factory with the PIN." : "Only this PC can open Wayne Factory.";
    $("ph-restart").classList.toggle("hidden", st.enabled === st.running_open);
    $("ph-connect").style.opacity = st.enabled ? 1 : 0.35;
    $("ph-url").textContent = st.url;
    $("ph-pin").textContent = st.pin;
    const others = (st.urls || []).filter((u) => u !== st.url);
    $("ph-more").innerHTML = others.length ? "If that one doesn't open, try: " + others.map((u) => `<b>${u}</b>`).join(" &middot; ") : "";
    $("ph-qr").innerHTML = "";
    if (window.qrcode) {  // web/qrcode.js (MIT, Kazuhiko Arase) - works without internet
      const qr = qrcode(0, "M");
      qr.addData(st.url);
      qr.make();
      $("ph-qr").innerHTML = qr.createSvgTag({ cellSize: 6, margin: 0 });
    }
  }
  async function load(body) {
    try { st = await api(body); render(); }
    catch (e) { document.querySelector(".wrap .panel").innerHTML = `<p class="hint">${e.message}</p>`; }
  }
  $("ph-switch").onclick = () => load({ enabled: !st.enabled });
  $("ph-new").onclick = () => { if (confirm("Make a new PIN? Phones will have to type it again.")) load({ new_pin: true }); };
  load();
})();
