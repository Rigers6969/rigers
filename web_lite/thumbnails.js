const TIMEZONE = "Europe/Tirane";
function tickClock() {
  document.getElementById("header-clock").innerText = new Intl.DateTimeFormat("en-GB", {
    timeZone: TIMEZONE, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(new Date());
}
tickClock();
setInterval(tickClock, 1000);

function showThumbnail(url) {
  document.getElementById("thumb-preview").src = url;
  document.getElementById("thumb-download-link").href = `${url}?download=1`;
  document.getElementById("thumb-preview-wrap").classList.remove("hidden");
}

document.getElementById("thumb-generate-btn").addEventListener("click", async () => {
  const btn = document.getElementById("thumb-generate-btn");
  const progressEl = document.getElementById("thumb-progress");
  const headline = document.getElementById("thumb-headline").value.trim();
  if (!headline) {
    progressEl.innerText = "Enter a headline first.";
    return;
  }

  btn.disabled = true;
  progressEl.innerText = "Generating...";

  const aspect = document.getElementById("thumb-aspect").value;
  const resp = await fetch("/api/thumbnail/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      headline,
      kicker: document.getElementById("thumb-kicker").value.trim(),
      tag: document.getElementById("thumb-tag").value.trim(),
      brand: document.getElementById("thumb-brand").value.trim(),
      aspect,
    }),
  });
  const data = await resp.json();
  btn.disabled = false;

  if (!resp.ok) {
    progressEl.innerText = data.error || "Failed to generate.";
    return;
  }
  progressEl.innerText = "Done.";
  showThumbnail(data.thumbnail_url);
});
