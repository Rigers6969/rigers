"""Autopilot: makes and uploads the documentary channels' videos by itself.

Once a day, at the time you pick, for every channel that is switched on and
due a new video:
  1. Research  - researcher.py finds today's best fresh topic for the channel
                 (one it hasn't used before)
  2. Produce   - producer.py writes the script, records the voice-over, finds
                 footage, assembles the video, adds captions/music
  3. Upload    - "review" (the default) puts it in the Review list: nothing
                 goes on YouTube until you watch it and press Approve (then
                 it's scheduled for the posting hour). "schedule" uploads it
                 straight away to go public at the posting hour; "private"
                 uploads it private.

Each channel needs its own YouTube login once (the "Connect" button: Google's
own sign-in page opens in your browser on this PC, and the key it gives back
is saved as tokens/yt_<channel>.json on this PC only). The app must stay open
for the Autopilot to run.
"""
from __future__ import annotations

import json
import re
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

APP_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = APP_DIR / "autopilot.json"
STATE_FILE = APP_DIR / "autopilot_state.json"
TOKENS_DIR = APP_DIR / "tokens"
CLIENT_SECRET = APP_DIR / "client_secret.json"
MAX_LOG = 200

DEFAULT_SETTINGS = {
    "enabled": False,
    "run_time": "02:30",          # when the nightly run starts (this PC's clock)
    "engine": "ollama",           # script writer, same choices as the Produce page
    "model": "",
    "ollama_host": "http://localhost:11434",
    "anthropic_key": "",
    "channels": [
        {"name": "Paper Trail", "enabled": True, "per_week": 2, "length": "long",
         "voice": "en-GB-RyanNeural", "publish": "review", "publish_hour": 17},
        {"name": "History", "enabled": False, "per_week": 1, "length": "long",
         "voice": "en-GB-ThomasNeural", "publish": "review", "publish_hour": 17},
        {"name": "The Forgotten Lab", "enabled": False, "per_week": 1, "length": "long",
         "voice": "en-GB-RyanNeural", "publish": "review", "publish_hour": 17},
    ],
}


class AutopilotError(Exception):
    pass


# ---------- settings and state ----------

def _read(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            pass
    return json.loads(json.dumps(default))


def load_settings() -> dict:
    s = _read(SETTINGS_FILE, DEFAULT_SETTINGS)
    for k, v in DEFAULT_SETTINGS.items():
        s.setdefault(k, v)
    return s


def save_settings(changes: dict) -> dict:
    s = load_settings()
    for key in ("enabled",):
        if key in changes:
            s[key] = bool(changes[key])
    if "run_time" in changes:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(changes["run_time"])):
            raise AutopilotError("Run time must look like 02:30.")
        s["run_time"] = str(changes["run_time"])
    for key in ("engine", "model", "ollama_host", "anthropic_key"):
        if key in changes:
            s[key] = str(changes[key]).strip()
    if s["engine"] not in ("ollama", "claude"):
        s["engine"] = "ollama"
    if "channels" in changes:
        chans = []
        for c in changes["channels"] or []:
            name = str(c.get("name", "")).strip()[:60]
            if not name:
                continue
            chans.append({
                "name": name, "enabled": bool(c.get("enabled")),
                "per_week": max(1, min(7, int(c.get("per_week") or 1))),
                "length": "short" if c.get("length") == "short" else "long",
                "voice": str(c.get("voice") or "en-GB-RyanNeural"),
                "publish": c.get("publish") if c.get("publish") in ("review", "private", "schedule") else "review",
                "publish_hour": max(0, min(23, int(c.get("publish_hour") or 17))),
            })
        s["channels"] = chans
    SETTINGS_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")
    return s


def load_state() -> dict:
    st = _read(STATE_FILE, {"last_run_day": None, "channels": {}, "log": [], "review": []})
    st.setdefault("channels", {})
    st.setdefault("review", [])
    st.setdefault("log", [])
    return st


def _save_state(st: dict) -> None:
    st["log"] = st["log"][-MAX_LOG:]
    STATE_FILE.write_text(json.dumps(st, indent=2, ensure_ascii=False), encoding="utf-8")


def _log(st: dict, channel: str, msg: str, ok: bool = True, **extra) -> None:
    st["log"].append({"time": datetime.now().isoformat(timespec="seconds"), "channel": channel,
                      "msg": msg, "ok": ok, **extra})
    _save_state(st)


# ---------- YouTube login per channel ----------

def token_path(channel: str) -> Path:
    return TOKENS_DIR / ("yt_" + re.sub(r"[^a-z0-9]+", "_", channel.lower()).strip("_") + ".json")


def connected(channel: str) -> bool:
    return token_path(channel).exists()


def connect(channel: str) -> str:
    """Opens Google's sign-in page in this PC's browser; pick the channel's account there."""
    if not CLIENT_SECRET.exists():
        raise AutopilotError("client_secret.json is missing - see the setup steps on the page (one time only).")
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), ["https://www.googleapis.com/auth/youtube.upload"])
    creds = flow.run_local_server(port=0, prompt="consent", authorization_prompt_message="")
    TOKENS_DIR.mkdir(exist_ok=True)
    token_path(channel).write_text(creds.to_json(), encoding="utf-8")
    return "connected"


# ---------- one channel, one video ----------

def due(chan: dict, st: dict, today: datetime) -> bool:
    last = (st["channels"].get(chan["name"]) or {}).get("last_made")
    if not last:
        return True
    gap = 7 / max(1, chan["per_week"])
    return (today.date() - datetime.fromisoformat(last).date()).days >= round(gap)


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", t.lower())[:80]


def pick_topic(chan: dict, st: dict, progress: Callable[[str], None]) -> dict:
    import researcher

    rchan = next((c for c in researcher.load_channels() if c["name"].lower() == chan["name"].lower()), None)
    if rchan is None:
        raise AutopilotError(f"No Research settings named '{chan['name']}' - add it on the Research page.")
    found = researcher.research_channel(rchan, progress, researcher._youtube_key())
    used = set((st["channels"].get(chan["name"]) or {}).get("used", []))
    for t in found["topics"]:
        if _norm(t["title"]) not in used:
            return t
    raise AutopilotError("Research found no new topic today" +
                         (f" (could not read: {', '.join(found['failed'])})" if found["failed"] else "") + ".")


def publish_time(hour: int, now: Optional[datetime] = None) -> str:
    """The next time it's `hour` o'clock on this PC, as UTC for YouTube (at least 1 hour away)."""
    now = now or datetime.now()
    when = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if when < now + timedelta(hours=1):
        when += timedelta(days=1)
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_one(chan: dict, settings: dict, st: dict, progress: Callable[[str], None] = lambda m: None) -> dict:
    from producer import CONTENT_ROOT, produce_video, resolve_target_words
    from studio_api import make_writer

    name = chan["name"]
    progress(f"{name}: researching...")
    topic = pick_topic(chan, st, progress)
    progress(f"{name}: making '{topic['title'][:60]}'...")
    writer = make_writer(settings["engine"], settings)
    result = produce_video(f"{topic['title']}. Angle: {topic['angle']}", name, writer, voice=chan["voice"],
                           target_words=resolve_target_words(chan["length"]), length=chan["length"],
                           progress=lambda m: progress(f"{name}: {m}"))
    cst = st["channels"].setdefault(name, {"used": []})
    cst["used"] = (cst.get("used", []) + [_norm(topic["title"])])[-300:]
    cst["last_made"] = datetime.now().isoformat(timespec="seconds")
    if result.get("video_error"):
        _log(st, name, f"Made the script and voice, but the video failed: {result['video_error']}", False,
             slug=result.get("slug"), topic=topic["title"])
        return result
    vdir = CONTENT_ROOT / result["slug"]
    video = vdir / "final_edited.mp4" if (vdir / "final_edited.mp4").exists() else vdir / "final.mp4"
    meta = json.loads((vdir / "metadata.json").read_text(encoding="utf-8")).get("youtube", {})
    title = str(meta.get("title") or topic["title"])[:100]
    if chan["publish"] == "review":
        st["review"].append({"channel": name, "slug": result["slug"], "title": title, "topic": topic["title"],
                             "description": str(meta.get("description") or ""), "tags": [str(t) for t in meta.get("tags") or []][:30],
                             "made": datetime.now().isoformat(timespec="seconds")})
        _log(st, name, f"Ready for you to check (Review list): {title}", True, slug=result["slug"], topic=topic["title"])
        return result
    if not connected(name):
        _log(st, name, f"Video ready, not uploaded - connect this channel's YouTube first: {title}", False,
             slug=result["slug"], topic=topic["title"])
        return result
    progress(f"{name}: uploading...")
    from publishing import upload_to_youtube

    when = publish_time(chan["publish_hour"]) if chan["publish"] == "schedule" else None
    vid = upload_to_youtube(video, title, str(meta.get("description") or ""), [str(t) for t in meta.get("tags") or []][:30],
                            client_secret_path=str(CLIENT_SECRET), token_path=str(token_path(name)), publish_at=when)
    cst["last_upload"] = vid
    thumb = vdir / "thumb_1.jpg"
    if thumb.exists():
        _set_thumb(vid, thumb, name, st)
    _log(st, name, f"Uploaded: {title}" + (f" (goes public {when})" if when else " (private - check it in YouTube Studio)"),
         True, slug=result["slug"], url=f"https://youtu.be/{vid}", topic=topic["title"])
    return result


# ---------- the nightly run ----------

_status = {"running": False, "message": ""}
_lock = threading.Lock()


def status() -> dict:
    s = load_settings()
    st = load_state()
    chans = []
    for c in s["channels"]:
        cst = st["channels"].get(c["name"], {})
        chans.append({**c, "connected": connected(c["name"]), "last_made": cst.get("last_made"),
                      "used": len(cst.get("used", []))})
    safe = {k: v for k, v in s.items() if k != "anthropic_key"} | {"has_anthropic_key": bool(s.get("anthropic_key")),
                                                                   "channels": chans}
    return {"settings": safe, "running": _status["running"], "message": _status["message"],
            "log": list(reversed(st["log"][-60:])), "client_secret": CLIENT_SECRET.exists(),
            "last_run_day": st.get("last_run_day")}


def run_now(only: Optional[str] = None) -> bool:
    with _lock:
        if _status["running"]:
            return False
        _status.update(running=True, message="Starting...")

    def job():
        try:
            settings = load_settings()
            st = load_state()
            st["last_run_day"] = datetime.now().date().isoformat()
            _save_state(st)
            today = datetime.now()
            for chan in settings["channels"]:
                if only and chan["name"] != only:
                    continue
                if not only and (not chan["enabled"] or not due(chan, st, today)):
                    continue
                try:
                    make_one(chan, settings, st, lambda m: _status.update(message=m))
                except Exception as exc:
                    _log(st, chan["name"], f"{type(exc).__name__}: {exc}", False)
                    traceback.print_exc()
        finally:
            _status.update(running=False, message="")
    threading.Thread(target=job, daemon=True).start()
    return True


def _scheduler() -> None:
    while True:
        try:
            s = load_settings()
            if s["enabled"]:
                now = datetime.now()
                st = load_state()
                if st.get("last_run_day") != now.date().isoformat() and now.strftime("%H:%M") >= s["run_time"]:
                    run_now()
        except Exception:
            traceback.print_exc()
        time.sleep(60)


_started = False


def start_scheduler() -> None:
    global _started
    if not _started:
        _started = True
        threading.Thread(target=_scheduler, daemon=True).start()


# ---------- review: you watch it, then approve ----------

def review_list() -> list[dict]:
    from producer import CONTENT_ROOT

    out = []
    for item in load_state()["review"]:
        vdir = CONTENT_ROOT / item["slug"]
        hooks = _read(vdir / "hooks.json", {"hooks": [], "chosen": None})
        thumbs = [n for n in (1, 2, 3) if (vdir / f"thumb_{n}.jpg").exists()]
        out.append({**item, "hooks": hooks.get("hooks", [])[:5], "chosen_hook": hooks.get("chosen"), "thumbs": thumbs,
                    "exists": (vdir / "final.mp4").exists()})
    return out


def video_file(slug: str) -> Optional[Path]:
    from producer import CONTENT_ROOT

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", slug or ""):
        return None
    vdir = CONTENT_ROOT / slug
    for name in ("final_edited.mp4", "final.mp4"):
        if (vdir / name).exists():
            return vdir / name
    return None


def approve(slug: str, title: Optional[str] = None, thumb: int = 1) -> dict:
    st = load_state()
    item = next((r for r in st["review"] if r["slug"] == slug), None)
    if item is None:
        raise AutopilotError("That video is not in the Review list any more.")
    chan = next((c for c in load_settings()["channels"] if c["name"] == item["channel"]), None)
    hour = chan["publish_hour"] if chan else 17
    if not connected(item["channel"]):
        raise AutopilotError(f"Connect {item['channel']}'s YouTube first (Connect YouTube button).")
    video = video_file(slug)
    if video is None:
        raise AutopilotError("The video file is missing.")
    from publishing import upload_to_youtube

    title = (title or item["title"]).strip()[:100]
    when = publish_time(hour)
    vid = upload_to_youtube(video, title, item.get("description", ""), item.get("tags", []),
                            client_secret_path=str(CLIENT_SECRET), token_path=str(token_path(item["channel"])),
                            publish_at=when)
    tpath = thumb_file(slug, int(thumb or 1))
    if tpath:
        _set_thumb(vid, tpath, item["channel"], st)
    st["review"] = [r for r in st["review"] if r["slug"] != slug]
    _log(st, item["channel"], f"Approved and uploaded: {title} (goes public {when})", True, slug=slug,
         url=f"https://youtu.be/{vid}")
    return {"video_id": vid, "publish_at": when}


def _set_thumb(video_id: str, path: Path, channel: str, st: dict) -> None:
    try:
        from publishing import set_thumbnail

        set_thumbnail(video_id, path, str(CLIENT_SECRET), str(token_path(channel)))
    except Exception as exc:  # most often: the channel isn't phone-verified for custom thumbnails yet
        _log(st, channel, f"Video uploaded but the thumbnail wasn't set ({type(exc).__name__}: {exc}). "
                          "Verify the channel by phone at youtube.com/verify, then set it in YouTube Studio.", False)


def thumb_file(slug: str, n: int) -> Optional[Path]:
    from producer import CONTENT_ROOT

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", slug or "") or n not in (1, 2, 3):
        return None
    p = CONTENT_ROOT / slug / f"thumb_{n}.jpg"
    return p if p.exists() else None


def reject(slug: str) -> None:
    st = load_state()
    item = next((r for r in st["review"] if r["slug"] == slug), None)
    st["review"] = [r for r in st["review"] if r["slug"] != slug]
    if item:
        _log(st, item["channel"], f"Skipped (not uploaded): {item['title']}", True, slug=slug)
    else:
        _save_state(st)
