"""Voice Generator - paste text, pick a voice, get an MP3.

Standalone: just this folder (voice_engine.py + this file). Every MP3 is
saved in the output/ folder next to this file.

Run it by double-clicking start.bat, or:
    python voice_app.py
then open http://localhost:5002
"""
from __future__ import annotations

import re
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from voice_engine import VOICES, VoiceSynthesisError, synthesize_speech

APP_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = APP_DIR / "output"
PORT = 5002
MAX_CHARS = 200_000

app = Flask(__name__)
jobs: dict[str, dict] = {}


def file_name_for(text: str) -> str:
    words = re.sub(r"[^a-zA-Z0-9 ]+", "", text).split()[:6]
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{'-'.join(words).lower() or 'voice'}.mp3"


def run_job(job_id: str, text: str, voice: str) -> None:
    job = jobs[job_id]
    try:
        name = file_name_for(text)
        synthesize_speech(text, voice, OUTPUT_DIR / name, progress=lambda m: job.update(progress=m))
        job.update(status="done", file=name, url=f"/output/{name}")
    except VoiceSynthesisError as exc:
        job.update(status="error", error=f"{exc} - check your internet connection (the voices come from Microsoft's servers).")
    except Exception as exc:
        job.update(status="error", error=str(exc))


@app.route("/")
def index():
    return PAGE


@app.route("/api/voices")
def voices():
    return jsonify({"voices": [{"label": label, "id": vid} for label, vid in VOICES.items()]})


@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()
    voice = str(data.get("voice", ""))
    if not text:
        return jsonify({"error": "Paste some text first."}), 400
    if len(text) > MAX_CHARS:
        return jsonify({"error": f"That's too long - keep it under {MAX_CHARS:,} characters."}), 400
    if voice not in VOICES.values():
        return jsonify({"error": "Pick a voice."}), 400
    job_id = uuid.uuid4().hex[:10]
    jobs[job_id] = {"status": "running", "progress": "Starting..."}
    threading.Thread(target=run_job, args=(job_id, text, voice), daemon=True).start()
    return jsonify({"job_id": job_id}), 202


@app.route("/api/jobs/<job_id>")
def job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "No such job."}), 404
    return jsonify(job)


@app.route("/api/history")
def history():
    files = sorted(OUTPUT_DIR.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)[:30] if OUTPUT_DIR.exists() else []
    return jsonify({"files": [{"file": p.name, "url": f"/output/{p.name}"} for p in files]})


@app.route("/output/<name>")
def output_file(name):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.mp3", name) or not (OUTPUT_DIR / name).exists():
        return jsonify({"error": "Not found."}), 404
    return send_from_directory(OUTPUT_DIR, name)


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Voice Generator</title>
<style>
  :root { --bg:#12141a; --panel:#1c1f27; --line:#2c303b; --text:#e9e9ee; --dim:#9a9fad; --gold:#c9a24b; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family: system-ui, "Segoe UI", sans-serif; }
  .wrap { max-width: 820px; margin: 0 auto; padding: 28px 16px 60px; }
  h1 { margin: 0 0 4px; font-size: 28px; }
  h1 span { color: var(--gold); }
  .sub { color: var(--dim); margin: 0 0 22px; }
  .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 18px; margin-bottom: 18px; }
  textarea { width: 100%; min-height: 260px; resize: vertical; background:#0f1116; color: var(--text); border:1px solid var(--line); border-radius: 8px; padding: 12px; font-size: 15px; line-height: 1.5; }
  .row { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 14px; }
  select { flex: 1 1 220px; background:#0f1116; color: var(--text); border:1px solid var(--line); border-radius: 8px; padding: 10px; font-size: 14px; }
  button { background: var(--gold); color: #1a1a1a; border: 0; border-radius: 8px; padding: 11px 24px; font-weight: 700; font-size: 15px; cursor: pointer; }
  button:disabled { opacity: .5; cursor: wait; }
  .label { font-size: 13px; color: var(--dim); margin-bottom: 6px; }
  .count { float: right; }
  .status { margin-top: 12px; color: var(--dim); min-height: 20px; }
  .error { color: #ff7a6b; }
  audio { width: 100%; margin-top: 10px; }
  a { color: var(--gold); }
  .hist { list-style: none; padding: 0; margin: 0; }
  .hist li { display: flex; gap: 10px; align-items: center; padding: 8px 0; border-top: 1px solid var(--line); flex-wrap: wrap; }
  .hist li:first-child { border-top: 0; }
  .hist span { flex: 1 1 220px; color: var(--dim); font-size: 13px; word-break: break-all; }
  .hist audio { flex: 2 1 240px; margin: 0; height: 36px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Voice <span>Generator</span></h1>
  <p class="sub">Paste your text, pick a voice, click Generate. Every MP3 is saved in the <code>output</code> folder.</p>

  <div class="panel">
    <div class="label">Text <span class="count" id="count">0 words</span></div>
    <textarea id="text" placeholder="Paste the text you want narrated..."></textarea>
    <div class="row">
      <select id="voice"></select>
      <button id="go">Generate</button>
    </div>
    <div class="status" id="status"></div>
    <div id="result"></div>
  </div>

  <div class="panel">
    <div class="label">Recent</div>
    <ul class="hist" id="history"></ul>
  </div>
</div>
<script>
const $ = (id) => document.getElementById(id);
function esc(s) { const d = document.createElement("div"); d.innerText = s; return d.innerHTML; }

async function loadVoices() {
  const data = await (await fetch("/api/voices")).json();
  $("voice").innerHTML = data.voices.map((v) => `<option value="${esc(v.id)}">${esc(v.label)}</option>`).join("");
}

async function loadHistory() {
  const data = await (await fetch("/api/history")).json();
  $("history").innerHTML = data.files.length
    ? data.files.map((f) => `<li><span>${esc(f.file)}</span><audio controls preload="none" src="${f.url}"></audio><a href="${f.url}" download>Download</a></li>`).join("")
    : "<li><span>Nothing yet.</span></li>";
}

$("text").oninput = () => {
  const n = $("text").value.trim().split(/\s+/).filter(Boolean).length;
  $("count").innerText = `${n} words · about ${Math.max(1, Math.round(n / 150))} min`;
};

$("go").onclick = async () => {
  const text = $("text").value.trim();
  if (!text) { $("status").innerHTML = '<span class="error">Paste some text first.</span>'; return; }
  $("go").disabled = true;
  $("result").innerHTML = "";
  $("status").innerText = "Starting...";
  try {
    const resp = await fetch("/api/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, voice: $("voice").value }) });
    const data = await resp.json();
    if (!resp.ok) { $("status").innerHTML = `<span class="error">${esc(data.error || "Failed.")}</span>`; $("go").disabled = false; return; }
    const timer = setInterval(async () => {
      const job = await (await fetch(`/api/jobs/${data.job_id}`)).json();
      if (job.status === "running") { $("status").innerText = job.progress || "Working..."; return; }
      clearInterval(timer);
      $("go").disabled = false;
      if (job.status === "done") {
        $("status").innerText = "Done - saved as " + job.file;
        $("result").innerHTML = `<audio controls autoplay src="${job.url}"></audio><p><a href="${job.url}" download>Download MP3</a></p>`;
        loadHistory();
      } else {
        $("status").innerHTML = `<span class="error">${esc(job.error || "Failed.")}</span>`;
      }
    }, 1200);
  } catch (e) {
    $("status").innerHTML = '<span class="error">Couldn\'t reach the app - is it still running?</span>';
    $("go").disabled = false;
  }
};

loadVoices();
loadHistory();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"Voice Generator running - open http://localhost:{PORT}")
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
