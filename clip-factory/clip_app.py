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

import ai
import channel_stats
import downloader
import moments
import permissions
import policy
import publisher
import renderer
import transcriber
import trends
import upload_text

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

def _clip_policy(result: dict, bleeped: int) -> dict:
    """What the page shows on each clip: verdict + short notes."""
    verdict = result["verdict"]
    notes = []
    for f in result["findings"]:
        if f["rule"] == "profanity" and f["where"] != "title" and bleeped:
            continue  # handled by the bleep
        if f["severity"] in ("yellow", "red"):
            notes.append(f"{f['why']} ({f['where']})")
    if bleeped:
        notes.append(f"{bleeped} swear word{'s' if bleeped != 1 else ''} bleeped")
        if verdict == "yellow" and not any(f["severity"] == "yellow" and not (f["rule"] == "profanity" and f["where"] != "title")
                                           for f in result["findings"]):
            verdict = "green"  # the only problem was swearing, and it's bleeped now
    return {"verdict": verdict, "notes": notes[:4]}

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
        keys = ai.load_keys()
        cloud = bool(ai.cloud_transcribers(keys))
        words = transcriber.cached_words(source, "cloud") or transcriber.cached_words(source, s["whisper"])
        if words:
            update(message="Using the saved transcript from last time.", percent=35)
            run["engines"]["transcribe"] = "saved transcript"
        elif cloud and info["duration"]:
            words, tstats = ai.cloud_transcribe(
                source, info["duration"], keys, run_dir / "audio",
                local_fallback=lambda piece: transcriber.local_words(piece, s["whisper"]),
                progress=lambda m, p: update(message=m, percent=p * 0.35), cancelled=cancelled,
            )
            if not words:
                raise transcriber.TranscriptionError("No speech was found in this video - clips are cut around what's said, so it needs talking.")
            transcriber.save_cache(source, "cloud", words)
            run["engines"]["transcribe"] = ", ".join(
                f"{who}" if n == tstats["pieces"] else f"{who} ({n} of {tstats['pieces']} pieces)" for who, n in tstats["by"].items())
            if tstats["local"]:
                part = "the audio" if tstats["local"] == tstats["pieces"] else "part of the audio"
                run["warning"] = f"The cloud couldn't do {part} ({tstats['problem']}), so this PC did it."
        else:
            words = transcriber.transcribe(
                source, s["whisper"], cancelled=cancelled,
                progress=lambda m, p: update(message=m, percent=p * 0.35),
            )
            run["engines"]["transcribe"] = f"Whisper {s['whisper']} (this PC)"
        try:
            (run_dir / "audio").rmdir()
        except OSError:
            pass

        # 2. moments (35-50%)
        update("moments", "Looking for the best moments...", 35, save=True)
        sentences = moments.split_sentences(words, s["max_len"])
        candidates = moments.make_candidates(sentences, s["min_len"], s["max_len"])
        if not candidates:
            raise renderer.RenderError(
                f"Couldn't find any {s['min_len']}-{s['max_len']}s stretch of speech - try a wider clip length."
            )
        brain = ai.build_brain(s, keys, report=lambda m: update(message=m))
        size = brain.batch_size if brain else moments.BATCH_SIZE
        batches = max(1, -(-len(candidates) // size))
        done_batches = {"n": 0}

        def scoring_progress(msg):
            m = re.search(r"batch (\d+) of", msg)
            if m:
                done_batches["n"] = int(m.group(1)) - 1
            update(message=msg, percent=35 + 15 * done_batches["n"] / batches)

        stats = moments.score_candidates(candidates, brain, progress=scoring_progress, cancelled=cancelled, kind=s["kind"])
        if cancelled():
            raise transcriber.Cancelled()
        if brain and stats["fallback"]:
            why = "; ".join(brain.problems) or stats["ai_error"] or "the AI answers didn't make sense"
            run["warning"] = " ".join(filter(None, [run["warning"], (
                f"{stats['fallback']} of {len(candidates)} moments were rated by the built-in scorer ({why}).")]))
        elif brain and brain.problems:
            run["warning"] = " ".join(filter(None, [run["warning"], "; ".join(brain.problems)]))
        run["engines"]["moments"] = ", ".join(f"{name} ({n})" for name, n in stats["by"].items()) or "built-in scorer"
        run["stats"] = dict(stats, candidates=len(candidates))
        # YouTube rules: check every moment; clips that would break the rules are never picked
        blocked = 0
        for c in candidates:
            clip_words = [w for w in words if c["start"] - 0.05 <= w["start"] < c["end"] + 0.4]
            c["title"] = policy.clean_title(c["title"])
            c["policy"] = policy.scan(c["title"], words=clip_words, duration=c["end"] - c["start"])
            if s["safe_mode"] and c["policy"]["verdict"] == "red":
                c["score"] = -1
                blocked += 1
        allowed = [c for c in candidates if c["score"] >= 0]
        if blocked:
            run["policy_note"] = (f"{blocked} moment{'s' if blocked != 1 else ''} broke YouTube's rules "
                                  f"(slurs, harassment or sexual content) and {'were' if blocked != 1 else 'was'} skipped.")
        picks = moments.pick_best(allowed, s["count"])
        run["planned"] = len(picks)
        if len(picks) < s["count"]:
            run["note"] = (f"This video only has room for {len(picks)} separate clips of {s['min_len']}-{s['max_len']}s "
                           f"(they never overlap), so you'll get {len(picks)} instead of {s['count']}.")
        update("render", f"Found {len(picks)} moments - cutting clip 1...", 50, save=True)

        # upload text (description + tags) for every clip: the built-in writer is instant; when an AI is
        # available it writes better ones alongside the rendering, and they replace the built-in ones
        src = upload_text.source_for(source)
        texts: dict[int, dict] = {}
        texts_lock = threading.Lock()
        items = [{"n": n, "title": c["title"], "text": c["text"]} for n, c in enumerate(picks, start=1)]

        def write_texts():
            for k in range(0, len(items), 10):
                if cancelled():
                    return
                got = upload_text.ai_batch(brain, items[k:k + 10], src, s["kind"], s["channel_name"])
                with texts_lock:
                    texts.update(got)
                    for clip in run["clips"]:
                        if clip["n"] in got:
                            clip["upload"] = got[clip["n"]]
                if got:
                    save_run(run)

        if brain:
            threading.Thread(target=write_texts, daemon=True).start()

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
                bleeped = renderer.render_clip(
                    source, start, end, words, c["title"] if s["show_title"] else "",
                    s["layout"], s["captions"], run_dir / f"{name}.mp4", run_dir / f"{name}.jpg",
                    has_audio=info["has_audio"], cancelled=cancelled, bleep=s["bleep"],
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
                "policy": _clip_policy(c["policy"], bleeped),
                "upload": None,
            })
            with texts_lock:
                run["clips"][-1]["upload"] = texts.get(n) or upload_text.fallback(
                    {"title": c["title"], "text": c["text"]}, src, s["kind"], s["channel_name"])
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
                    "input_folder": str(INPUT_DIR), "js_runtime": bool(downloader.js_runtimes())})


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


class StartError(Exception):
    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.code = code


def parse_settings(data: dict) -> dict:
    min_len = _int(data, "min_len", 20, 5, 170)
    max_len = _int(data, "max_len", 60, 10, 180)
    if max_len < min_len + 5:
        raise StartError("The longest clip length must be at least 5 seconds more than the shortest.")
    host = str(data.get("host") or DEFAULT_HOST).strip()
    if not host.startswith("http"):
        host = "http://" + host
    return {
        "count": _int(data, "count", 10, 1, MAX_CLIPS),
        "min_len": min_len, "max_len": max_len,
        "layout": data.get("layout") if data.get("layout") in renderer.LAYOUTS else "crop",
        "captions": data.get("captions") if data.get("captions") in renderer.CAPTION_STYLES else "highlight",
        "show_title": bool(data.get("show_title", True)),
        "whisper": data.get("whisper") if data.get("whisper") in ("base", "small", "medium") else "base",
        "use_ai": bool(data.get("use_ai", True)),
        "safe_mode": bool(data.get("safe_mode", True)),
        "kind": "podcast" if data.get("kind") == "podcast" else "",
        "channel_name": re.sub(r"[\r\n]+", " ", str(data.get("channel_name") or "")).strip()[:60],
        "bleep": bool(data.get("bleep", True)),
        "host": host, "model": str(data.get("model") or "llama3").strip() or "llama3",
    }


def start_run(source: Path, settings: dict) -> str:
    if source.suffix.lower() not in VIDEO_EXTS:
        raise StartError(f"That doesn't look like a video file ({source.suffix or 'no extension'}).")
    with state_lock:
        if active_run["id"]:
            raise StartError("Another video is still being cut - wait for it to finish or press Stop.", 409)
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
        "video_duration": None, "finished_at": None, "engines": {}, "policy_note": None,
    }
    runs[run_id] = run
    save_run(run)
    threading.Thread(target=run_pipeline, args=(run,), daemon=True).start()
    return run_id


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
    try:
        run_id = start_run(source, parse_settings(data))
    except StartError as exc:
        return jsonify({"error": str(exc)}), exc.code
    return jsonify({"id": run_id}), 202


# ---------- AI engines (keys) ----------

def _ai_public() -> dict:
    k = ai.load_keys()
    return {"cloud_on": k["cloud_on"], "providers": [
        {"id": n, "label": ai.CLOUD[n][0], "free": ai.CLOUD[n][3], "set": bool(k[f"{n}_key"]), "hint": ai.key_hint(k[f"{n}_key"])}
        for n in ai.ORDER]}


@app.route("/api/ai", methods=["GET", "POST"])
def ai_settings():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        update = {"cloud_on": bool(data.get("cloud_on"))}
        for name in ai.ORDER:
            field = f"{name}_key"
            value = str(data.get(field) or "").strip()
            if data.get(f"clear_{field}"):
                update[field] = ""
            elif value:
                if not re.fullmatch(r"[A-Za-z0-9_\-.]{10,300}", value):
                    return jsonify({"error": f"That {ai.CLOUD[name][0]} key doesn't look right - copy it again."}), 400
                update[field] = value
        ai.save_keys(update)
    return jsonify(_ai_public())


@app.route("/api/ai/test", methods=["POST"])
def ai_test():
    return jsonify(ai.test_keys(ai.load_keys()))


# ---------- YouTube rules ----------

def _policy_input() -> tuple[dict, str, str, str]:
    data = request.get_json(silent=True) or {}
    return data, str(data.get("title") or "")[:300], str(data.get("description") or "")[:5000], str(data.get("text") or "")[:60000]


def _brain_from(data: dict):
    host = str(data.get("host") or DEFAULT_HOST).strip()
    host = host if host.startswith("http") else "http://" + host
    return ai.build_brain({"use_ai": True, "host": host, "model": str(data.get("model") or "llama3")}, ai.load_keys())


@app.route("/api/rules")
def rules_book():
    return jsonify(policy.load_rules() | {"questions": policy.QUESTIONS})


@app.route("/api/policy/scan", methods=["POST"])
def policy_scan():
    _data, title, description, text = _policy_input()
    return jsonify(policy.scan(title, description, text))


@app.route("/api/policy/review", methods=["POST"])
def policy_review():
    data, title, description, text = _policy_input()
    if not (title or description or text):
        return jsonify({"error": "Paste a title, description or script first."}), 400
    quick = policy.scan(title, description, text)
    review = policy.ai_review(_brain_from(data), title, description, text, str(data.get("kind") or "video"))
    verdict = quick["verdict"]
    if review.get("ok") and policy.LEVELS[review["verdict"]] > policy.LEVELS[verdict]:
        verdict = review["verdict"]
    return jsonify({"verdict": verdict, "scan": quick, "ai": review})


@app.route("/api/policy/fix", methods=["POST"])
def policy_fix():
    data, title, description, text = _policy_input()
    if not (title or description or text):
        return jsonify({"error": "Paste a title, description or script first."}), 400
    issues = data.get("issues") if isinstance(data.get("issues"), list) else []
    issues = issues or policy.scan(title, description, text)["findings"]
    return jsonify(policy.ai_fix(_brain_from(data), title, description, text, issues, str(data.get("kind") or "video")))


@app.route("/api/policy/ypp", methods=["POST"])
def policy_ypp():
    data = request.get_json(silent=True) or {}
    return jsonify(policy.ypp_status(_int(data, "subs", 0, 0, 10**9), _int(data, "hours", 0, 0, 10**9),
                                     _int(data, "shorts", 0, 0, 10**12), _int(data, "uploads", 0, 0, 10**6)))


@app.route("/api/policy/channel", methods=["POST"])
def policy_channel():
    data = request.get_json(silent=True) or {}
    return jsonify({"risks": policy.channel_risks(data.get("answers") or {})})


@app.route("/api/policy/updates", methods=["POST"])
def policy_updates():
    data = request.get_json(silent=True) or {}
    return jsonify(policy.check_updates(_brain_from(data)))


# ---------- Find viral videos ----------

TRENDS_FILE = APP_DIR / "trends_last.json"
trend_state: dict = {"status": "idle", "message": "", "error": None, "result": None, "label": None,
                     "updated": None, "summary": None, "summary_status": "idle"}
trend_lock = threading.Lock()


def _load_last_trends() -> None:
    try:
        saved = json.loads(TRENDS_FILE.read_text(encoding="utf-8"))
        trend_state.update(result=saved.get("result"), label=saved.get("label"), updated=saved.get("updated"),
                           summary=saved.get("summary"), status="done")
    except (OSError, json.JSONDecodeError):
        pass


def _save_trends() -> None:
    data = {k: trend_state[k] for k in ("result", "label", "updated", "summary")}
    TRENDS_FILE.write_text(json.dumps(data), encoding="utf-8")


def _trend_job(label: str, fn) -> tuple[dict, int]:
    with trend_lock:
        if trend_state["status"] == "running" or trend_state["summary_status"] == "running":
            return {"error": "Already looking - give it a moment."}, 409
        trend_state.update(status="running", message="Starting...", error=None)

    def work():
        try:
            result = fn(lambda m: trend_state.update(message=m))
            trend_state.update(status="done", result=result, label=label, summary=None,
                               updated=time.strftime("%Y-%m-%d %H:%M"), message="")
            _save_trends()
        except trends.TrendError as exc:
            trend_state.update(status="error", error=str(exc))
        except Exception as exc:
            trend_state.update(status="error", error=f"Unexpected problem: {trends.clean_error(exc)}")

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True}, 202


def _kind(value) -> str:
    return value if value in trends.LISTS else "streamers"


@app.route("/api/streamers", methods=["GET", "POST"])
def streamers():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        names = data.get("names") if isinstance(data.get("names"), list) else str(data.get("names") or "").splitlines()
        return jsonify({"names": trends.save_streamers([str(n) for n in names], _kind(data.get("kind")))})
    return jsonify({"names": trends.load_streamers(_kind(request.args.get("kind")))})


@app.route("/api/trends")
def trends_state():
    return jsonify(trend_state)


@app.route("/api/trends/scan", methods=["POST"])
def trends_scan():
    data = request.get_json(silent=True) or {}
    days = _int(data, "days", 7, 1, 60)
    include_streams = bool(data.get("include_streams", True))
    kind = _kind(data.get("kind"))
    names = trends.load_streamers(kind)
    if not names:
        return jsonify({"error": "Add at least one streamer first."}), 400
    body, code = _trend_job(
        f"{len(names)} {kind}, last {days} day{'s' if days != 1 else ''}",
        lambda progress: trends.scan_streamers(names, days, include_streams, progress, kind),
    )
    return jsonify(body), code


@app.route("/api/trends/search", methods=["POST"])
def trends_search():
    data = request.get_json(silent=True) or {}
    query = str(data.get("query") or "").strip()[:100]
    period = data.get("period") if data.get("period") in trends.SEARCH_PERIODS else "week"
    if not query:
        return jsonify({"error": "Type what to search for first."}), 400
    label = {"hour": "the last hour", "today": "today", "week": "this week", "month": "this month"}[period]
    episodes = bool(data.get("episodes_only"))
    body, code = _trend_job(f'"{query}", most viewed {label}' + (" (full episodes)" if episodes else ""),
                            lambda progress: trends.search(query, period, episodes))
    return jsonify(body), code


@app.route("/api/trends/summary", methods=["POST"])
def trends_summary():
    data = request.get_json(silent=True) or {}
    result = trend_state.get("result") or {}
    if not result.get("videos"):
        return jsonify({"error": "Scan or search first."}), 400
    with trend_lock:
        if trend_state["summary_status"] == "running" or trend_state["status"] == "running":
            return jsonify({"error": "Already working on it."}), 409
        trend_state["summary_status"] = "running"
    host = str(data.get("host") or DEFAULT_HOST).strip()
    host = host if host.startswith("http") else "http://" + host
    model = str(data.get("model") or "llama3")

    def work():
        try:
            brain = ai.build_brain({"use_ai": True, "host": host, "model": model}, ai.load_keys())
            trend_state["summary"] = trends.summarize(result["videos"], brain)
            _save_trends()
        finally:
            trend_state["summary_status"] = "idle"

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True}), 202


# ---------- Publish ----------

def _queue_public() -> list[dict]:
    names = {c["id"]: c["name"] for c in channel_stats.load_config()["channels"]}
    out = []
    for it in publisher.load_queue():
        out.append(dict(it, channel=names.get(it["cid"], "(pick a channel)"), file_name=Path(it["file"]).name,
                        missing=not Path(it["file"]).exists()))
    return sorted(out, key=lambda i: (i["when"] or "9999", i["added"]))


@app.route("/api/publish")
def publish_state():
    s = publisher.load_settings()
    secret = publisher.client_secret_path()
    return jsonify({
        "approved": s["approved"], "client_secret": str(secret) if secret else None,
        "channels": [{k: c.get(k) for k in ("id", "name", "ref", "connected", "token", "slots")} for c in publisher.channels()],
        "connecting": publisher.state["connecting"], "connect_error": publisher.state["connect_error"],
        "uploading": publisher.state["uploading"], "queue": _queue_public(), "quota": publisher.quota(),
        "weekdays": publisher.WEEKDAYS,
    })


@app.route("/api/publish/sources")
def publish_sources():
    runs_out = []
    if OUTPUT_DIR.exists():
        for d in sorted(OUTPUT_DIR.iterdir(), reverse=True)[:30]:
            run = load_run(d.name) if d.is_dir() else None
            if run and run.get("clips"):
                runs_out.append({"id": run["id"], "video": run["video"], "clips": len(run["clips"]), "created": run.get("created")})
    return jsonify({"runs": runs_out, "wayne": publisher.wayne_videos()})


def _publish_body() -> dict:
    return request.get_json(silent=True) or {}


@app.route("/api/publish/connect", methods=["POST"])
def publish_connect():
    try:
        publisher.connect_async(str(_publish_body().get("cid") or ""))
    except publisher.PublishError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True}), 202


@app.route("/api/publish/disconnect", methods=["POST"])
def publish_disconnect():
    publisher.disconnect(str(_publish_body().get("cid") or ""))
    return publish_state()


@app.route("/api/publish/approved", methods=["POST"])
def publish_approved():
    s = publisher.load_settings()
    s["approved"] = bool(_publish_body().get("approved"))
    publisher.save_settings(s)
    return publish_state()


@app.route("/api/publish/add", methods=["POST"])
def publish_add():
    data = _publish_body()
    items = []
    if data.get("run_id"):
        run = load_run(str(data["run_id"]))
        if not run:
            return jsonify({"error": "That clip run doesn't exist."}), 404
        for c in run.get("clips", []):
            up = c.get("upload") or {}
            items.append({"file": str(OUTPUT_DIR / run["id"] / c["file"]), "kind": "short", "cid": str(data.get("cid") or ""),
                          "title": up.get("title") or c["title"], "description": up.get("description") or c["title"],
                          "tags": up.get("tags") or [], "source": f"Clip Factory: {run['video']} #{c['n']}"})
    for w in data.get("wayne") or []:
        if isinstance(w, dict):
            items.append(w)
    added = publisher.add_items(items)
    return jsonify({"added": added})


@app.route("/api/publish/fill", methods=["POST"])
def publish_fill():
    return jsonify({"filled": publisher.fill_schedule()})


@app.route("/api/publish/item/<item_id>", methods=["POST"])
def publish_item(item_id):
    try:
        publisher.update_item(item_id, _publish_body())
    except publisher.PublishError as exc:
        return jsonify({"error": str(exc)}), 404
    return publish_state()


@app.route("/api/publish/item/<item_id>/remove", methods=["POST"])
def publish_remove(item_id):
    publisher.remove_item(item_id)
    return publish_state()


@app.route("/api/publish/item/<item_id>/upload", methods=["POST"])
def publish_upload(item_id):
    test = bool(_publish_body().get("test"))
    item = next((i for i in publisher.load_queue() if i["id"] == item_id), None)
    if not item:
        return jsonify({"error": "That item isn't in the queue any more."}), 404
    if publisher.state["uploading"]:
        return jsonify({"error": "Another upload is running - wait for it to finish."}), 409
    publisher.state["uploading"] = item_id

    def work():
        try:
            publisher._set(item_id, status="uploading", error="")
            res = publisher.upload_item(item, test=test, progress=lambda pct: publisher._set(item_id, progress=pct))
            if test:  # a private test copy - the item stays on the to-do list
                note = ("Test upload done (private) - open the link: if YouTube Studio shows 'Locked as private', Google "
                        "hasn't approved the app yet. Delete the test copy in YouTube Studio afterwards. " + res["note"]).strip()
                publisher._set(item_id, status="waiting", url=res["url"], error=note, progress=0, test=True)
            else:
                publisher._set(item_id, status="uploaded", video_id=res["video_id"], url=res["url"], error=res["note"],
                               progress=100, uploaded_at=time.strftime("%Y-%m-%d %H:%M"), test=False)
        except Exception as exc:
            publisher._set(item_id, status="failed", error=str(exc)[:300])
        finally:
            publisher.state["uploading"] = None

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True}), 202


@app.route("/api/publish/reveal", methods=["POST"])
def publish_reveal():
    item = next((i for i in publisher.load_queue() if i["id"] == str(_publish_body().get("id"))), None)
    if not item or not Path(item["file"]).exists():
        return jsonify({"error": "The file isn't there any more."}), 404
    try:
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", str(Path(item["file"]))])
        else:
            subprocess.Popen(["xdg-open", str(Path(item["file"]).parent)])
    except Exception as exc:
        return jsonify({"error": str(exc), "path": item["file"]}), 500
    return jsonify({"ok": True, "path": item["file"]})


@app.route("/api/publish/audit")
def publish_audit():
    return jsonify({"text": publisher.audit_text()})


# ---------- My channels (analyzer) ----------

@app.route("/api/stats")
def stats_report():
    return jsonify(channel_stats.analyze() | {"refreshing": channel_stats.refresh_running(),
                                              "last_error": channel_stats._refresh_state["last_error"]})


@app.route("/api/stats/config", methods=["POST"])
def stats_config():
    channel_stats.save_config(request.get_json(silent=True) or {})
    return stats_report()


@app.route("/api/stats/refresh", methods=["POST"])
def stats_refresh():
    if not any(c["ref"] for c in channel_stats.load_config()["channels"]):
        return jsonify({"error": "Add at least one channel's @handle first."}), 400
    channel_stats.refresh_async()
    return jsonify({"ok": True}), 202


@app.route("/api/stats/coach", methods=["POST"])
def stats_coach():
    data = request.get_json(silent=True) or {}
    return jsonify(channel_stats.coach(channel_stats.analyze(), _brain_from(data) if data.get("use_ai", True) else None))


# ---------- Clipping permission ----------

perm_state: dict = {"status": "idle", "message": "", "error": None}


@app.route("/api/permissions")
def permissions_state():
    return jsonify(dict(perm_state, results=permissions.all_cached()))


@app.route("/api/permissions/check", methods=["POST"])
def permissions_check():
    data = request.get_json(silent=True) or {}
    names = [str(n).strip() for n in (data.get("names") or []) if str(n).strip()][:40]
    if not names:
        return jsonify({"error": "No channels to check."}), 400
    with trend_lock:
        if perm_state["status"] == "running":
            return jsonify({"error": "Already checking - give it a moment."}), 409
        perm_state.update(status="running", message="Starting...", error=None)
    brain = _brain_from(data)
    force = bool(data.get("force"))

    def work():
        try:
            permissions.check_many(names, brain, force, progress=lambda m: perm_state.update(message=m))
            perm_state.update(status="done", message="")
        except Exception as exc:
            perm_state.update(status="error", error=f"Unexpected problem: {trends.clean_error(exc)}")

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True}), 202


# ---------- Downloads ----------

def _public_download(d: dict) -> dict:
    return {k: v for k, v in d.items() if k not in ("then_clip", "cancel")} | {"auto_clip": bool(d.get("then_clip"))}


@app.route("/api/downloads", methods=["GET", "POST"])
def downloads_route():
    if request.method == "GET":
        items = sorted(downloader.downloads.values(), key=lambda d: d["created"], reverse=True)[:30]
        return jsonify({"downloads": [_public_download(d) for d in items]})
    data = request.get_json(silent=True) or {}
    url = str(data.get("url") or "").strip()
    if not downloader.is_url(url):
        return jsonify({"error": "Paste a full link (starting with https://)."}), 400
    then_clip = None
    if data.get("then_clip"):
        try:
            then_clip = parse_settings(data.get("settings") or {})
        except StartError as exc:
            return jsonify({"error": str(exc)}), 400
    d = downloader.add(url, str(data.get("quality") or "1080"), str(data.get("title") or ""), then_clip)
    return jsonify(_public_download(d)), 202


@app.route("/api/downloads/<did>/cancel", methods=["POST"])
def cancel_download(did):
    return jsonify({"ok": downloader.cancel(did)})


def _auto_clip(d: dict) -> None:
    """After a "Download + make clips": start cutting as soon as no other video is being cut."""
    if d["status"] != "done" or not d.get("then_clip") or not d.get("file"):
        return

    def wait_and_start():
        d["message"] = "Downloaded - waiting for the current clips to finish, then this one starts."
        while True:
            try:
                d["clip_run"] = start_run(INPUT_DIR / d["file"], d["then_clip"])
                d["message"] = "Downloaded - clips are being made now."
                return
            except StartError as exc:
                if exc.code != 409:
                    d.update(message=f"Downloaded, but the clips couldn't start: {exc}")
                    return
            time.sleep(5)

    threading.Thread(target=wait_and_start, daemon=True).start()


downloader.on_finished.append(_auto_clip)


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
        for c in run["clips"]:  # title + description + tags for each clip, ready to paste
            if c.get("upload"):
                zf.writestr(f"{c['n']:03d} - upload text.txt", upload_text.as_text(c["upload"]))
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
  .verdict { border-radius: 8px; padding: 6px 9px; font-size: 12px; line-height: 1.4; }
  .verdict.green { background: #12301f; color: var(--ok); }
  .verdict.yellow { background: #3a2f0a; color: #ffcf4d; }
  .verdict.red { background: #3a1512; color: var(--err); }
  .verdict b { display: block; font-size: 13px; }
  .issue { border-left: 3px solid var(--line); padding: 6px 10px; margin: 8px 0; background: #14161c; border-radius: 0 8px 8px 0; }
  .issue.yellow { border-color: #ffcf4d; } .issue.red { border-color: var(--err); } .issue.info { border-color: var(--line); }
  .rule { border-top: 1px solid var(--line); padding: 12px 0; }
  .rule:first-child { border-top: 0; }
  .rule h3 { margin: 0 0 4px; font-size: 15px; }
  .rule .area { color: var(--dim); font-size: 12px; }
  .rule ul { margin: 6px 0; padding-left: 20px; }
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
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; }
  .kpi { background: #14161c; border: 1px solid var(--line); border-radius: 10px; padding: 14px; display: grid; gap: 4px; align-content: start; }
  .kpi .lbl { font-size: 12px; color: var(--dim); text-transform: uppercase; letter-spacing: .06em; }
  .kpi .big { font-size: 28px; font-weight: 800; font-variant-numeric: tabular-nums; }
  .kpi .sub { font-size: 13px; color: var(--dim); }
  .up { color: var(--ok); } .down { color: var(--err); }
  .goalbar { height: 10px; background: #0d0f13; border-radius: 4px; overflow: hidden; margin-top: 6px; }
  .goalbar div { height: 100%; background: var(--accent); border-radius: 4px; }
  .legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 13px; color: var(--dim); margin-bottom: 6px; }
  .legend i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
  .chartwrap { position: relative; }
  .chartwrap svg { width: 100%; height: auto; display: block; }
  .tip { position: absolute; pointer-events: none; background: #0d0f13; border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; font-size: 12px; line-height: 1.5; min-width: 150px; }
  .tbl { width: 100%; border-collapse: collapse; font-size: 14px; font-variant-numeric: tabular-nums; }
  .tbl th, .tbl td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
  .tbl th { font-size: 12px; color: var(--dim); text-transform: uppercase; letter-spacing: .06em; font-weight: 600; }
  .tbl td.r, .tbl th.r { text-align: right; }
  .tblwrap { overflow-x: auto; }
  .step { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 12px; padding: 14px 0; border-top: 1px solid var(--line); }
  .step:first-of-type { border-top: 0; }
  .step .n { width: 30px; height: 30px; border-radius: 50%; background: #23262f; display: flex; align-items: center; justify-content: center; font-weight: 800; }
  .step .n.ok { background: var(--ok); color: #111; }
  .conn { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; padding: 6px 0; }
  .conn b { min-width: 140px; }
  .qday { margin-top: 14px; font-weight: 700; color: var(--dim); text-transform: uppercase; font-size: 12px; letter-spacing: .06em; }
  .qitem { display: grid; grid-template-columns: 70px minmax(0, 1fr); gap: 12px; padding: 10px; border: 1px solid var(--line); border-radius: 10px; margin-top: 8px; background: #14161c; }
  .qitem .time { font-weight: 800; font-variant-numeric: tabular-nums; }
  .qitem .acts { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }
  .qitem .acts button, .qitem .acts a { padding: 5px 10px; font-size: 12px; }
  .banner { border-radius: 10px; padding: 12px 14px; font-size: 14px; margin-bottom: 10px; }
  .banner.manual { background: #3a2f0a; color: #ffcf4d; }
  .banner.auto { background: #12301f; color: var(--ok); }
  .chrow { display: grid; grid-template-columns: 1.2fr 2fr; gap: 10px; align-items: center; margin-bottom: 8px; }
  .tabs { display: flex; gap: 8px; margin: 0 0 18px; flex-wrap: wrap; }
  .tabs button { background: var(--panel); color: var(--dim); border: 1px solid var(--line); font-size: 15px; padding: 11px 20px; }
  .tabs button.on { background: var(--accent); color: #111; border-color: var(--accent); }
  textarea { width: 100%; min-height: 120px; resize: vertical; background:#0d0f13; color: var(--text); border:1px solid var(--line); border-radius: 8px; padding: 10px; font-size: 14px; line-height: 1.5; }
  .vids { display: flex; flex-direction: column; gap: 10px; }
  .vid { display: flex; gap: 12px; background: #14161c; border: 1px solid var(--line); border-radius: 10px; padding: 10px; align-items: flex-start; }
  .vid img { width: 176px; aspect-ratio: 16/9; object-fit: cover; border-radius: 6px; background: #000; flex: none; }
  .vid .info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 5px; }
  .vid .t { font-weight: 700; font-size: 15px; line-height: 1.3; }
  .vid .meta { color: var(--dim); font-size: 13px; }
  .vid .stats { display: flex; gap: 6px; flex-wrap: wrap; }
  .tag { font-size: 12px; border-radius: 6px; padding: 3px 8px; background: #23262f; }
  .tag.hot { background: #3a2a00; color: var(--accent); font-weight: 700; }
  .tag.big { background: #12301f; color: var(--ok); font-weight: 700; }
  .tag.no { background: #3a1512; color: var(--err); font-weight: 700; }
  .tag.maybe { background: #3a2f0a; color: #ffcf4d; }
  .perm { border-top: 1px solid var(--line); padding: 10px 0; }
  .perm:first-child { border-top: 0; }
  .perm q { display: block; color: var(--dim); font-size: 13px; margin: 4px 0 0 10px; }
  .vid .actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
  .vid .actions .btn, .vid .actions button { padding: 7px 12px; font-size: 13px; }
  .rank { font-size: 20px; font-weight: 800; color: var(--accent); width: 34px; text-align: center; flex: none; padding-top: 4px; }
  .dl { border-top: 1px solid var(--line); padding: 10px 0; }
  .dl:first-child { border-top: 0; }
  .dl .bar { margin: 6px 0; height: 7px; }
  .summary { background: #14161c; border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; margin-bottom: 14px; }
  .summary ul { margin: 6px 0 0; padding-left: 20px; }
  .summary li { margin: 3px 0; }
  @media (max-width: 640px) { .vid { flex-wrap: wrap; } .vid img { width: 100%; } .rank { display: none; } }
</style>
</head>
<body>
<div class="wrap">
  <h1>Clip <span>Factory</span></h1>
  <p class="sub">Find what's going viral &rarr; download it &rarr; get vertical Shorts with captions. AI picks the best moments; clip 1 is ready to download while the rest are still being made.</p>
  <div id="sysError" class="panel error hide"></div>
  <div class="tabs">
    <button id="tabBtnFind" data-tab="find">Find viral videos</button>
    <button id="tabBtnClips" data-tab="clips">Make clips</button>
    <button id="tabBtnRules" data-tab="rules">YouTube rules</button>
    <button id="tabBtnStats" data-tab="stats">My channels</button>
    <button id="tabBtnPub" data-tab="pub">Publish</button>
    <button id="aiToggle" class="ghost" style="margin-left:auto">AI engines: ...</button>
  </div>

  <div class="panel hide" id="aiPanel">
    <h2>AI engines</h2>
    <label class="check" style="font-size:15px"><input type="checkbox" id="cloudOn"> <b>Use cloud AI - much faster.</b>&nbsp;Your PC only cuts the clips.</label>
    <div class="msg" style="margin:8px 0 14px">
      Add a key for any AI you want - only those get used. <b>Free</b> ones are always tried first; <b>paid</b> ones only when the free ones are busy or used up.<br>
      Writing down the speech: Groq &rarr; ChatGPT (OpenAI) &rarr; this PC.
      Picking the viral moments: Gemini &rarr; Groq &rarr; OpenRouter &rarr; Claude &rarr; ChatGPT &rarr; Grok &rarr; Ollama on this PC &rarr; built-in scorer.
    </div>
    <div class="grid" id="aiKeys"></div>
    <div class="row" style="margin-top:14px">
      <button id="aiSave">Save</button>
      <button class="ghost" id="aiTest">Test the keys</button>
      <span class="msg" id="aiMsg"></span>
    </div>
    <div class="note">Keys are saved only on this PC (in <code>ai_keys.json</code>). With cloud AI on, the video's audio and text are sent to those companies to be processed.
      A ChatGPT Plus or Claude Pro subscription is not an API key - paid keys are pay-per-use from the links above.</div>
  </div>

  <div id="tabFind">
    <div class="panel">
      <h2>Download a video from a link</h2>
      <div class="row">
        <input type="text" id="linkInput" style="flex:1 1 320px" placeholder="Paste a YouTube, Twitch or Kick link...">
        <select id="quality" style="width:auto"><option value="1080">1080p</option><option value="720">720p (smaller, faster)</option></select>
        <button id="linkDl" class="ghost">Download</button>
        <button id="linkDlClip">Download + make clips</button>
      </div>
      <div class="msg" id="linkMsg"></div>
      <div id="downloads" style="margin-top:8px"></div>
    </div>

    <div class="panel">
      <h2>What's viral right now</h2>
      <div class="grid">
        <div>
          <div class="row" style="margin-bottom:8px">
            <label class="check" style="margin:0"><input type="radio" name="listKind" value="streamers" checked> Streamers</label>
            <label class="check" style="margin:0"><input type="radio" name="listKind" value="podcasts"> Podcasts</label>
          </div>
          <label id="listLabel">Your streamers - one per line (their YouTube @name or channel link)</label>
          <textarea id="streamers" spellcheck="false"></textarea>
          <div class="note hide" id="podcastNote">Only full episodes (20+ minutes) are shown. Big podcasts often claim copyright on clips, but many welcome clippers - click <b>Can I clip them?</b> and the AI reads each show's rules for you.</div>
          <div class="row" style="margin-top:10px">
            <select id="days" style="width:auto">
              <option value="1">Last 24 hours</option><option value="3">Last 3 days</option>
              <option value="7" selected>Last 7 days</option><option value="14">Last 14 days</option><option value="30">Last 30 days</option>
            </select>
            <label class="check" style="margin:0"><input type="checkbox" id="incStreams" checked> Include past live streams</label>
          </div>
          <div class="row" style="margin-top:10px"><button id="scanBtn">Scan my streamers</button>
            <button class="ghost" id="permBtn">Can I clip them?</button></div>
        </div>
        <div>
          <label>Or search all of YouTube</label>
          <input type="text" id="searchInput" placeholder="e.g. kai cenat stream, minecraft, podcast...">
          <div class="row" style="margin-top:10px">
            <select id="period" style="width:auto">
              <option value="today">Most viewed today</option><option value="week" selected>Most viewed this week</option><option value="month">Most viewed this month</option>
            </select>
            <button id="searchBtn">Search</button>
          </div>
          <label class="check"><input type="checkbox" id="episodesOnly"> Full episodes only (20+ min) - best for podcasts</label>
        </div>
      </div>
      <div class="msg" id="trendMsg" style="margin-top:12px"></div>
    </div>

    <div class="panel hide" id="permPanel">
      <div class="row" style="justify-content:space-between">
        <h2 style="margin:0">Clipping permission</h2>
        <span class="msg" id="permMsg"></span>
      </div>
      <div class="msg" style="margin:6px 0 8px">The AI reads each channel's description and its latest video descriptions. Quotes are copied word for word from the channel. <b>Allowed</b> = the show invites clippers. <b>Unclear</b> = it doesn't say - ask the show first. This is a helper, not legal advice.</div>
      <div id="permList"></div>
    </div>

    <div class="panel hide" id="resultsPanel">
      <div class="row" style="justify-content:space-between;margin-bottom:12px">
        <h2 style="margin:0" id="resultsTitle"></h2>
        <div class="row">
          <select id="sortBy" style="width:auto">
            <option value="heat">Hottest right now</option><option value="vs_normal">Biggest jump vs. their normal</option>
            <option value="views">Most views</option><option value="newest">Newest</option>
          </select>
          <button class="ghost" id="askAi">Ask AI what's hot</button>
        </div>
      </div>
      <div id="summary"></div>
      <div class="warn hide" id="failedMsg"></div>
      <div class="vids" id="vids"></div>
    </div>
  </div>

  <div id="tabPub" class="hide">
    <div class="panel">
      <h2>Set up the publisher (once)</h2>
      <div class="step"><div class="n" id="st1n">1</div><div>
        <b>Google project file (client_secret.json)</b>
        <div class="msg" id="st1msg"></div>
        <details style="margin-top:6px"><summary class="msg" style="cursor:pointer">How to get it (10 minutes, free)</summary>
          <ol class="msg" style="margin:8px 0 0;padding-left:20px;line-height:1.7">
            <li>Open <a href="https://console.cloud.google.com/" target="_blank" rel="noopener" style="color:var(--accent)">console.cloud.google.com</a> and create a project (top bar &rarr; New project), or use the one your API key is in.</li>
            <li>APIs &amp; Services &rarr; Library &rarr; search <b>YouTube Data API v3</b> &rarr; Enable.</li>
            <li>Open <a href="https://console.cloud.google.com/auth/overview" target="_blank" rel="noopener" style="color:var(--accent)">Google Auth Platform</a> (same project). If you see <b>Get started</b>: app name <b>Clip Factory</b>, your email, Audience <b>External</b>, your email again, tick I agree &rarr; <b>Create</b>.</li>
            <li>Left menu &rarr; <b>Audience</b> &rarr; under Publishing status click <b>Publish app</b> &rarr; Confirm (otherwise logins expire every 7 days).</li>
            <li>Left menu &rarr; <b>Clients</b> &rarr; <b>+ Create client</b> &rarr; Application type <b>Desktop app</b> &rarr; Create &rarr; click the download button.</li>
            <li>When you connect, Google says "Google hasn't verified this app" - that's normal for your own app: click <b>Advanced</b> &rarr; <b>Go to Clip Factory</b> &rarr; Continue.</li>
            <li>Rename the file to <code>client_secret.json</code> and put it in the <code>clip-factory</code> folder. Then reload this page.</li>
          </ol></details>
      </div></div>
      <div class="step"><div class="n" id="st2n">2</div><div>
        <b>Connect each channel</b>
        <div class="msg">Google's login opens in your browser. When it asks which account or channel to use, pick <b>that</b> channel. The channels come from the My channels tab.</div>
        <div id="connList" style="margin-top:6px"></div>
        <div class="error hide" id="connErr"></div>
      </div></div>
      <div class="step"><div class="n" id="st3n">3</div><div>
        <b>Google's approval for automatic uploads</b>
        <div class="msg">Until Google approves your app (free, usually 1-4 weeks), YouTube locks every video it uploads as private. Until then the schedule below is a checklist you post from yourself.</div>
        <div class="row" style="margin-top:8px">
          <button class="ghost" id="auditBtn">Prepare the approval request</button>
          <label class="check" style="margin:0"><input type="checkbox" id="approvedChk"> Google approved my app - upload automatically</label>
        </div>
        <div class="hide" id="auditBox" style="margin-top:10px">
          <div class="msg">Open <a href="https://support.google.com/youtube/contact/yt_api_form" target="_blank" rel="noopener" style="color:var(--accent)">Google's form</a> and copy these answers into it:</div>
          <textarea id="auditText" readonly style="min-height:260px;margin-top:6px;font-size:12px"></textarea>
          <button class="ghost" id="auditCopy" style="margin-top:6px">Copy all</button>
        </div>
      </div></div>
    </div>

    <div class="panel">
      <h2>Add videos to the schedule</h2>
      <div class="grid" style="align-items:end">
        <div><label for="addRun">Clips from Clip Factory</label><select id="addRun"></select></div>
        <div><label for="addRunCh">Post them on</label><select id="addRunCh"></select></div>
        <div><button id="addRunBtn">Add these clips</button></div>
      </div>
      <div style="margin-top:16px"><div class="row" style="justify-content:space-between"><label style="margin:0">Finished videos from Wayne Factory</label><button class="ghost" id="addAllWayne">Add all</button></div>
        <div id="wayneList" class="msg" style="margin-top:6px">Looking for videos...</div></div>
      <div class="msg" id="addMsg" style="margin-top:8px"></div>
    </div>

    <div class="panel">
      <div class="row" style="justify-content:space-between">
        <h2 style="margin:0">Schedule</h2>
        <div class="row"><span class="msg" id="quotaMsg"></span><button id="fillBtn">Fill the schedule</button></div>
      </div>
      <div class="msg" style="margin:6px 0 10px" id="slotsMsg"></div>
      <div id="modeBanner"></div>
      <div id="queueList"></div>
    </div>
  </div>

  <div id="tabStats" class="hide">
    <div class="panel">
      <div class="row" style="justify-content:space-between">
        <h2 style="margin:0">All my channels</h2>
        <div class="row">
          <span class="msg" id="statsMsg"></span>
          <button class="ghost" id="statsSetupBtn">Channels &amp; goal</button>
          <button id="statsRefresh">Refresh now</button>
        </div>
      </div>
      <div class="msg" id="statsSource" style="margin-top:6px"></div>
    </div>

    <div class="panel hide" id="statsSetup">
      <h2>Channels &amp; goal</h2>
      <div class="msg" style="margin-bottom:10px">Type each channel's YouTube @handle (or paste its link). Numbers are checked every 3 hours while Clip Factory is open.</div>
      <div id="chanRows"></div>
      <div class="grid" style="margin-top:12px">
        <div><label for="goalViews">Goal: total views across all channels</label><input type="number" id="goalViews" min="1000" step="1000"></div>
        <div><label for="goalStart">Counting from</label><input type="text" id="goalStart" placeholder="2026-10-03"></div>
        <div><label for="goalEnd">Deadline</label><input type="text" id="goalEnd" placeholder="2026-12-01"></div>
        <div><label for="ytKey">YouTube API key (optional - exact numbers)</label><input type="text" id="ytKey" autocomplete="off" spellcheck="false" placeholder="AIza..."><div class="msg" id="ytKeyState"></div></div>
      </div>
      <div class="row" style="margin-top:12px"><button id="statsSave">Save and check now</button><span class="msg" id="statsSaveMsg"></span></div>
    </div>

    <div class="kpis" id="kpis" style="margin-bottom:18px"></div>

    <div class="panel">
      <div class="row" style="justify-content:space-between;margin-bottom:8px">
        <h2 style="margin:0">Views per day</h2>
        <button class="ghost" id="chartAsTable">Show as table</button>
      </div>
      <div class="legend" id="chartLegend"></div>
      <div class="chartwrap" id="chartWrap"><svg id="chart" viewBox="0 0 720 250" role="img" aria-label="Views per day, last 14 days"></svg><div class="tip hide" id="chartTip"></div></div>
      <div class="tblwrap hide" id="chartTable"></div>
    </div>

    <div class="panel">
      <h2>This week, channel by channel</h2>
      <div class="tblwrap"><table class="tbl" id="chanTable"></table></div>
    </div>

    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr));align-items:start">
      <div class="panel">
        <h2 id="topTitle">Top videos this week</h2>
        <div id="topVids"></div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between;margin-bottom:8px"><h2 style="margin:0">What to do next week</h2><button class="ghost" id="coachBtn">Ask the AI coach</button></div>
        <div id="coach"></div>
      </div>
    </div>
  </div>

  <div id="tabRules" class="hide">
    <div class="panel">
      <h2>Check a video before you upload</h2>
      <div class="msg" style="margin-bottom:10px">Paste the title, description and script (or spoken words). The instant check runs on this PC; <b>AI review</b> reads it against all of YouTube's rules.</div>
      <label>Title</label><input type="text" id="pTitle" placeholder="Your video title">
      <label style="margin-top:10px">Description</label><textarea id="pDesc" style="min-height:70px" placeholder="Optional"></textarea>
      <label style="margin-top:10px">Script / what's said in the video</label><textarea id="pText" style="min-height:160px" placeholder="Paste the script or transcript"></textarea>
      <div class="row" style="margin-top:12px">
        <button class="ghost" id="pScan">Instant check</button>
        <button id="pReview">AI review</button>
        <button class="ghost" id="pFix">Fix it for me</button>
        <span class="msg" id="pMsg"></span>
      </div>
      <div id="pResult" style="margin-top:12px"></div>
    </div>

    <div class="panel">
      <h2>Can my channel get monetized?</h2>
      <div class="grid">
        <div><label>Subscribers</label><input type="number" id="ySubs" min="0" value="0"></div>
        <div><label>Watch hours (last 12 months)</label><input type="number" id="yHours" min="0" value="0"></div>
        <div><label>Shorts views (last 90 days)</label><input type="number" id="yShorts" min="0" value="0"></div>
        <div><label>Public uploads (last 90 days)</label><input type="number" id="yUploads" min="0" value="0"></div>
      </div>
      <div class="row" style="margin-top:12px"><button id="yCheck">Check</button></div>
      <div id="yResult" style="margin-top:12px"></div>
    </div>

    <div class="panel">
      <h2>Is my channel at risk?</h2>
      <div class="msg" style="margin-bottom:8px">These are the rules that remove whole channels from monetization - tick what's true for you.</div>
      <div id="qList"></div>
      <div class="row" style="margin-top:12px"><button id="qCheck">Check my channel</button></div>
      <div id="qResult" style="margin-top:12px"></div>
    </div>

    <div class="panel">
      <div class="row" style="justify-content:space-between">
        <h2 style="margin:0">YouTube's rules, in plain English</h2>
        <button class="ghost" id="updBtn">Check for rule updates</button>
      </div>
      <div class="msg" id="rulesAsOf" style="margin:6px 0 10px"></div>
      <div id="updResult"></div>
      <div id="rulesList"></div>
    </div>
  </div>

  <div id="tabClips">
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
    <div class="row" style="margin-bottom:12px">
      <label style="margin:0">Type of video:</label>
      <select id="kind" style="width:auto">
        <option value="">Stream, gaming, vlog...</option>
        <option value="podcast">Podcast / interview</option>
      </select>
      <span class="msg" id="kindNote"></span>
    </div>
    <div class="grid">
      <div><label>How many clips (1-100)</label><input type="number" id="count" min="1" max="100" value="10"></div>
      <div><label>Shortest clip (seconds)</label><input type="number" id="minLen" min="5" max="170" value="20"></div>
      <div><label>Longest clip (seconds)</label><input type="number" id="maxLen" min="10" max="180" value="60"></div>
      <div><label>Layout</label>
        <select id="layout">
          <option value="crop">Fill screen (one person talking)</option>
          <option value="fit">Whole picture + blurred background</option>
          <option value="podcast">Podcast - two people, split screen</option>
        </select></div>
      <div><label>Captions</label>
        <select id="captions">
          <option value="highlight">Word-by-word, yellow highlight</option>
          <option value="simple">Simple white</option>
          <option value="none">No captions</option>
        </select></div>
      <div><label>Ollama model</label><select id="model"></select></div>
    </div>
    <label class="check"><input type="checkbox" id="useAi" checked> Let AI pick the viral moments (otherwise a built-in scorer does)</label>
    <div style="max-width:420px;margin:4px 0 6px"><label for="channelName">Your channel name (used at the end of each description)</label><input type="text" id="channelName" placeholder="e.g. Hot Mic Moments"></div>
    <label class="check"><input type="checkbox" id="showTitle" checked> Put a hook title at the top of each clip</label>
    <label class="check"><input type="checkbox" id="safeMode" checked> Skip moments that break YouTube's rules (slurs, harassment, sexual content)</label>
    <label class="check"><input type="checkbox" id="bleep" checked> Bleep swear words (and show them as F*** in the captions)</label>
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
    <div class="note hide" id="runEngines"></div>
    <div class="warn hide" id="runWarn"></div>
    <div class="note hide" id="runNote"></div>
    <div class="note hide" id="runPolicy"></div>
    <div class="error hide" id="runError"></div>
    <div class="clips" id="clips" style="margin-top:16px"></div>
  </div>

  <div class="panel">
    <h2>Past runs</h2>
    <ul class="runs" id="runs"></ul>
  </div>
  </div>
</div>
<script>
const $ = (id) => document.getElementById(id);
function esc(s) { const d = document.createElement("div"); d.innerText = s == null ? "" : String(s); return d.innerHTML; }
const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
                set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} } };
const SETTINGS = ["channelName", "kind", "count", "minLen", "maxLen", "layout", "captions", "whisper", "host", "useAi", "showTitle", "safeMode", "bleep"];

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
  const body = { input: $("inputSel").value, path: $("pathInput").value, ...clipSettings() };
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

function clipSettings() {
  return {
    count: +$("count").value, min_len: +$("minLen").value, max_len: +$("maxLen").value,
    layout: $("layout").value, captions: $("captions").value, show_title: $("showTitle").checked,
    whisper: $("whisper").value, use_ai: $("useAi").checked, host: $("host").value, model: $("model").value,
    safe_mode: $("safeMode").checked, bleep: $("bleep").checked, kind: $("kind").value, channel_name: $("channelName").value,
  };
}

function openRun(id) {
  showTab("clips");
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
      <div class="meta">${c.length}s &middot; from ${esc(c.at)} &middot; score ${c.score}${c.rated_by === "heuristic" ? " (built-in)" : " &middot; " + esc(c.rated_by)}</div>
      ${policyBadge(c.policy)}
      <div class="actions">
        <a class="btn" href="${c.download}" download>Download</a>
        <button class="ghost copy">Copy title</button>
      </div>
      <div class="actions">
        <button class="ghost copydesc">Copy description</button>
        <button class="ghost copytags">Copy tags</button>
      </div>
      <details class="uptext"><summary class="msg" style="cursor:pointer">Upload text</summary><div class="uptext-body"></div></details>
      <button class="ghost rulescheck" style="padding:6px;font-size:12px">Full rules check</button>
    </div>`;
  el.querySelector(".media").onclick = () => {
    const media = el.querySelector(".media");
    if (media.querySelector("video")) return;
    media.innerHTML = `<video src="${c.url}" controls autoplay playsinline></video><span class="num">#${c.n}</span>`;
  };
  el.querySelector(".rulescheck").onclick = () => {
    $("pTitle").value = c.title; $("pDesc").value = ""; $("pText").value = c.text || "";
    showTab("rules"); $("pTitle").scrollIntoView({ behavior: "smooth", block: "center" }); runPolicyCheck(true);
  };
  const copy = async (btn, text, label) => {
    try { await navigator.clipboard.writeText(text); btn.innerText = "Copied"; } catch (err) { btn.innerText = "Can't copy"; }
    setTimeout(() => (btn.innerText = label), 1500);
  };
  el.querySelector(".copy").onclick = (e) => copy(e.target, c.title, "Copy title");
  el.querySelector(".copydesc").onclick = (e) => copy(e.target, el._upload ? el._upload.description : c.title, "Copy description");
  el.querySelector(".copytags").onclick = (e) => copy(e.target, el._upload ? el._upload.tags.join(", ") : "", "Copy tags");
  setUpload(el, c.upload);
  return el;
}

function setUpload(el, up) {
  el._upload = up || null;
  const body = el.querySelector(".uptext-body");
  if (!up) { body.innerHTML = '<div class="msg">Writing the description...</div>'; return; }
  body.innerHTML = `<div class="msg" style="margin-top:6px">Description${up.by && up.by !== "built-in" ? " (written by " + esc(up.by) + ")" : ""}</div>
    <textarea readonly style="min-height:120px;font-size:12px">${esc(up.description)}</textarea>
    <div class="msg" style="margin-top:6px">Tags</div>
    <textarea readonly style="min-height:60px;font-size:12px">${esc(up.tags.join(", "))}</textarea>`;
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
  $("runPolicy").innerText = run.policy_note ? "YouTube rules: " + run.policy_note : ""; $("runPolicy").classList.toggle("hide", !run.policy_note);
  const eng = run.engines || {};
  const engText = [eng.transcribe && "Speech: " + eng.transcribe, eng.moments && "Moments picked by: " + eng.moments].filter(Boolean).join("  \u00b7  ");
  $("runEngines").innerText = engText; $("runEngines").classList.toggle("hide", !engText);
  let err = run.error || "";
  if (run.failed && run.failed.length) err += (err ? "\n" : "") + `Clip(s) ${run.failed.map((f) => f.n).join(", ")} couldn't be made: ${run.failed[run.failed.length - 1].error}`;
  $("runError").innerText = err; $("runError").classList.toggle("hide", !err);
  $("cancelBtn").classList.toggle("hide", !running);
  $("zipBtn").classList.toggle("hide", !run.clips.length);
  $("zipBtn").href = `/api/runs/${run.id}/zip`;
  $("zipBtn").innerText = running ? `Download finished (${run.clips.length}) as zip` : "Download all (zip)";

  // finished clips appear one by one, in place, without touching ones already shown (so playing videos keep playing)
  for (const c of run.clips) {
    if (shown.has(c.n)) {
      // the AI's description can arrive after the clip - refresh just that card's upload text
      const card = $("clips").querySelector(`.card[data-n="${c.n}"]`);
      if (card && c.upload && (!card._upload || card._upload.by !== c.upload.by)) setUpload(card, c.upload);
      continue;
    }
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

// ---------- Find viral videos ----------
function showTab(name) {
  for (const [tab, btn, id] of [["tabFind", "tabBtnFind", "find"], ["tabClips", "tabBtnClips", "clips"], ["tabRules", "tabBtnRules", "rules"], ["tabStats", "tabBtnStats", "stats"], ["tabPub", "tabBtnPub", "pub"]]) {
    $(tab).classList.toggle("hide", name !== id);
    $(btn).classList.toggle("on", name === id);
  }
  store.set("cf_tab", name);
}
document.querySelectorAll(".tabs button[data-tab]").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));

function fmtCount(n) {
  if (n == null) return "?";
  for (const [size, suf] of [[1e9, "B"], [1e6, "M"], [1e3, "K"]]) if (n >= size) return (n / size).toFixed(1).replace(/\.0$/, "") + suf;
  return String(Math.round(n));
}
function fmtAge(h) {
  if (h == null) return "";
  if (h < 1) return "just now";
  if (h < 24) return `${Math.round(h)} hour${Math.round(h) === 1 ? "" : "s"} ago`;
  const d = Math.round(h / 24);
  return `${d} day${d === 1 ? "" : "s"} ago`;
}
function fmtDur(s) {
  if (!s) return "";
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}

let trendData = null, trendTimer = null, dlTimer = null, knownDone = new Set();

function listKind() { return document.querySelector("input[name=listKind]:checked").value; }
async function loadStreamers() {
  const kind = listKind();
  const data = await api("/api/streamers?kind=" + kind);
  $("streamers").value = data.names.join("\n");
  const pod = kind === "podcasts";
  $("listLabel").innerText = pod ? "Your podcasts - one per line (their YouTube @name or channel link)" : "Your streamers - one per line (their YouTube @name or channel link)";
  $("scanBtn").innerText = pod ? "Scan my podcasts" : "Scan my streamers";
  $("podcastNote").classList.toggle("hide", !pod);
  $("incStreams").parentElement.classList.toggle("hide", pod);
  $("episodesOnly").checked = pod;
  // clips made from here use podcast settings when podcasts are picked
  if (pod && $("kind").value !== "podcast") { $("kind").value = "podcast"; applyKind(); }
  if (!pod && $("kind").value === "podcast") { $("kind").value = ""; applyKind(); }
}
document.querySelectorAll("input[name=listKind]").forEach((r) => (r.onchange = () => { store.set("cf_listKind", listKind()); loadStreamers(); }));
function applyKind() {
  if ($("kind").value === "podcast") {
    $("layout").value = "podcast"; $("minLen").value = 30; $("maxLen").value = 90;
    $("kindNote").innerText = "Podcast settings: split screen, 30-90 s clips, AI looks for hot takes, stories and debates.";
  } else {
    if ($("layout").value === "podcast") $("layout").value = "crop";
    $("minLen").value = 20; $("maxLen").value = 60;
    $("kindNote").innerText = "";
  }
  saveSettings();
}
$("kind").onchange = applyKind;

function renderTrends() {
  const st = trendData;
  if (!st) return;
  const busy = st.status === "running";
  $("scanBtn").disabled = busy; $("searchBtn").disabled = busy;
  $("trendMsg").innerHTML = busy ? esc(st.message || "Looking...") : st.status === "error" ? `<span class="error">${esc(st.error)}</span>` : "";
  const result = st.result;
  if (!result) { $("resultsPanel").classList.add("hide"); return; }
  $("resultsPanel").classList.remove("hide");
  $("resultsTitle").innerText = `${result.videos.length} videos - ${st.label || ""}${st.updated ? " (" + st.updated + ")" : ""}`;
  const failed = result.failed || [];
  $("failedMsg").innerText = failed.length ? "Couldn't load: " + failed.map((f) => `${f.name} (${f.error})`).join("; ") + " - check those names." : "";
  $("failedMsg").classList.toggle("hide", !failed.length);

  const sum = st.summary;
  $("askAi").disabled = st.summary_status === "running" || busy || !result.videos.length;
  $("askAi").innerText = st.summary_status === "running" ? "AI is thinking..." : "Ask AI what's hot";
  if (sum && (sum.trends.length || sum.picks.length)) {
    $("summary").innerHTML = `<div class="summary">
      ${sum.trends.length ? `<b>What's blowing up right now</b><ul>${sum.trends.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : ""}
      <b style="display:block;margin-top:8px">Best to clip</b><ul>${sum.picks.map((p) => `<li><b>#${p.n} ${esc(p.title)}</b> - ${esc(p.why)}</li>`).join("")}</ul>
      ${sum.source === "numbers" && sum.error ? `<div class="warn">No AI could answer (${esc(sum.error)}) - these picks are by the numbers.</div>` : `<div class="note">Answered by ${esc(sum.source)}</div>`}
    </div>`;
  } else { $("summary").innerHTML = ""; }

  const key = $("sortBy").value;
  const vids = result.videos.map((v, i) => ({ ...v, n: i + 1 }));
  if (key === "vs_normal") vids.sort((a, b) => (b.vs_normal || 0) - (a.vs_normal || 0));
  else if (key === "views") vids.sort((a, b) => (b.views || 0) - (a.views || 0));
  else if (key === "newest") vids.sort((a, b) => (a.age_hours ?? 1e9) - (b.age_hours ?? 1e9));
  $("vids").innerHTML = vids.length ? vids.map((v) => `
    <div class="vid">
      <div class="rank">#${v.n}</div>
      <a href="${esc(v.url)}" target="_blank" rel="noopener"><img src="${esc(v.thumb)}" alt="" loading="lazy"></a>
      <div class="info">
        <div class="t">${esc(v.title)}</div>
        <div class="meta">${esc(v.channel)}${v.was_live ? " &middot; past live stream" : ""}${v.duration ? " &middot; " + fmtDur(v.duration) : ""}${v.age_hours != null ? " &middot; " + fmtAge(v.age_hours) : ""}</div>
        <div class="stats">
          ${v.views_per_hour != null ? `<span class="tag hot">${fmtCount(v.views_per_hour)} views/hour</span>` : ""}
          ${v.vs_normal ? `<span class="tag ${v.vs_normal >= 2 ? "big" : ""}">${v.vs_normal}x their normal</span>` : ""}
          <span class="tag">${fmtCount(v.views)} views</span>
          ${permTag(v)}
        </div>
        <div class="actions">
          <a class="btn ghost" href="${esc(v.url)}" target="_blank" rel="noopener">Watch</a>
          <button class="ghost" data-dl="${esc(v.id)}">Download</button>
          <button data-dlclip="${esc(v.id)}">Download + make clips</button>
        </div>
      </div>
    </div>`).join("") : '<div class="msg">Nothing found in that time - try more days or other streamers.</div>';
  const byId = Object.fromEntries(result.videos.map((v) => [v.id, v]));
  $("vids").querySelectorAll("[data-dl]").forEach((b) => (b.onclick = () => startDownload(byId[b.dataset.dl].url, byId[b.dataset.dl].title, false, b)));
  $("vids").querySelectorAll("[data-dlclip]").forEach((b) => (b.onclick = () => {
    const v = byId[b.dataset.dlclip], pr = perms[v.perm_key];
    if (pr && pr.verdict === "not_allowed" && !confirm(`${v.channel} says not to reupload its videos:\n"${(pr.evidence || [])[0] || pr.summary}"\n\nClipping it can get your channel copyright strikes. Download and clip anyway?`)) return;
    startDownload(v.url, v.title, true, b);
  }));
  $("vids").querySelectorAll("[data-perm]").forEach((b) => (b.onclick = () => { b.disabled = true; b.innerText = "Checking..."; checkPerms([b.dataset.perm]); }));
}

async function pollTrends() {
  try { trendData = await api("/api/trends"); } catch (e) { return; }
  renderTrends();
  const busy = trendData.status === "running" || trendData.summary_status === "running";
  clearTimeout(trendTimer);
  if (busy) trendTimer = setTimeout(pollTrends, 1200);
}

async function trendAction(url, body) {
  try {
    await api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch (e) { $("trendMsg").innerHTML = `<span class="error">${esc(e.message)}</span>`; return; }
  pollTrends();
}

$("scanBtn").onclick = async () => {
  try {
    await api("/api/streamers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ names: $("streamers").value, kind: listKind() }) });
  } catch (e) {}
  trendAction("/api/trends/scan", { days: +$("days").value, include_streams: $("incStreams").checked, kind: listKind() });
};
$("searchBtn").onclick = () => trendAction("/api/trends/search", { query: $("searchInput").value, period: $("period").value, episodes_only: $("episodesOnly").checked });
$("searchInput").onkeydown = (e) => { if (e.key === "Enter") $("searchBtn").click(); };
$("sortBy").onchange = renderTrends;
$("askAi").onclick = () => trendAction("/api/trends/summary", { host: $("host").value, model: $("model").value });

async function startDownload(url, title, thenClip, button) {
  saveSettings();
  try {
    await api("/api/downloads", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, title, quality: $("quality").value, then_clip: thenClip, settings: clipSettings() }) });
    if (button) { button.innerText = thenClip ? "Added - see downloads above" : "Added to downloads"; button.disabled = true; }
    $("linkMsg").innerText = "";
  } catch (e) {
    if (button) alert(e.message); else $("linkMsg").innerHTML = `<span class="error">${esc(e.message)}</span>`;
  }
  pollDownloads();
  if (button) $("downloads").scrollIntoView({ behavior: "smooth", block: "center" });
}
$("linkDl").onclick = () => startDownload($("linkInput").value, "", false);
$("linkDlClip").onclick = () => startDownload($("linkInput").value, "", true);

async function pollDownloads() {
  let data;
  try { data = await api("/api/downloads"); } catch (e) { return; }
  $("downloads").innerHTML = data.downloads.map((d) => {
    const active = d.status === "queued" || d.status === "downloading";
    return `<div class="dl">
      <div class="row" style="justify-content:space-between">
        <b style="word-break:break-all">${esc(d.title)}</b>
        <span class="row">
          ${active ? `<button class="ghost" data-cancel="${d.id}" style="padding:5px 10px">Cancel</button>` : ""}
          ${d.status === "done" && d.clip_run ? `<button data-openrun="${esc(d.clip_run)}" style="padding:5px 10px">See the clips</button>` : ""}
          ${d.status === "done" && !d.auto_clip ? `<button data-useit="${esc(d.file)}" style="padding:5px 10px">Make clips from it</button>` : ""}
        </span>
      </div>
      ${active ? `<div class="bar"><div style="width:${d.percent}%"></div></div>` : ""}
      <div class="msg">${d.status === "error" ? `<span class="error">${esc(d.error)}</span>` : esc(d.message)}</div>
    </div>`;
  }).join("");
  $("downloads").querySelectorAll("[data-cancel]").forEach((b) => (b.onclick = () => api(`/api/downloads/${b.dataset.cancel}/cancel`, { method: "POST" }).then(pollDownloads)));
  $("downloads").querySelectorAll("[data-openrun]").forEach((b) => (b.onclick = () => openRun(b.dataset.openrun)));
  $("downloads").querySelectorAll("[data-useit]").forEach((b) => (b.onclick = async () => {
    await loadInputs(b.dataset.useit); $("pathInput").value = ""; showTab("clips"); window.scrollTo({ top: 0, behavior: "smooth" });
  }));
  let newFile = false;
  for (const d of data.downloads) if (d.status === "done" && !knownDone.has(d.id)) { knownDone.add(d.id); newFile = true; }
  if (newFile) { loadInputs(); loadRuns(); }
  clearTimeout(dlTimer);
  const waiting = data.downloads.some((d) => d.status === "queued" || d.status === "downloading" || (d.auto_clip && d.status === "done" && !d.clip_run && !/couldn't start/.test(d.message)));
  if (waiting) dlTimer = setTimeout(pollDownloads, 1500);
}

// ---------- Clipping permission ----------
let perms = {}, permTimer = null;
const PERM_LABEL = { allowed: ["big", "Clipping allowed"], not_allowed: ["no", "Says no reuploads"], unclear: ["maybe", "Clipping: unclear"], error: ["maybe", "Couldn't check"] };
function permTag(v) {
  const p = perms[v.perm_key];
  if (p) return `<span class="tag ${PERM_LABEL[p.verdict][0]}" title="${esc(p.summary)}">${PERM_LABEL[p.verdict][1]}</span>`;
  return v.channel_ref ? `<button class="ghost" data-perm="${esc(v.channel_ref)}" style="padding:2px 8px;font-size:12px">Can I clip this?</button>` : "";
}
function renderPerms(st) {
  perms = st.results || {};
  const busy = st.status === "running";
  $("permBtn").disabled = busy;
  $("permMsg").innerHTML = busy ? esc(st.message) : st.status === "error" ? `<span class="error">${esc(st.error)}</span>` : "";
  const items = Object.values(perms).sort((a, b) => (a.channel || a.name).localeCompare(b.channel || b.name));
  $("permPanel").classList.toggle("hide", !items.length && !busy);
  $("permList").innerHTML = items.map((p) => `<div class="perm">
      <span class="tag ${PERM_LABEL[p.verdict][0]}">${PERM_LABEL[p.verdict][1]}</span>
      <b style="margin-left:6px">${esc(p.channel || p.name)}</b> <span class="msg">&middot; ${esc(p.checked_on || "")}${p.by ? " &middot; " + esc(p.by) : ""}</span>
      <div style="margin-top:4px">${esc(p.summary)}</div>
      ${(p.evidence || []).map((q) => `<q>${esc(q)}</q>`).join("")}
      ${(p.conditions || []).length ? `<div class="msg">Their rules: ${p.conditions.map(esc).join("; ")}</div>` : ""}
      ${p.join_link ? `<div><a href="${esc(p.join_link)}" target="_blank" rel="noopener" style="color:var(--accent)">Join their clipping program &rarr;</a></div>` : ""}
    </div>`).join("");
  if (trendData) renderTrends();
}
async function pollPerms() {
  let st;
  try { st = await api("/api/permissions"); } catch (e) { return; }
  renderPerms(st);
  clearTimeout(permTimer);
  if (st.status === "running") permTimer = setTimeout(pollPerms, 1500);
}
async function checkPerms(names, force) {
  try {
    await api("/api/permissions/check", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ names, force: !!force, host: $("host").value, model: $("model").value }) });
  } catch (e) { $("permMsg").innerHTML = `<span class="error">${esc(e.message)}</span>`; }
  $("permPanel").classList.remove("hide");
  pollPerms();
}
$("permBtn").onclick = async () => {
  const names = $("streamers").value.split("\n").map((x) => x.trim()).filter(Boolean);
  if (!names.length) return;
  try { await api("/api/streamers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ names: $("streamers").value, kind: listKind() }) }); } catch (e) {}
  checkPerms(names);
  $("permPanel").scrollIntoView({ behavior: "smooth", block: "start" });
};

// ---------- YouTube rules ----------
const VERDICT_TEXT = { green: "Looks ad-friendly", yellow: "Risk of limited ads", red: "Risk of no ads, removal or a strike" };
function policyBadge(p) {
  if (!p) return "";
  return `<div class="verdict ${p.verdict}"><b>${VERDICT_TEXT[p.verdict]}</b>${(p.notes || []).map((n) => esc(n)).join("<br>")}</div>`;
}
function issueHtml(i) {
  return `<div class="issue ${esc(i.severity)}"><b>${esc(i.rule)}</b>${i.where ? " &middot; " + esc(i.where) : ""}${i.quote ? ` &middot; "<i>${esc(i.quote)}</i>"` : ""}
    <div>${esc(i.why)}</div>${i.fix ? `<div class="msg">Fix: ${esc(i.fix)}</div>` : ""}</div>`;
}
function policyBody() { return { title: $("pTitle").value, description: $("pDesc").value, text: $("pText").value, host: $("host").value, model: $("model").value }; }
let lastIssues = [];
async function runPolicyCheck(quickOnly) {
  $("pMsg").innerText = quickOnly ? "" : "The AI is reading it...";
  try {
    if (quickOnly) {
      const r = await api("/api/policy/scan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(policyBody()) });
      lastIssues = r.findings;
      $("pResult").innerHTML = `<div class="verdict ${r.verdict}"><b>${VERDICT_TEXT[r.verdict]} (instant check)</b></div>` +
        (r.findings.length ? r.findings.map(issueHtml).join("") : '<div class="msg">Nothing found by the instant check. For a full check, click AI review.</div>');
      return;
    }
    const r = await api("/api/policy/review", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(policyBody()) });
    const aiPart = r.ai.ok
      ? `<div class="msg" style="margin:8px 0">${esc(r.ai.summary)} <i>(checked by ${esc(r.ai.by)})</i></div>` + r.ai.issues.map(issueHtml).join("")
      : `<div class="warn">No AI could review it (${esc(r.ai.error)}) - only the instant check below.</div>`;
    lastIssues = [...r.scan.findings, ...(r.ai.ok ? r.ai.issues : [])];
    $("pResult").innerHTML = `<div class="verdict ${r.verdict}"><b>${VERDICT_TEXT[r.verdict]}</b></div>` + aiPart +
      (r.scan.findings.length ? `<div class="msg" style="margin-top:10px">Instant check:</div>` + r.scan.findings.map(issueHtml).join("") : "");
    $("pMsg").innerText = "";
  } catch (e) { $("pMsg").innerHTML = `<span class="error">${esc(e.message)}</span>`; }
}
$("pScan").onclick = () => runPolicyCheck(true);
$("pReview").onclick = () => runPolicyCheck(false);
$("pFix").onclick = async () => {
  $("pMsg").innerText = "The AI is rewriting it...";
  try {
    const r = await api("/api/policy/fix", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...policyBody(), issues: lastIssues }) });
    if (!r.ok) { $("pMsg").innerHTML = `<span class="error">No AI could rewrite it (${esc(r.error)}).</span>`; return; }
    if (r.title) $("pTitle").value = r.title;
    if (r.description) $("pDesc").value = r.description;
    if (r.script) $("pText").value = r.script;
    $("pMsg").innerText = "";
    $("pResult").innerHTML = `<div class="verdict ${r.check.verdict}"><b>Rewritten by ${esc(r.by)} - now: ${VERDICT_TEXT[r.check.verdict]}</b>${r.changes.map((c) => "&bull; " + esc(c)).join("<br>")}</div>
      ${r.check.findings.map(issueHtml).join("")}<div class="msg">The boxes above now hold the safe version - click AI review to double-check.</div>`;
  } catch (e) { $("pMsg").innerHTML = `<span class="error">${esc(e.message)}</span>`; }
};
$("yCheck").onclick = async () => {
  const r = await api("/api/policy/ypp", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subs: +$("ySubs").value, hours: +$("yHours").value, shorts: +$("yShorts").value, uploads: +$("yUploads").value }) });
  $("yResult").innerHTML = r.tiers.map((t) => `<div class="verdict ${t.met ? "green" : "yellow"}" style="margin-bottom:8px">
      <b>${t.met ? "&#10003;" : "&#10007;"} ${esc(t.name)}</b>${esc(t.unlocks)}<br><span style="opacity:.8">Needs: ${esc(t.needs)}</span>
      ${t.missing.length ? "<br>Still missing: " + t.missing.map(esc).join("; ") : "<br>You qualify - apply in YouTube Studio &rarr; Earn."}</div>`).join("") +
    `<div class="warn">${esc(r.note_2027)}</div><div class="msg" style="margin-top:6px">Also required: ${r.general.map(esc).join(" &middot; ")}</div>`;
};
let rulesBook = null;
async function loadRules() {
  rulesBook = await api("/api/rules");
  $("rulesAsOf").innerText = `Summary as of ${rulesBook.as_of}. ${rulesBook.note}`;
  $("qList").innerHTML = rulesBook.questions.map(([id, q]) => `<label class="check"><input type="checkbox" data-q="${esc(id)}"> ${esc(q)}</label>`).join("");
  $("rulesList").innerHTML = rulesBook.rules.map((r) => `<div class="rule">
      <h3>${esc(r.title)}</h3><div class="area">${esc(r.area)}</div>
      <div>${esc(r.summary)}</div>
      <div class="msg" style="margin-top:4px"><b>What happens:</b> ${esc(r.consequence)}</div>
      <ul>${r.safe.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      <div class="msg">Sources: ${r.sources.map((u) => `<a href="${esc(u)}" target="_blank" rel="noopener" style="color:var(--dim)">${esc(u.replace(/^https?:\/\/(www\.)?/, "").slice(0, 45))}</a>`).join(" &middot; ")}</div>
    </div>`).join("");
}
$("qCheck").onclick = async () => {
  const answers = {};
  document.querySelectorAll("[data-q]").forEach((c) => (answers[c.dataset.q] = c.checked));
  const r = await api("/api/policy/channel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answers }) });
  $("qResult").innerHTML = r.risks.map((x) => `<div class="verdict ${x.level}" style="margin-bottom:8px"><b>${esc(x.rule)}</b>${esc(x.text)}</div>`).join("");
};
$("updBtn").onclick = async () => {
  $("updResult").innerHTML = '<div class="msg">Reading YouTube\'s official policy pages...</div>';
  try {
    const r = await api("/api/policy/updates", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ host: $("host").value, model: $("model").value }) });
    const icon = { same: "&#10003; no change", changed: "&#9888; CHANGED", saved: "saved", error: "&#10007; couldn't load" };
    $("updResult").innerHTML = (r.summary ? `<div class="verdict yellow" style="margin-bottom:10px"><b>What changed (explained by ${esc(r.summary.by)})</b>${r.summary.points.map((x) => "&bull; " + esc(x)).join("<br>")}</div>` : "") +
      r.pages.map((pg) => `<div class="issue ${pg.status === "changed" ? "yellow" : pg.status === "error" ? "red" : "info"}">
        <b>${icon[pg.status]}</b> &middot; <a href="${esc(pg.url)}" target="_blank" rel="noopener" style="color:var(--accent)">${esc(pg.name)}</a>
        <div class="msg" style="white-space:pre-wrap">${esc(pg.detail).slice(0, 1500)}</div></div>`).join("");
  } catch (e) { $("updResult").innerHTML = `<div class="error">${esc(e.message)}</div>`; }
};

// ---------- Publish ----------
let pubData = null, pubTimer = null;
const chColor = (cid) => { const list = statsData ? statsData.config.channels : (pubData ? pubData.channels : []); const i = list.findIndex((c) => c.id === cid); return i >= 0 ? CH_COLORS[i] : "#555"; };
const postJson = (url, body) => api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
async function loadPub() {
  try { pubData = await api("/api/publish"); } catch (e) { return; }
  renderPub();
  clearTimeout(pubTimer);
  if (pubData.connecting || pubData.uploading || pubData.queue.some((q) => q.status === "uploading")) pubTimer = setTimeout(loadPub, 2000);
}
async function loadPubSources() {
  if (!pubData) await loadPub();
  let src;
  try { src = await api("/api/publish/sources"); } catch (e) { return; }
  $("addRun").innerHTML = src.runs.length ? src.runs.map((r) => `<option value="${esc(r.id)}">${esc(r.video)} (${r.clips} clips, ${esc(r.created || "")})</option>`).join("") : '<option value="">No clips made yet</option>';
  const fresh = src.wayne.filter((w) => !w.queued);
  window._wayne = fresh;
  const opts = (sel) => pubData.channels.map((c) => `<option value="${esc(c.id)}" ${c.id === sel ? "selected" : ""}>${esc(c.name)}</option>`).join("");
  $("wayneList").innerHTML = fresh.length ? fresh.map((w, i) => `<div class="row" style="padding:6px 0;border-top:1px solid var(--line)">
      <span style="flex:1 1 260px;min-width:0"><b style="color:var(--text)">${esc(w.title)}</b><br><span class="msg">${w.kind === "short" ? "Short" : "Full video"} · ${esc(w.source)}</span></span>
      <select data-wch="${i}" style="width:auto"><option value="">Channel...</option>${opts(w.cid)}</select>
      <button class="ghost" data-wadd="${i}" style="padding:6px 12px">Add</button></div>`).join("") : "No new finished videos found in Wayne Factory's content folders.";
  $("wayneList").querySelectorAll("[data-wadd]").forEach((b) => (b.onclick = () => addWayne([+b.dataset.wadd])));
  $("addAllWayne").disabled = !fresh.length;
}
async function addWayne(idxs) {
  const items = idxs.map((i) => ({ ...window._wayne[i], cid: document.querySelector(`[data-wch="${i}"]`).value }));
  if (items.some((it) => !it.cid)) { $("addMsg").innerHTML = '<span class="error">Pick a channel for each video first.</span>'; return; }
  const r = await postJson("/api/publish/add", { wayne: items });
  $("addMsg").innerText = `Added ${r.added}. Click "Fill the schedule" to give them times.`;
  await loadPub(); loadPubSources();
}
$("addAllWayne").onclick = () => addWayne(window._wayne.map((_, i) => i));
$("addRunBtn").onclick = async () => {
  if (!$("addRun").value) return;
  try {
    const r = await postJson("/api/publish/add", { run_id: $("addRun").value, cid: $("addRunCh").value });
    $("addMsg").innerText = r.added ? `Added ${r.added} clips. Click "Fill the schedule" to give them times.` : "Those clips are already in the schedule.";
  } catch (e) { $("addMsg").innerHTML = `<span class="error">${esc(e.message)}</span>`; }
  loadPub();
};
const STATUS_TXT = (d, it) => ({ waiting: d.approved ? "Waiting to upload" : "To do", uploading: `Uploading ${it.progress || 0}%`,
  uploaded: "Uploaded", scheduled: "Scheduled by you", failed: "Failed" }[it.status] || it.status);
function renderPub() {
  const d = pubData;
  const secretOk = !!d.client_secret;
  $("st1n").className = "n" + (secretOk ? " ok" : ""); $("st1n").innerHTML = secretOk ? "&#10003;" : "1";
  $("st1msg").innerHTML = secretOk ? `Found: <code style="word-break:break-all">${esc(d.client_secret)}</code>` : "Not found yet - follow the steps below.";
  const wanted = d.channels.filter((c) => c.ref), connected = d.channels.filter((c) => c.connected && !c.connected.mismatch);
  const allConn = wanted.length > 0 && wanted.every((c) => c.connected && !c.connected.mismatch);
  $("st2n").className = "n" + (allConn ? " ok" : ""); $("st2n").innerHTML = allConn ? "&#10003;" : "2";
  $("connList").innerHTML = d.channels.map((c) => {
    const k = c.connected;
    const st = d.connecting === c.id ? '<span class="msg">Waiting for the Google login in your browser...</span>'
      : k ? (k.mismatch ? `<span class="error">Logged in as "${esc(k.title)}" (${esc(k.handle)}) - that's not this channel. Connect again and pick ${esc(c.name)}.</span>`
                        : `<span style="color:var(--ok)">&#10003; Connected as ${esc(k.title)} ${esc(k.handle || "")}</span>`)
      : '<span class="msg">Not connected</span>';
    return `<div class="conn"><b>${esc(c.name)}</b>${st}<button class="ghost" data-conn="${esc(c.id)}" style="padding:5px 12px" ${secretOk && !d.connecting ? "" : "disabled"}>${k ? "Reconnect" : "Connect"}</button>${k ? `<button class="ghost" data-disc="${esc(c.id)}" style="padding:5px 12px">Disconnect</button>` : ""}</div>`;
  }).join("");
  $("connErr").innerText = d.connect_error || ""; $("connErr").classList.toggle("hide", !d.connect_error);
  $("connList").querySelectorAll("[data-conn]").forEach((b) => (b.onclick = async () => {
    try { await postJson("/api/publish/connect", { cid: b.dataset.conn }); } catch (e) { $("connErr").innerText = e.message; $("connErr").classList.remove("hide"); }
    loadPub();
  }));
  $("connList").querySelectorAll("[data-disc]").forEach((b) => (b.onclick = async () => { pubData = await postJson("/api/publish/disconnect", { cid: b.dataset.disc }); renderPub(); }));
  $("approvedChk").checked = d.approved;
  $("st3n").className = "n" + (d.approved ? " ok" : ""); $("st3n").innerHTML = d.approved ? "&#10003;" : "3";
  const keep = $("addRunCh").value;
  $("addRunCh").innerHTML = d.channels.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join("");
  $("addRunCh").value = keep || (d.channels.find((c) => c.id === "clips") || d.channels[0] || {}).id || "";
  $("quotaMsg").innerText = d.approved ? `YouTube quota today: ${d.quota.uploads_left} uploads left` : "";
  $("slotsMsg").innerHTML = "Weekly plan: " + d.channels.map((c) => `<b>${esc(c.name)}</b> ` + c.slots.map((r) => `${r.kind === "long" ? "full video" : "Short"} ${r.days.length === 7 ? "daily" : r.days.map((x) => d.weekdays[x]).join("/")} ${r.time}`).join(", ")).join(" · ");
  $("modeBanner").innerHTML = d.approved
    ? '<div class="banner auto">Automatic: each video is uploaded up to 3 days before its time, and YouTube publishes it at that time by itself. Open Clip Factory at least every couple of days so it can upload.</div>'
    : '<div class="banner manual">Until Google approves, post each item yourself: click <b>Show file</b>, upload it in YouTube Studio, paste the title, description and tags with the copy buttons, set <b>Schedule</b> to the time shown, then click <b>Scheduled</b>. Tip: do the whole week in one sitting on Sunday.</div>';
  let html = "", day = null;
  if (!d.queue.length) html = '<div class="msg">Nothing in the schedule yet - add clips or videos above.</div>';
  for (const it of d.queue) {
    const dlabel = it.when ? new Date(it.when).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" }) : "No time yet - click Fill the schedule";
    if (dlabel !== day) { day = dlabel; html += `<div class="qday">${esc(dlabel)}</div>`; }
    const done = it.status === "uploaded" || it.status === "scheduled";
    const ch = d.channels.find((c) => c.id === it.cid) || {};
    const studio = ch.connected ? `https://studio.youtube.com/channel/${encodeURIComponent(ch.connected.id)}/videos/upload` : "https://studio.youtube.com/";
    html += `<div class="qitem" data-q="${esc(it.id)}">
      <div class="time">${it.when ? esc(it.when.slice(11, 16)) : "--:--"}</div>
      <div style="min-width:0">
        <div><span class="tag" style="background:${chColor(it.cid)};color:#fff">${esc(it.channel)}</span> <span class="tag">${it.kind === "long" ? "Full video" : "Short"}</span>
          <span class="tag ${done ? "big" : it.status === "failed" ? "no" : "maybe"}">${esc(STATUS_TXT(d, it))}</span></div>
        <div style="font-weight:700;margin-top:4px">${esc(it.title)}</div>
        <div class="msg" style="font-size:12px">${esc(it.source)}${it.missing ? ' · <span class="error">file missing</span>' : ""}</div>
        ${it.error ? `<div class="${it.status === "failed" ? "error" : "msg"}" style="font-size:12px">${esc(it.error)}</div>` : ""}
        ${it.url ? `<a href="${esc(it.url)}" target="_blank" rel="noopener" style="color:var(--accent);font-size:13px">${esc(it.url)}</a>` : ""}
        <div class="acts">
          <button class="ghost" data-cp="title">Copy title</button><button class="ghost" data-cp="description">Copy description</button><button class="ghost" data-cp="tags">Copy tags</button>
          <button class="ghost" data-act="reveal">Show file</button>
          ${!d.approved && !done ? `<a class="btn ghost" href="${studio}" target="_blank" rel="noopener">Open YouTube Studio</a><button data-act="scheduled">Scheduled</button>` : ""}
          ${d.approved && it.status !== "uploaded" && it.status !== "uploading" ? `<button data-act="upload">Upload now</button>` : ""}
          ${!d.approved && it.status === "waiting" && ch.connected ? `<button class="ghost" data-act="test">Test upload (private)</button>` : ""}
          ${it.status === "failed" || it.status === "scheduled" ? `<button class="ghost" data-act="retry">Back to to-do</button>` : ""}
          <select data-act="cid" style="width:auto;padding:4px 6px;font-size:12px" aria-label="Channel">${d.channels.map((c) => `<option value="${esc(c.id)}" ${c.id === it.cid ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select>
          <input type="datetime-local" data-act="when" value="${esc(it.when || "")}" style="width:auto;padding:4px 6px;font-size:12px" aria-label="Publish time">
          <button class="ghost" data-act="remove">Remove</button>
        </div>
      </div></div>`;
  }
  $("queueList").innerHTML = html;
  const byId = Object.fromEntries(d.queue.map((i) => [i.id, i]));
  $("queueList").querySelectorAll(".qitem").forEach((el) => {
    const it = byId[el.dataset.q];
    el.querySelectorAll("[data-cp]").forEach((b) => (b.onclick = async () => {
      const text = b.dataset.cp === "tags" ? it.tags.join(", ") : it[b.dataset.cp];
      try { await navigator.clipboard.writeText(text); b.innerText = "Copied"; } catch (e) { b.innerText = "Can't copy"; }
      setTimeout(() => (b.innerText = { title: "Copy title", description: "Copy description", tags: "Copy tags" }[b.dataset.cp]), 1500);
    }));
    el.querySelectorAll("[data-act]").forEach((b) => {
      const act = b.dataset.act;
      if (act === "when" || act === "cid") { b.onchange = async () => { pubData = await postJson(`/api/publish/item/${it.id}`, { [act]: b.value }); renderPub(); }; return; }
      b.onclick = async () => {
        try {
          if (act === "reveal") { await postJson("/api/publish/reveal", { id: it.id }); b.innerText = "Opened"; return; }
          if (act === "scheduled") pubData = await postJson(`/api/publish/item/${it.id}`, { status: "scheduled" });
          if (act === "retry") pubData = await postJson(`/api/publish/item/${it.id}`, { status: "waiting" });
          if (act === "remove") pubData = await postJson(`/api/publish/item/${it.id}/remove`);
          if (act === "upload" || act === "test") { await postJson(`/api/publish/item/${it.id}/upload`, { test: act === "test" }); return loadPub(); }
          renderPub();
        } catch (e) { b.innerText = e.message.slice(0, 60); }
      };
    });
  });
}
$("fillBtn").onclick = async () => { const r = await api("/api/publish/fill", { method: "POST" }); await loadPub(); $("fillBtn").innerText = `Filled ${r.filled}`; setTimeout(() => ($("fillBtn").innerText = "Fill the schedule"), 1800); };
$("approvedChk").onchange = async () => { pubData = await postJson("/api/publish/approved", { approved: $("approvedChk").checked }); renderPub(); };
$("auditBtn").onclick = async () => { const r = await api("/api/publish/audit"); $("auditText").value = r.text; $("auditBox").classList.toggle("hide"); };
$("auditCopy").onclick = async () => { try { await navigator.clipboard.writeText($("auditText").value); $("auditCopy").innerText = "Copied"; } catch (e) { $("auditText").select(); } };
$("tabBtnPub").addEventListener("click", () => { loadPubSources(); });

// ---------- My channels ----------
const CH_COLORS = ["#3987e5", "#d95926", "#199e70", "#9085e9", "#c98500", "#d55181", "#008300", "#e66767"];
let statsData = null, statsTimer = null, chartTable = false;
const fmtN = (n) => (n == null ? "-" : Number(n).toLocaleString("en-US"));
function pct(a, b) { if (a == null || b == null || b === 0) return ""; const p = Math.round(((a - b) / b) * 100); return `<span class="${p >= 0 ? "up" : "down"}">${p >= 0 ? "+" : ""}${p}%</span>`; }
async function loadStats() {
  try { statsData = await api("/api/stats"); } catch (e) { return; }
  renderStats();
  clearTimeout(statsTimer);
  if (statsData.refreshing) statsTimer = setTimeout(loadStats, 2500);
}
function renderStats() {
  const d = statsData, g = d.goal, t = d.totals;
  const configured = d.channels.filter((c) => c.ref);
  if (!configured.length) $("statsSetup").classList.remove("hide");
  $("statsMsg").innerHTML = d.refreshing ? "Checking your channels..." : d.latest_at ? `Last checked ${esc(d.latest_at.replace("T", " "))}` : "";
  $("statsSource").innerText = !configured.length ? "Add your channels to start tracking." :
    (d.source === "api" ? `Exact numbers from the YouTube API (key ${d.key_where}).` : "Numbers read from your channel pages (rounded by YouTube, e.g. 1.2K). Add an API key in Channels & goal for exact numbers.") +
    (d.first_at && new Date(d.first_at) > new Date(Date.now() - 7 * 864e5) ? ` Tracking started ${d.first_at.slice(0, 10)}, so "this week" covers the days since then.` : "");
  // setup form
  $("chanRows").innerHTML = d.config.channels.map((c, i) => `<div class="chrow">
      <input type="text" id="chName${i}" value="${esc(c.name)}" aria-label="Channel ${i + 1} name">
      <input type="text" id="chRef${i}" value="${esc(c.ref)}" placeholder="@handle or channel link" aria-label="Channel ${i + 1} handle">
    </div>`).join("");
  $("goalViews").value = d.config.goal_views; $("goalStart").value = d.config.start; $("goalEnd").value = d.config.deadline;
  $("ytKeyState").innerText = d.config.api_key_set ? "Saved." : d.key_where ? `Using the key ${d.key_where}.` : "None - the public channel pages are used.";
  // KPIs
  const done = Math.min(100, (g.done / g.views) * 100);
  const weekCard = d.have_week
    ? `<div class="kpi"><span class="lbl">Views this week</span><span class="big">${fmtN(t.week)}</span><span class="sub">${d.have_prev ? `${pct(t.week, t.prev_week)} vs last week (${fmtN(t.prev_week)})` : "Last week: not tracked yet"}</span></div>`
    : `<div class="kpi"><span class="lbl">Views on videos posted in the last 7 days</span><span class="big">${fmtN(configured.length && d.snapshots ? t.new_week_views : null)}</span><span class="sub">${fmtN(t.new_week_videos)} new videos. Views gained per week appear after the next check (every 3 hours while the app is open).</span></div>`;
  $("kpis").innerHTML = `
    <div class="kpi"><span class="lbl">All channels together</span><span class="big">${fmtN(d.snapshots ? t.all_time : null)}</span><span class="sub">total views · ${fmtN(d.snapshots ? t.subs : null)} subscribers</span></div>
    ${weekCard}
    <div class="kpi"><span class="lbl">Goal: ${fmtN(g.views)} views by ${esc(g.deadline)}</span><span class="big">${fmtN(g.done)}</span>
      <div class="goalbar"><div style="width:${done}%"></div></div><span class="sub">${done.toFixed(done < 1 ? 2 : 1)}% done · ${g.days_left} days left</span></div>
    <div class="kpi"><span class="lbl">Needed per day</span><span class="big">${fmtN(g.needed_per_day)}</span><span class="sub">Your pace this week: ${g.pace_per_day == null ? "-" : fmtN(g.pace_per_day) + " a day"}</span></div>
    <div class="kpi"><span class="lbl">At this pace, by ${esc(g.deadline)}</span><span class="big">${fmtN(g.projection)}</span><span class="sub">${g.projection == null ? "Needs a day of data" : g.projection >= g.views ? '<span class="up">On track for the goal</span>' : `<span class="down">${fmtN(g.views - g.projection)} short of the goal</span>`}</span></div>`;
  renderChart();
  // channel table
  $("chanTable").innerHTML = `<thead><tr><th>Channel</th><th class="r">Subscribers</th><th class="r">Total views</th><th class="r">This week</th><th class="r">Last week</th><th class="r">Shorts / long</th><th>Best video this week</th></tr></thead><tbody>` +
    d.channels.map((c, i) => c.ref ? `<tr>
      <td><span class="tag" style="background:${CH_COLORS[i]};color:#fff;padding:1px 6px">&nbsp;</span> <b>${esc(c.name)}</b>${c.error ? `<div class="error" style="font-size:12px">${esc(c.error)}</div>` : ""}</td>
      <td class="r">${fmtN(c.subs)}<div class="msg" style="font-size:12px">${c.subs != null ? Math.min(100, Math.round((c.subs / 1000) * 100)) + "% of 1,000" : ""}</div></td>
      <td class="r">${fmtN(c.views)}<div class="msg" style="font-size:12px">${c.videos != null ? fmtN(c.videos) + " videos" : ""}</div></td>
      <td class="r">${c.week != null ? fmtN(c.week) + " " + pct(c.week, c.prev_week) : `<span class="msg">after next check</span>`}${c.new_week_videos ? `<div class="msg" style="font-size:12px">${c.new_week_videos} new: ${fmtN(c.new_week_views)} views</div>` : ""}</td><td class="r">${fmtN(c.prev_week)}</td>
      <td class="r">${c.week != null ? fmtN(c.week_shorts) + " / " + fmtN(c.week_long) : "-"}</td>
      <td>${c.best ? `<a href="https://www.youtube.com/watch?v=${esc(c.best.id)}" target="_blank" rel="noopener" style="color:var(--text)">${esc(c.best.title)}</a> <span class="msg">+${fmtN(c.best.gain)}</span>` : '<span class="msg">-</span>'}</td>
    </tr>` : `<tr><td><b>${esc(c.name)}</b></td><td colspan="6" class="msg">No @handle yet - add it in Channels &amp; goal</td></tr>`).join("") + "</tbody>";
  $("topTitle").innerText = d.top.length ? "Top videos this week" : "Most viewed recent videos";
  const recent = d.recent_top || [];
  $("topVids").innerHTML = !d.top.length && recent.length ? recent.map((v, i) => `<div style="display:flex;gap:10px;padding:7px 0;border-top:${i ? "1px solid var(--line)" : "0"}">
      <b style="color:var(--accent);width:22px">${i + 1}</b>
      <div style="min-width:0"><a href="https://www.youtube.com/watch?v=${esc(v.id)}" target="_blank" rel="noopener" style="color:var(--text)">${esc(v.title)}</a>
      <div class="msg">${esc(v.channel)} · ${v.short ? "Short" : "Video"} · ${fmtN(v.views)} views${v.posted ? " · posted " + esc(v.posted) : ""}</div></div></div>`).join("") :
    d.top.length ? d.top.map((v, i) => `<div style="display:flex;gap:10px;padding:7px 0;border-top:${i ? "1px solid var(--line)" : "0"}">
      <b style="color:var(--accent);width:22px">${i + 1}</b>
      <div style="min-width:0"><a href="https://www.youtube.com/watch?v=${esc(v.id)}" target="_blank" rel="noopener" style="color:var(--text)">${esc(v.title)}</a>
      <div class="msg">${esc(v.channel)} · ${v.short ? "Short" : "Video"} · +${fmtN(v.gain)} views this week</div></div></div>`).join("") :
    '<div class="msg">Shows up after the first day of tracking.</div>';
  if (!$("coach").innerHTML) loadCoach(false);
}
function renderChart() {
  const d = statsData, chans = d.channels.map((c, i) => ({ ...c, color: CH_COLORS[i] })).filter((c) => c.ref);
  $("chartLegend").innerHTML = chans.map((c) => `<span><i style="background:${c.color}"></i>${esc(c.name)}</span>`).join("");
  const rows = d.days.map((r) => ({ date: r.date, parts: chans.map((c) => ({ c, v: r[c.id] || 0 })), any: chans.some((c) => r[c.id] != null) }));
  const max = Math.max(1, ...rows.map((r) => r.parts.reduce((a, p) => a + p.v, 0)));
  const nice = (m) => { const e = Math.pow(10, Math.floor(Math.log10(m))); return [1, 2, 2.5, 5, 10].map((f) => f * e).find((x) => x >= m); };
  const top = nice(max), W = 720, H = 250, L = 56, R = 8, T = 10, B = 28, bw = (W - L - R) / rows.length;
  const y = (v) => T + (H - T - B) * (1 - v / top);
  let svg = "";
  for (let k = 0; k <= 4; k++) {
    const v = (top / 4) * k, yy = y(v);
    svg += `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" stroke="#2c303b" stroke-width="1"/>`;
    svg += `<text x="${L - 8}" y="${yy + 4}" fill="#9a9fad" font-size="11" text-anchor="end">${v >= 1e6 ? v / 1e6 + "M" : v >= 1e3 ? v / 1e3 + "K" : v}</text>`;
  }
  rows.forEach((r, i) => {
    const x = L + i * bw + bw * 0.18, w = bw * 0.64;
    let acc = 0;
    const visible = r.parts.filter((p) => p.v > 0);
    visible.forEach((p, k) => {
      const y1 = y(acc + p.v), y0 = y(acc);
      const h = Math.max(0, y0 - y1 - (k ? 2 : 0));  // 2px gap between stacked segments
      const last = k === visible.length - 1, rad = last ? Math.min(4, h / 2, w / 2) : 0;
      svg += rad ? `<path d="M${x},${y1 + h} V${y1 + rad} Q${x},${y1} ${x + rad},${y1} H${x + w - rad} Q${x + w},${y1} ${x + w},${y1 + rad} V${y1 + h} Z" fill="${p.c.color}"/>`
                 : `<rect x="${x}" y="${y1}" width="${w}" height="${h}" fill="${p.c.color}"/>`;
      acc += p.v;
    });
    if (i % 2 === rows.length % 2 || rows.length < 8) svg += `<text x="${x + w / 2}" y="${H - 8}" fill="#9a9fad" font-size="11" text-anchor="middle">${r.date.slice(5).replace("-", "/")}</text>`;
    svg += `<rect class="hit" data-i="${i}" x="${L + i * bw}" y="${T}" width="${bw}" height="${H - T - B}" fill="transparent"/>`;
  });
  $("chart").innerHTML = svg;
  const tip = $("chartTip");
  $("chart").querySelectorAll(".hit").forEach((h) => {
    h.onmousemove = (e) => {
      const r = rows[+h.dataset.i], box = $("chartWrap").getBoundingClientRect();
      tip.innerHTML = `<b>${r.date}</b><br>` + (r.any ? r.parts.map((p) => `<span style="color:${p.c.color}">&#9632;</span> ${esc(p.c.name)}: ${fmtN(p.v)}`).join("<br>") + `<br><b>Total: ${fmtN(r.parts.reduce((a, p) => a + p.v, 0))}</b>` : "Not tracked");
      tip.classList.remove("hide");
      const left = Math.min(e.clientX - box.left + 12, box.width - tip.offsetWidth - 4);
      tip.style.left = left + "px"; tip.style.top = Math.max(0, e.clientY - box.top - tip.offsetHeight - 8) + "px";
    };
    h.onmouseleave = () => tip.classList.add("hide");
  });
  $("chartTable").innerHTML = `<table class="tbl"><thead><tr><th>Day</th>${chans.map((c) => `<th class="r">${esc(c.name)}</th>`).join("")}<th class="r">Total</th></tr></thead><tbody>` +
    rows.map((r) => `<tr><td>${r.date}</td>${r.parts.map((p) => `<td class="r">${r.any ? fmtN(p.v) : "-"}</td>`).join("")}<td class="r">${r.any ? fmtN(r.parts.reduce((a, p) => a + p.v, 0)) : "-"}</td></tr>`).join("") + "</tbody></table>";
}
async function loadCoach(useAi) {
  $("coach").innerHTML = '<div class="msg">' + (useAi ? "The AI coach is reading your numbers..." : "") + "</div>";
  try {
    const c = await api("/api/stats/coach", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ use_ai: useAi, host: $("host").value, model: $("model").value }) });
    $("coach").innerHTML = `<div style="font-weight:700;margin-bottom:6px">${esc(c.headline)}</div><ul style="margin:0;padding-left:18px">${c.actions.map((a) => `<li style="margin:4px 0">${esc(a)}</li>`).join("")}</ul><div class="msg" style="margin-top:6px">By ${esc(c.by)}</div>`;
  } catch (e) { $("coach").innerHTML = `<div class="error">${esc(e.message)}</div>`; }
}
$("coachBtn").onclick = () => loadCoach(true);
$("statsSetupBtn").onclick = () => $("statsSetup").classList.toggle("hide");
$("chartAsTable").onclick = () => { chartTable = !chartTable; $("chartTable").classList.toggle("hide", !chartTable); $("chartWrap").classList.toggle("hide", chartTable); $("chartAsTable").innerText = chartTable ? "Show as chart" : "Show as table"; };
$("statsRefresh").onclick = async () => {
  try { await api("/api/stats/refresh", { method: "POST" }); } catch (e) { $("statsMsg").innerHTML = `<span class="error">${esc(e.message)}</span>`; return; }
  loadStats();
};
$("statsSave").onclick = async () => {
  const channels = statsData.config.channels.map((c, i) => ({ id: c.id, name: $("chName" + i).value, ref: $("chRef" + i).value }));
  try {
    statsData = await api("/api/stats/config", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channels, goal_views: +$("goalViews").value, start: $("goalStart").value, deadline: $("goalEnd").value, api_key: $("ytKey").value || null }) });
    $("ytKey").value = "";
    $("statsSaveMsg").innerText = "Saved.";
    if (channels.some((c) => c.ref.trim())) { await api("/api/stats/refresh", { method: "POST" }); }
    loadStats();
  } catch (e) { $("statsSaveMsg").innerHTML = `<span class="error">${esc(e.message)}</span>`; }
};

// ---------- AI engines ----------
const AI_LINKS = {
  gemini: ["https://aistudio.google.com/apikey", "AIza..."], groq: ["https://console.groq.com/keys", "gsk_..."],
  openrouter: ["https://openrouter.ai/settings/keys", "sk-or-..."], anthropic: ["https://console.anthropic.com/settings/keys", "sk-ant-..."],
  openai: ["https://platform.openai.com/api-keys", "sk-..."], xai: ["https://console.x.ai", "xai-..."],
};
let aiState = null;
function renderAi(st) {
  aiState = st;
  $("cloudOn").checked = st.cloud_on;
  if (!$("aiKeys").children.length) {
    $("aiKeys").innerHTML = st.providers.map((p) => `
      <div>
        <label>${esc(p.label)} key &middot; <span class="tag ${p.free ? "big" : ""}" style="padding:1px 6px">${p.free ? "free" : "paid"}</span> &middot;
          <a href="${AI_LINKS[p.id][0]}" target="_blank" rel="noopener" style="color:var(--accent)">get a key</a></label>
        <input type="text" id="key_${p.id}" autocomplete="off" spellcheck="false" placeholder="${AI_LINKS[p.id][1]}">
        <div class="msg" id="state_${p.id}"></div>
      </div>`).join("");
  }
  for (const p of st.providers) {
    $("state_" + p.id).innerHTML = p.set ? `Saved (${esc(p.hint)}) &middot; <a href="#" data-clear="${p.id}" style="color:var(--dim)">remove</a>` : "Not set";
  }
  $("aiKeys").querySelectorAll("[data-clear]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); saveAi({ ["clear_" + a.dataset.clear + "_key"]: true }); }));
  const names = st.providers.filter((p) => p.set).map((p) => p.label);
  $("aiToggle").innerText = st.cloud_on && names.length ? `AI engines: ${names.join(" + ")} + this PC` : "AI engines: this PC only - make it faster";
  $("aiToggle").classList.toggle("ghost", !!(st.cloud_on && names.length));
}
async function loadAi() { try { renderAi(await api("/api/ai")); } catch (e) {} }
async function saveAi(extra) {
  $("aiMsg").innerText = "";
  const body = { cloud_on: $("cloudOn").checked, ...(extra || {}) };
  for (const p of aiState.providers) body[p.id + "_key"] = $("key_" + p.id).value;
  try {
    const st = await api("/api/ai", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    for (const p of st.providers) $("key_" + p.id).value = "";
    renderAi(st);
    $("aiMsg").innerText = "Saved.";
    return true;
  } catch (e) { $("aiMsg").innerHTML = `<span class="error">${esc(e.message)}</span>`; return false; }
}
$("aiToggle").onclick = () => $("aiPanel").classList.toggle("hide");
$("aiSave").onclick = () => saveAi();
$("cloudOn").onchange = () => saveAi();
$("aiTest").onclick = async () => {
  if (!(await saveAi())) return;
  $("aiMsg").innerText = "Testing...";
  try {
    const r = await api("/api/ai/test", { method: "POST" });
    const labels = Object.fromEntries(aiState.providers.map((p) => [p.id, p.label]));
    const parts = Object.entries(r).map(([id, v]) => `${esc(labels[id] || id)}: ${v.startsWith("ok") ? `<span style="color:var(--ok)">${esc(v)}</span>` : `<span class="error">${esc(v)}</span>`}`);
    $("aiMsg").innerHTML = parts.length ? parts.join(" &nbsp; ") : "Add at least one key first.";
  } catch (e) { $("aiMsg").innerHTML = `<span class="error">${esc(e.message)}</span>`; }
};

(async () => {
  loadSettings();
  const savedKind = store.get("cf_listKind");
  if (savedKind) { const r = document.querySelector(`input[name=listKind][value=${savedKind}]`); if (r) r.checked = true; }
  loadAi();
  loadRules();
  showTab(store.get("cf_tab") || "find");
  await loadStatus();
  await Promise.all([loadInputs(), loadModels(), loadRuns(), loadStreamers(), pollTrends(), pollDownloads(), pollPerms(), loadStats(), loadPub()]);
  if (store.get("cf_tab") === "pub") loadPubSources();
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    _load_last_trends()
    channel_stats.start_background()
    publisher.start_background()
    INPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"Clip Factory running - open http://localhost:{PORT}")
    print(f"Tip: put long videos in {INPUT_DIR} and they show up in the list.")
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
