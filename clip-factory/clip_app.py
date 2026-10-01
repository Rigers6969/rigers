"""Clip Factory - turns one long video into up to 100 vertical Shorts.

1. Whisper writes down every word (with its exact time).
2. Ollama rates every possible moment for how viral it could be.
3. The best moments are cut to 1080x1920 with word-by-word captions,
   best first - clip 1 can be downloaded while 2, 3, 4... are still being made.

Run it by double-clicking start.bat, or:
    python clip_app.py
then open http://localhost:5003
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import zipfile
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

import moments
import renderer
import transcriber

APP_DIR = Path(__file__).resolve().parent
INPUT_DIR = APP_DIR / "input"
OUTPUT_DIR = APP_DIR / "output"
PORT = 5003
DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
if not DEFAULT_HOST.startswith("http"):
    DEFAULT_HOST = "http://" + DEFAULT_HOST
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".flv", ".wmv", ".ts"}
RUN_ID_RE = re.compile(r"^\d{8}-\d{6}-[a-z0-9-]{0,40}$")
CLIP_FILE_RE = re.compile(r"^clip_\d{3}\.(mp4|jpg)$")
MAX_CLIPS = 100

app = Flask(__name__)
runs: dict[str, dict] = {}  # runs started since the app opened (the rest are read from disk)
state_lock = threading.Lock()
active_run: dict = {"id": None}


# ---------- helpers ----------

def slugify(text: str, limit: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit].strip("-") or "video"


def safe_filename(text: str, limit: int = 60) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", text).strip(" .")
    return text[:limit].strip() or "clip"


def fmt_time(seconds: float) -> str:
    seconds = int(max(0, seconds))
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 else f"{seconds // 60}:{seconds % 60:02d}"


def save_run(run: dict) -> None:
    path = OUTPUT_DIR / run["id"] / "run.json"
    tmp = path.with_suffix(".tmp")
    with state_lock:
        tmp.write_text(json.dumps(run, indent=2), encoding="utf-8")
        os.replace(tmp, path)


def load_run(run_id: str) -> dict | None:
    if not RUN_ID_RE.match(run_id or ""):
        return None
    if run_id in runs:
        return runs[run_id]
    path = OUTPUT_DIR / run_id / "run.json"
    if not path.exists():
        return None
    try:
        run = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if run.get("status") == "running":  # the app was closed in the middle of it
        run["status"] = "stopped"
        run["message"] = f"Stopped when the app was closed - {len(run.get('clips', []))} clip(s) were finished."
    return run


def public(run: dict) -> dict:
    out = {k: v for k, v in list(run.items()) if k not in ("source", "cancel")}
    out["clips"] = [
        dict(c, url=f"/files/{run['id']}/{c['file']}", download=f"/files/{run['id']}/{c['file']}?dl=1",
             poster=f"/files/{run['id']}/{c['poster']}" if c.get("poster") else None)
        for c in run.get("clips", [])
    ]
    return out


# ---------- the pipeline ----------

def run_pipeline(run: dict) -> None:
    s = run["settings"]
    source = Path(run["source"])
    cancelled = lambda: run.get("cancel", False)  # noqa: E731
    run_dir = OUTPUT_DIR / run["id"]

    def update(stage=None, message=None, percent=None, save=False):
        if stage is not None:
            run["stage"] = stage
        if message is not None:
            run["message"] = message
        if percent is not None:
            run["percent"] = round(percent, 1)
        if save:
            save_run(run)

    try:
        renderer.require_ffmpeg()
        info = renderer.probe(source)
        run["video_duration"] = info["duration"]
        if info["duration"] and info["duration"] < s["min_len"]:
            raise renderer.RenderError(f"This video is only {info['duration']:.0f}s long - shorter than the minimum clip length.")

        # 1. transcript (0-35%)
        update("transcribe", "Getting ready to transcribe...", 0, save=True)
        words = transcriber.transcribe(
            source, s["whisper"], cancelled=cancelled,
            progress=lambda m, p: update(message=m, percent=p * 0.35),
        )

        # 2. moments (35-50%)
        update("moments", "Looking for the best moments...", 35, save=True)
        sentences = moments.split_sentences(words, s["max_len"])
        candidates = moments.make_candidates(sentences, s["min_len"], s["max_len"])
        if not candidates:
            raise renderer.RenderError(
                f"Couldn't find any {s['min_len']}-{s['max_len']}s stretch of speech - try a wider clip length."
            )
        model = s["model"]
        use_ai = s["use_ai"]
        if use_ai:
            try:
                model = moments.check_ollama(s["host"], s["model"])
            except moments.OllamaUnavailable as exc:
                use_ai = False
                run["warning"] = f"{exc}. The built-in scorer picked the clips instead."
        batches = max(1, -(-len(candidates) // moments.BATCH_SIZE))
        done_batches = {"n": 0}

        def scoring_progress(msg):
            m = re.search(r"batch (\d+) of", msg)
            if m:
                done_batches["n"] = int(m.group(1)) - 1
            update(message=msg, percent=35 + 15 * done_batches["n"] / batches)

        stats = moments.score_candidates(candidates, use_ai, s["host"], model, progress=scoring_progress, cancelled=cancelled)
        if cancelled():
            raise transcriber.Cancelled()
        if use_ai and stats["ai_error"] and stats["fallback"]:
            run["warning"] = (f"Ollama had a problem ({stats['ai_error']}), so {stats['fallback']} of "
                              f"{len(candidates)} moments were rated by the built-in scorer.")
        run["stats"] = dict(stats, candidates=len(candidates), model=model if use_ai else None)
        picks = moments.pick_best(candidates, s["count"])
        run["planned"] = len(picks)
        if len(picks) < s["count"]:
            run["note"] = (f"This video only has room for {len(picks)} separate clips of {s['min_len']}-{s['max_len']}s "
                           f"(they never overlap), so you'll get {len(picks)} instead of {s['count']}.")
        update("render", f"Found {len(picks)} moments - cutting clip 1...", 50, save=True)

        # 3. render, best first (50-100%) - each clip is downloadable as soon as it's finished
        duration = info["duration"] or (words[-1]["end"] + 1)
        failures_in_a_row = 0
        for n, c in enumerate(picks, start=1):
            if cancelled():
                raise transcriber.Cancelled()
            update(message=f"Cutting clip {n} of {len(picks)}...", percent=50 + 50 * (n - 1) / len(picks))
            start = max(0.0, c["start"] - 0.15)
            end = min(duration, c["end"] + 0.4)
            name = f"clip_{n:03d}"
            began = time.time()
            try:
                renderer.render_clip(
                    source, start, end, words, c["title"] if s["show_title"] else "",
                    s["layout"], s["captions"], run_dir / f"{name}.mp4", run_dir / f"{name}.jpg",
                    has_audio=info["has_audio"], cancelled=cancelled,
                )
            except renderer.Cancelled:
                raise transcriber.Cancelled()
            except renderer.RenderError as exc:
                failures_in_a_row += 1
                run["failed"].append({"n": n, "error": str(exc)[:500]})
                if failures_in_a_row >= 3:
                    raise
                continue
            failures_in_a_row = 0
            run["clips"].append({
                "n": n, "file": f"{name}.mp4",
                "poster": f"{name}.jpg" if (run_dir / f"{name}.jpg").exists() else None,
                "title": c["title"], "score": round(c["score"], 1), "rated_by": c["source"],
                "start": round(start, 2), "end": round(end, 2), "length": round(end - start, 1),
                "at": f"{fmt_time(start)} - {fmt_time(end)}", "text": c["text"],
                "download_name": f"{n:03d} - {safe_filename(c['title'])}.mp4",
                "render_seconds": round(time.time() - began, 1),
            })
            save_run(run)

        made = len(run["clips"])
        run["status"] = "done"
        update("done", f"Done - {made} clip{'s' if made != 1 else ''} ready.", 100)
    except transcriber.Cancelled:
        run["status"] = "cancelled"
        update("done", f"Stopped - {len(run['clips'])} clip(s) were finished before that.")
    except (renderer.RenderError, transcriber.TranscriptionError) as exc:
        run["status"] = "error"
        run["error"] = str(exc)
        update(message="Something went wrong.")
    except Exception as exc:  # never leave a run stuck on "running"
        run["status"] = "error"
        run["error"] = f"Unexpected problem: {exc}"
        update(message="Something went wrong.")
    finally:
        run["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_run(run)
        with state_lock:
            if active_run["id"] == run["id"]:
                active_run["id"] = None


# ---------- routes ----------

@app.route("/")
def index():
    return PAGE


@app.route("/api/status")
def status():
    try:
        renderer.require_ffmpeg()
        ffmpeg_error = None
    except renderer.RenderError as exc:
        ffmpeg_error = str(exc)
    return jsonify({"ffmpeg_error": ffmpeg_error, "active": active_run["id"], "default_host": DEFAULT_HOST,
                    "input_folder": str(INPUT_DIR)})


@app.route("/api/inputs")
def inputs():
    files = sorted(
        (p for p in INPUT_DIR.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS),
        key=lambda p: p.stat().st_mtime, reverse=True,
    ) if INPUT_DIR.exists() else []
    return jsonify({"files": [{"name": p.name, "size_mb": round(p.stat().st_size / 1e6)} for p in files]})


@app.route("/api/models")
def models():
    host = request.args.get("host") or DEFAULT_HOST
    names = moments.list_models(host)
    return jsonify({"reachable": bool(names) or _ollama_up(host), "models": names})


def _ollama_up(host: str) -> bool:
    try:
        moments.requests.get(f"{host.rstrip('/')}/api/tags", timeout=3).raise_for_status()
        return True
    except Exception:
        return False


@app.route("/api/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "No file was sent."}), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in VIDEO_EXTS:
        return jsonify({"error": f"That doesn't look like a video ({ext or 'no extension'})."}), 400
    INPUT_DIR.mkdir(exist_ok=True)
    name = f"{safe_filename(Path(f.filename).stem, 80)}{ext}"
    target = INPUT_DIR / name
    if target.exists():
        name = f"{Path(name).stem}-{time.strftime('%H%M%S')}{ext}"
        target = INPUT_DIR / name
    f.save(target)
    return jsonify({"name": name})


def _int(data, key, default, lo, hi):
    try:
        return max(lo, min(hi, int(float(data.get(key, default)))))
    except (TypeError, ValueError):
        return default


@app.route("/api/start", methods=["POST"])
def start():
    data = request.get_json(silent=True) or {}
    path_text = str(data.get("path") or "").strip().strip('"').strip("'").strip()
    if path_text:
        source = Path(os.path.expandvars(os.path.expanduser(path_text)))
        if not source.is_file():
            return jsonify({"error": f"Can't find that file: {path_text}"}), 400
    else:
        name = str(data.get("input") or "")
        source = INPUT_DIR / name
        if not name or "/" in name or "\\" in name or not source.is_file():
            return jsonify({"error": "Pick a video first."}), 400
    if source.suffix.lower() not in VIDEO_EXTS:
        return jsonify({"error": f"That doesn't look like a video file ({source.suffix or 'no extension'})."}), 400

    min_len = _int(data, "min_len", 20, 5, 170)
    max_len = _int(data, "max_len", 60, 10, 180)
    if max_len < min_len + 5:
        return jsonify({"error": "The longest clip length must be at least 5 seconds more than the shortest."}), 400
    host = str(data.get("host") or DEFAULT_HOST).strip()
    if not host.startswith("http"):
        host = "http://" + host
    settings = {
        "count": _int(data, "count", 10, 1, MAX_CLIPS),
        "min_len": min_len, "max_len": max_len,
        "layout": data.get("layout") if data.get("layout") in renderer.LAYOUTS else "crop",
        "captions": data.get("captions") if data.get("captions") in renderer.CAPTION_STYLES else "highlight",
        "show_title": bool(data.get("show_title", True)),
        "whisper": data.get("whisper") if data.get("whisper") in ("base", "small", "medium") else "base",
        "use_ai": bool(data.get("use_ai", True)),
        "host": host, "model": str(data.get("model") or "llama3").strip() or "llama3",
    }

    with state_lock:
        if active_run["id"]:
            return jsonify({"error": "Another video is still being cut - wait for it to finish or press Stop."}), 409
        run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{slugify(source.stem)}"
        while (OUTPUT_DIR / run_id).exists():
            time.sleep(1)
            run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{slugify(source.stem)}"
        (OUTPUT_DIR / run_id).mkdir(parents=True)
        active_run["id"] = run_id
    run = {
        "id": run_id, "video": source.name, "source": str(source.resolve()), "settings": settings,
        "status": "running", "stage": "start", "message": "Starting...", "percent": 0,
        "clips": [], "planned": None, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        # every key exists from the start: the page reads this dict while the job thread fills it in
        "cancel": False, "warning": None, "note": None, "error": None, "failed": [], "stats": None,
        "video_duration": None, "finished_at": None,
    }
    runs[run_id] = run
    save_run(run)
    threading.Thread(target=run_pipeline, args=(run,), daemon=True).start()
    return jsonify({"id": run_id}), 202


@app.route("/api/runs")
def list_runs():
    items = []
    if OUTPUT_DIR.exists():
        for d in sorted(OUTPUT_DIR.iterdir(), reverse=True):
            run = load_run(d.name) if d.is_dir() else None
            if run:
                items.append({k: run.get(k) for k in ("id", "video", "status", "created", "planned")}
                             | {"made": len(run.get("clips", []))})
    return jsonify({"runs": items[:50]})


@app.route("/api/runs/<run_id>")
def get_run(run_id):
    run = load_run(run_id)
    if not run:
        return jsonify({"error": "Not found."}), 404
    return jsonify(public(run))


@app.route("/api/runs/<run_id>/cancel", methods=["POST"])
def cancel(run_id):
    run = runs.get(run_id)
    if not run or run.get("status") != "running":
        return jsonify({"error": "That isn't running."}), 400
    run["cancel"] = True
    run["message"] = "Stopping..."
    return jsonify({"ok": True})


@app.route("/api/runs/<run_id>/zip")
def zip_run(run_id):
    run = load_run(run_id)
    if not run or not run.get("clips"):
        return jsonify({"error": "No finished clips yet."}), 404
    run_dir = OUTPUT_DIR / run_id
    zip_path = run_dir / "all_clips.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:  # mp4 is already compressed
        for c in run["clips"]:
            if (run_dir / c["file"]).exists():
                zf.write(run_dir / c["file"], c.get("download_name") or c["file"])
        zf.writestr("titles.txt", "\n".join(f"{c['n']:03d}  {c['title']}" for c in run["clips"]))
    return send_file(zip_path, as_attachment=True, download_name=f"{safe_filename(Path(run['video']).stem)} - clips.zip")


@app.route("/api/runs/<run_id>/open-folder", methods=["POST"])
def open_folder(run_id):
    run_dir = OUTPUT_DIR / run_id
    if not RUN_ID_RE.match(run_id) or not run_dir.is_dir():
        return jsonify({"error": "Not found."}), 404
    try:
        if os.name == "nt":
            os.startfile(run_dir)  # noqa: S606 - opens File Explorer on this PC
        else:
            subprocess.Popen(["xdg-open", str(run_dir)])
    except Exception as exc:
        return jsonify({"error": str(exc), "path": str(run_dir)}), 500
    return jsonify({"ok": True, "path": str(run_dir)})


@app.route("/files/<run_id>/<name>")
def run_file(run_id, name):
    if not RUN_ID_RE.match(run_id) or not CLIP_FILE_RE.match(name):
        return jsonify({"error": "Not found."}), 404
    run_dir = OUTPUT_DIR / run_id
    if not (run_dir / name).exists():
        return jsonify({"error": "Not found."}), 404
    if request.args.get("dl"):
        run = load_run(run_id) or {}
        clip = next((c for c in run.get("clips", []) if c["file"] == name), {})
        return send_from_directory(run_dir, name, as_attachment=True, download_name=clip.get("download_name") or name)
    return send_from_directory(run_dir, name, max_age=0 if name.endswith(".jpg") else None)


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Clip Factory</title>
<style>
  :root { --bg:#111318; --panel:#1b1e26; --line:#2c303b; --text:#ececf1; --dim:#9a9fad; --accent:#ffd400; --ok:#5fd38d; --err:#ff7a6b; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family: system-ui, "Segoe UI", sans-serif; }
  .wrap { max-width: 1100px; margin: 0 auto; padding: 26px 16px 70px; }
  h1 { margin: 0 0 4px; font-size: 30px; }
  h1 span { color: var(--accent); }
  h2 { font-size: 17px; margin: 0 0 12px; }
  .sub { color: var(--dim); margin: 0 0 22px; }
  .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 18px; margin-bottom: 18px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; }
  label { display: block; font-size: 13px; color: var(--dim); margin-bottom: 5px; }
  input[type=text], input[type=number], select { width: 100%; background:#0d0f13; color: var(--text); border:1px solid var(--line); border-radius: 8px; padding: 10px; font-size: 14px; }
  .check { display: flex; align-items: center; gap: 8px; color: var(--text); font-size: 14px; margin-top: 8px; }
  .row { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
  .or { color: var(--dim); font-size: 13px; margin: 12px 0 8px; }
  button, .btn { background: var(--accent); color: #111; border: 0; border-radius: 8px; padding: 10px 18px; font-weight: 700; font-size: 14px; cursor: pointer; text-decoration: none; display: inline-block; }
  button.big { font-size: 17px; padding: 13px 30px; }
  button.ghost, .btn.ghost { background: transparent; color: var(--text); border: 1px solid var(--line); font-weight: 600; }
  button:disabled { opacity: .45; cursor: not-allowed; }
  .bar { height: 10px; background: #0d0f13; border-radius: 6px; overflow: hidden; margin: 12px 0 8px; }
  .bar div { height: 100%; width: 0; background: var(--accent); transition: width .4s; }
  .msg { color: var(--dim); min-height: 20px; }
  .error { color: var(--err); white-space: pre-wrap; }
  .warn { color: #ffb84d; margin-top: 8px; }
  .note { color: var(--dim); margin-top: 8px; }
  .clips { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 14px; }
  .card { background: #14161c; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; display: flex; flex-direction: column; }
  .card .media { position: relative; aspect-ratio: 9/16; background: #000; cursor: pointer; }
  .card .media img, .card .media video { width: 100%; height: 100%; object-fit: cover; display: block; }
  .card .num { position: absolute; top: 8px; left: 8px; background: var(--accent); color: #111; font-weight: 800; border-radius: 6px; padding: 2px 8px; }
  .card .play { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 44px; color: #fff; text-shadow: 0 2px 10px #000; }
  .card .body { padding: 10px; display: flex; flex-direction: column; gap: 6px; flex: 1; }
  .card .t { font-weight: 700; font-size: 14px; line-height: 1.3; }
  .card .meta { color: var(--dim); font-size: 12px; }
  .card .actions { display: flex; gap: 6px; margin-top: auto; }
  .card .actions .btn, .card .actions button { flex: 1; text-align: center; padding: 8px; font-size: 13px; }
  .pending { border-style: dashed; align-items: center; justify-content: center; color: var(--dim); aspect-ratio: 9/16; font-size: 14px; text-align: center; padding: 10px; }
  .runs { list-style: none; padding: 0; margin: 0; }
  .runs li { display: flex; gap: 10px; align-items: center; padding: 9px 0; border-top: 1px solid var(--line); flex-wrap: wrap; cursor: pointer; }
  .runs li:first-child { border-top: 0; }
  .runs li:hover .v { color: var(--accent); }
  .runs .v { flex: 1 1 260px; font-weight: 600; word-break: break-all; }
  .runs .d { color: var(--dim); font-size: 13px; }
  .pill { font-size: 12px; border-radius: 99px; padding: 2px 9px; border: 1px solid var(--line); }
  .pill.done { color: var(--ok); } .pill.error { color: var(--err); } .pill.running { color: var(--accent); }
  details summary { cursor: pointer; color: var(--dim); font-size: 13px; margin-top: 14px; }
  code { background:#0d0f13; padding: 1px 5px; border-radius: 4px; }
  .hide { display: none !important; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Clip <span>Factory</span></h1>
  <p class="sub">Long video in &rarr; vertical Shorts out, with captions. Ollama picks the most viral moments; clip 1 is ready to download while the rest are still being made.</p>
  <div id="sysError" class="panel error hide"></div>

  <div class="panel">
    <h2>1. Your video</h2>
    <label>Videos in the <code>input</code> folder</label>
    <div class="row">
      <select id="inputSel" style="flex:1 1 300px"></select>
      <button class="ghost" id="refreshInputs">Refresh</button>
    </div>
    <div class="or">&mdash; or upload one from your PC &mdash;</div>
    <div class="row">
      <input type="file" id="uploadFile" accept="video/*,.mkv,.flv,.ts">
      <span class="msg" id="uploadMsg"></span>
    </div>
    <div class="or">&mdash; or paste where it is on your PC (right-click the file &rarr; Copy as path) &mdash;</div>
    <input type="text" id="pathInput" placeholder='e.g. "C:\Users\you\Videos\podcast.mp4"'>
  </div>

  <div class="panel">
    <h2>2. Settings</h2>
    <div class="grid">
      <div><label>How many clips (1-100)</label><input type="number" id="count" min="1" max="100" value="10"></div>
      <div><label>Shortest clip (seconds)</label><input type="number" id="minLen" min="5" max="170" value="20"></div>
      <div><label>Longest clip (seconds)</label><input type="number" id="maxLen" min="10" max="180" value="60"></div>
      <div><label>Layout</label>
        <select id="layout">
          <option value="crop">Fill screen (one person talking)</option>
          <option value="fit">Whole picture + blurred background</option>
        </select></div>
      <div><label>Captions</label>
        <select id="captions">
          <option value="highlight">Word-by-word, yellow highlight</option>
          <option value="simple">Simple white</option>
          <option value="none">No captions</option>
        </select></div>
      <div><label>Ollama model</label><select id="model"></select></div>
    </div>
    <label class="check"><input type="checkbox" id="useAi" checked> Let Ollama pick the viral moments (otherwise a built-in scorer does)</label>
    <label class="check"><input type="checkbox" id="showTitle" checked> Put a hook title at the top of each clip</label>
    <details>
      <summary>Advanced</summary>
      <div class="grid" style="margin-top:12px">
        <div><label>Transcription accuracy</label>
          <select id="whisper">
            <option value="base">Normal (fast)</option>
            <option value="small">Better (about 2-3x slower)</option>
          </select></div>
        <div><label>Ollama address</label><input type="text" id="host"></div>
      </div>
    </details>
    <div style="margin-top:18px" class="row">
      <button class="big" id="startBtn">Make clips</button>
      <span class="msg" id="startMsg"></span>
    </div>
  </div>

  <div class="panel hide" id="runPanel">
    <div class="row" style="justify-content:space-between">
      <h2 id="runTitle" style="margin:0"></h2>
      <div class="row">
        <button class="ghost hide" id="cancelBtn">Stop</button>
        <button class="ghost" id="folderBtn">Open folder</button>
        <a class="btn hide" id="zipBtn">Download all (zip)</a>
      </div>
    </div>
    <div class="bar" id="barWrap"><div id="bar"></div></div>
    <div class="msg" id="runMsg"></div>
    <div class="warn hide" id="runWarn"></div>
    <div class="note hide" id="runNote"></div>
    <div class="error hide" id="runError"></div>
    <div class="clips" id="clips" style="margin-top:16px"></div>
  </div>

  <div class="panel">
    <h2>Past runs</h2>
    <ul class="runs" id="runs"></ul>
  </div>
</div>
<script>
const $ = (id) => document.getElementById(id);
function esc(s) { const d = document.createElement("div"); d.innerText = s == null ? "" : String(s); return d.innerHTML; }
const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
                set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} } };
const SETTINGS = ["count", "minLen", "maxLen", "layout", "captions", "whisper", "host", "useAi", "showTitle"];

let currentRun = null, pollTimer = null, shown = new Set();

async function api(url, opts) {
  const resp = await fetch(url, opts);
  let data = {};
  try { data = await resp.json(); } catch (e) {}
  if (!resp.ok) throw new Error(data.error || `Request failed (${resp.status})`);
  return data;
}

function loadSettings() {
  for (const id of SETTINGS) {
    const v = store.get("cf_" + id);
    if (v == null) continue;
    if ($(id).type === "checkbox") $(id).checked = v === "1"; else $(id).value = v;
  }
}
function saveSettings() {
  for (const id of SETTINGS) store.set("cf_" + id, $(id).type === "checkbox" ? ($(id).checked ? "1" : "0") : $(id).value);
  store.set("cf_model", $("model").value);
}

async function loadStatus() {
  const st = await api("/api/status");
  if (!$("host").value) $("host").value = st.default_host;
  if (st.ffmpeg_error) { $("sysError").innerText = st.ffmpeg_error; $("sysError").classList.remove("hide"); }
  if (st.active) openRun(st.active);
}

async function loadInputs(select) {
  const data = await api("/api/inputs");
  const prev = select || $("inputSel").value;
  $("inputSel").innerHTML = data.files.length
    ? data.files.map((f) => `<option value="${esc(f.name)}">${esc(f.name)} (${f.size_mb} MB)</option>`).join("")
    : '<option value="">(empty - upload a video, or put one in the input folder and press Refresh)</option>';
  if (prev && data.files.some((f) => f.name === prev)) $("inputSel").value = prev;
}

async function loadModels() {
  const data = await api("/api/models?host=" + encodeURIComponent($("host").value));
  const wanted = store.get("cf_model") || "llama3";
  if (!data.models.length) {
    $("model").innerHTML = `<option value="${esc(wanted)}">${esc(wanted)}${data.reachable ? " (not installed!)" : " (Ollama isn't running)"}</option>`;
    return;
  }
  $("model").innerHTML = data.models.map((m) => `<option value="${esc(m)}">${esc(m)}</option>`).join("");
  const match = data.models.find((m) => m === wanted) || data.models.find((m) => m.split(":")[0] === wanted.split(":")[0]);
  if (match) $("model").value = match;
}

$("refreshInputs").onclick = () => loadInputs();
$("host").onchange = () => { saveSettings(); loadModels(); };

$("uploadFile").onchange = () => {
  const file = $("uploadFile").files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload");
  $("startBtn").disabled = true;
  xhr.upload.onprogress = (e) => { if (e.lengthComputable) $("uploadMsg").innerText = `Uploading... ${Math.round(e.loaded / e.total * 100)}%`; };
  xhr.onload = async () => {
    $("startBtn").disabled = false;
    let data = {};
    try { data = JSON.parse(xhr.responseText); } catch (e) {}
    if (xhr.status !== 200) { $("uploadMsg").innerHTML = `<span class="error">${esc(data.error || "Upload failed.")}</span>`; return; }
    $("uploadMsg").innerText = "Uploaded - it's selected above.";
    $("pathInput").value = "";
    await loadInputs(data.name);
  };
  xhr.onerror = () => { $("startBtn").disabled = false; $("uploadMsg").innerHTML = '<span class="error">Upload failed - is the app still running?</span>'; };
  xhr.send(form);
};

$("startBtn").onclick = async () => {
  saveSettings();
  $("startMsg").innerText = "";
  const body = {
    input: $("inputSel").value, path: $("pathInput").value,
    count: +$("count").value, min_len: +$("minLen").value, max_len: +$("maxLen").value,
    layout: $("layout").value, captions: $("captions").value, show_title: $("showTitle").checked,
    whisper: $("whisper").value, use_ai: $("useAi").checked, host: $("host").value, model: $("model").value,
  };
  $("startBtn").disabled = true;
  try {
    const data = await api("/api/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    openRun(data.id);
    loadRuns();
  } catch (e) {
    $("startMsg").innerHTML = `<span class="error">${esc(e.message)}</span>`;
    $("startBtn").disabled = false;
  }
};

function openRun(id) {
  currentRun = id;
  shown = new Set();
  $("clips").innerHTML = "";
  $("runPanel").classList.remove("hide");
  clearInterval(pollTimer);
  poll();
  pollTimer = setInterval(poll, 1500);
  $("runPanel").scrollIntoView({ behavior: "smooth", block: "start" });
}

function clipCard(c) {
  const el = document.createElement("div");
  el.className = "card";
  el.dataset.n = c.n;
  el.innerHTML = `
    <div class="media">${c.poster ? `<img src="${c.poster}" alt="">` : ""}<span class="num">#${c.n}</span><span class="play">&#9654;</span></div>
    <div class="body">
      <div class="t">${esc(c.title)}</div>
      <div class="meta">${c.length}s &middot; from ${esc(c.at)} &middot; score ${c.score}${c.rated_by === "ollama" ? "" : " (built-in)"}</div>
      <div class="actions">
        <a class="btn" href="${c.download}" download>Download</a>
        <button class="ghost copy">Copy title</button>
      </div>
    </div>`;
  el.querySelector(".media").onclick = () => {
    const media = el.querySelector(".media");
    if (media.querySelector("video")) return;
    media.innerHTML = `<video src="${c.url}" controls autoplay playsinline></video><span class="num">#${c.n}</span>`;
  };
  el.querySelector(".copy").onclick = async (e) => {
    try { await navigator.clipboard.writeText(c.title); e.target.innerText = "Copied"; } catch (err) { e.target.innerText = "Can't copy"; }
    setTimeout(() => (e.target.innerText = "Copy title"), 1500);
  };
  return el;
}

function pendingCard(n, active) {
  const el = document.createElement("div");
  el.className = "card pending";
  el.dataset.pending = n;
  el.innerText = active ? `Clip ${n} is being cut...` : `Clip ${n} - waiting`;
  return el;
}

async function poll() {
  if (!currentRun) return;
  let run;
  try { run = await api(`/api/runs/${currentRun}`); } catch (e) { $("runMsg").innerText = "Can't reach the app - is it still running?"; return; }
  const running = run.status === "running";
  $("runTitle").innerText = run.video;
  $("bar").style.width = (running ? run.percent || 0 : 100) + "%";
  $("barWrap").classList.toggle("hide", !running);
  $("runMsg").innerText = run.message || "";
  $("runWarn").innerText = run.warning || ""; $("runWarn").classList.toggle("hide", !run.warning);
  $("runNote").innerText = run.note || ""; $("runNote").classList.toggle("hide", !run.note);
  let err = run.error || "";
  if (run.failed && run.failed.length) err += (err ? "\n" : "") + `Clip(s) ${run.failed.map((f) => f.n).join(", ")} couldn't be made: ${run.failed[run.failed.length - 1].error}`;
  $("runError").innerText = err; $("runError").classList.toggle("hide", !err);
  $("cancelBtn").classList.toggle("hide", !running);
  $("zipBtn").classList.toggle("hide", !run.clips.length);
  $("zipBtn").href = `/api/runs/${run.id}/zip`;
  $("zipBtn").innerText = running ? `Download finished (${run.clips.length}) as zip` : "Download all (zip)";

  // finished clips appear one by one, in place, without touching ones already shown (so playing videos keep playing)
  for (const c of run.clips) {
    if (shown.has(c.n)) continue;
    shown.add(c.n);
    const card = clipCard(c);
    const placeholder = $("clips").querySelector(`[data-pending="${c.n}"]`);
    if (placeholder) placeholder.replaceWith(card); else $("clips").appendChild(card);
  }
  $("clips").querySelectorAll("[data-pending]").forEach((el) => el.remove());
  if (running && run.planned) {
    const failed = new Set((run.failed || []).map((f) => f.n));
    const next = Math.max(0, ...run.clips.map((c) => c.n), ...failed) + 1;
    for (let n = next; n <= Math.min(run.planned, next + 3); n++) $("clips").appendChild(pendingCard(n, n === next));
  }
  if (!running) {
    clearInterval(pollTimer);
    $("startBtn").disabled = false;
    loadRuns();
  } else {
    $("startBtn").disabled = true;
  }
}

$("cancelBtn").onclick = async () => { if (currentRun && confirm("Stop making clips? The finished ones are kept.")) { try { await api(`/api/runs/${currentRun}/cancel`, { method: "POST" }); } catch (e) {} } };
$("folderBtn").onclick = async () => { if (!currentRun) return; try { await api(`/api/runs/${currentRun}/open-folder`, { method: "POST" }); } catch (e) { alert(e.message); } };

async function loadRuns() {
  const data = await api("/api/runs");
  $("runs").innerHTML = data.runs.length
    ? data.runs.map((r) => `<li data-id="${esc(r.id)}"><span class="v">${esc(r.video)}</span><span class="d">${esc(r.created)}</span>
        <span class="d">${r.made}${r.planned ? " / " + r.planned : ""} clips</span><span class="pill ${esc(r.status)}">${esc(r.status)}</span></li>`).join("")
    : '<li style="cursor:default"><span class="d">Nothing yet.</span></li>';
  $("runs").querySelectorAll("li[data-id]").forEach((li) => (li.onclick = () => openRun(li.dataset.id)));
}

(async () => {
  loadSettings();
  await loadStatus();
  await Promise.all([loadInputs(), loadModels(), loadRuns()]);
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    INPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"Clip Factory running - open http://localhost:{PORT}")
    print(f"Tip: put long videos in {INPUT_DIR} and they show up in the list.")
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
