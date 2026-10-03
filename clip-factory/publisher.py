"""Auto publisher - a weekly schedule for every channel, and automatic
uploads to YouTube.

How it works:
  1. Connect each channel once (Google login in the browser). Tokens are
     saved in tokens/ on this PC.
  2. Add videos to the queue: Clip Factory clips (with their description
     and tags) and finished Wayne Factory videos and Shorts.
  3. "Fill the schedule" gives each one a time slot from the channel's
     weekly plan (e.g. Paper Trail: full videos Mon & Thu 17:00).
  4. Uploading:
     - Google hasn't approved the app yet: YouTube locks every video an
       unapproved app uploads as private. So the queue becomes a checklist:
       each item has its time, its file, and its title/description/tags to
       copy - you schedule it in YouTube Studio and tick "Scheduled".
     - Approved: the publisher uploads each video by itself (as private
       with YouTube's own "publish at" time, so YouTube makes it public at
       the right moment even if this PC is off), a few days ahead,
       within the daily quota (10,000 units = 6 uploads a day).
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

import channel_stats

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
SETTINGS_FILE = APP_DIR / "publisher.json"
QUEUE_FILE = APP_DIR / "publish_queue.json"
TOKENS_DIR = APP_DIR / "tokens"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
UPLOAD_UNITS, THUMB_UNITS, DAILY_UNITS = 1600, 50, 10_000
UPLOAD_AHEAD_DAYS = 3        # upload this far ahead of the publish time (spreads the daily quota)
WEEK_DIR = APP_DIR / "to-upload"   # "this week" folders for bulk uploads in YouTube Studio
CONTENT_DIRS = [ROOT / "content", ROOT / "wayne-factory-lite" / "content"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# the 60-day plan: full videos rotate between the story channels, Shorts every day
DEFAULT_SLOTS = {
    "paper":   [{"kind": "long", "days": [0, 3], "time": "17:00"}, {"kind": "short", "days": list(range(7)), "time": "12:00"}],
    "science": [{"kind": "long", "days": [1, 4], "time": "17:00"}, {"kind": "short", "days": list(range(7)), "time": "12:00"}],
    "history": [{"kind": "long", "days": [2, 5], "time": "17:00"}, {"kind": "short", "days": list(range(7)), "time": "12:00"}],
    "clips":   [{"kind": "short", "days": list(range(7)), "every": 60, "from": "09:00", "to": "23:00"}],
    "streams": [{"kind": "short", "days": list(range(7)), "time": t} for t in ("10:00", "14:00", "18:00", "22:00")],
}
# choices for "Shorts per channel" in the Publish tab
SHORT_PLANS = {
    "1day": [{"kind": "short", "days": list(range(7)), "time": "12:00"}],
    "3day": [{"kind": "short", "days": list(range(7)), "time": t} for t in ("09:00", "15:00", "21:00")],
    "2h":   [{"kind": "short", "days": list(range(7)), "every": 120, "from": "09:00", "to": "23:00"}],
    "1h":   [{"kind": "short", "days": list(range(7)), "every": 60, "from": "09:00", "to": "23:00"}],
}
DEFAULT_GAP = 60   # minutes between any two posts, all channels together
ISO = "%Y-%m-%dT%H:%M"
OTHER_SLOTS = [{"kind": "long", "days": [2], "time": "17:00"}, {"kind": "short", "days": list(range(7)), "time": "12:00"}]

_lock = threading.RLock()
state = {"connecting": None, "connect_error": None, "uploading": None, "last_error": None}


class PublishError(Exception):
    pass


class QuotaError(PublishError):
    """Today's upload quota is used up - try again tomorrow (not the video's fault)."""


# ---------- settings / queue storage ----------

def load_settings() -> dict:
    try:
        s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        s = {}
    s.setdefault("approved", False)
    s.setdefault("connected", {})
    s.setdefault("slots", {})
    s.setdefault("quota", {"date": "", "used": 0})
    s.setdefault("gap", DEFAULT_GAP)
    return s


def save_settings(s: dict) -> None:
    with _lock:
        SETTINGS_FILE.write_text(json.dumps(s, indent=1), encoding="utf-8")


def load_queue() -> list[dict]:
    try:
        q = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        return q if isinstance(q, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_queue(q: list[dict]) -> None:
    with _lock:
        tmp = QUEUE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(q, indent=1), encoding="utf-8")
        tmp.replace(QUEUE_FILE)


def channels() -> list[dict]:
    """The channels from My channels (same ids), with their slots and connection."""
    s = load_settings()
    out = []
    for c in channel_stats.load_config()["channels"]:
        conn = s["connected"].get(c["id"])
        out.append(dict(c, slots=s["slots"].get(c["id"]) or DEFAULT_SLOTS.get(c["id"], OTHER_SLOTS),
                        connected=conn, token=(TOKENS_DIR / f"{c['id']}.json").exists()))
    return out


# ---------- Google connection ----------

def client_secret_path() -> Optional[Path]:
    for p in (APP_DIR / "client_secret.json", ROOT / "wayne-factory-lite" / "client_secret.json", ROOT / "client_secret.json"):
        if p.exists():
            return p
    return None


def _handle(text: str) -> str:
    return (text or "").strip().lower().lstrip("@")


def connect_async(cid: str) -> None:
    """Opens Google's login in the browser; the person picks the channel there."""
    if state["connecting"]:
        raise PublishError("Already waiting for a Google login - finish that one first.")
    secret = client_secret_path()
    if not secret:
        raise PublishError("client_secret.json is missing - see step 1.")
    state.update(connecting=cid, connect_error=None)

    def work():
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
            # prompt=select_account: always ask which Google account / channel, never reuse the last login
            creds = flow.run_local_server(port=0, open_browser=True, timeout_seconds=600,
                                          prompt="select_account consent", authorization_prompt_message="",
                                          success_message="Connected - you can close this tab and go back to Clip Factory.")
            info = _whoami(creds)
            TOKENS_DIR.mkdir(exist_ok=True)
            (TOKENS_DIR / f"{cid}.json").write_text(creds.to_json(), encoding="utf-8")
            want = next((c for c in channel_stats.load_config()["channels"] if c["id"] == cid), {})
            mismatch = bool(want.get("ref")) and _handle(info["handle"]) != _handle(channel_stats.trends.channel_url(want["ref"]).rsplit("/", 1)[-1])
            s = load_settings()
            s["connected"][cid] = dict(info, mismatch=mismatch, at=time.strftime("%Y-%m-%d %H:%M"))
            save_settings(s)
        except Exception as exc:
            msg = str(exc)
            if "access_denied" in msg or "403" in msg:
                msg = ("Google said access_denied. In Google Cloud -> Google Auth Platform -> Audience, press Publish app "
                       "(or add your Google address under Test users), then try again.")
            state["connect_error"] = msg[:400]
        finally:
            state["connecting"] = None

    threading.Thread(target=work, daemon=True).start()


def _whoami(creds) -> dict:
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    items = yt.channels().list(part="snippet", mine=True).execute().get("items") or []
    if not items:
        raise PublishError("That Google login has no YouTube channel.")
    ch = items[0]
    return {"id": ch["id"], "title": ch["snippet"].get("title", ""), "handle": ch["snippet"].get("customUrl", "")}


def disconnect(cid: str) -> None:
    (TOKENS_DIR / f"{cid}.json").unlink(missing_ok=True)
    s = load_settings()
    s["connected"].pop(cid, None)
    save_settings(s)


def _creds(cid: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    path = TOKENS_DIR / f"{cid}.json"
    if not path.exists():
        raise PublishError("this channel isn't connected")
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                raise PublishError("the Google login expired - click Connect again (in Google Cloud, press "
                                   "'Publish app' so logins stop expiring after 7 days)") from exc
            path.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise PublishError("the Google login expired - click Connect again")
    return creds


# ---------- finding videos to publish ----------

def _probe_vertical(path: Path) -> bool:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                              "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=30).stdout.strip()
        w, h = (int(x) for x in out.split(",")[:2])
        return h > w
    except Exception:
        return False


# other words Wayne Factory's channel names may use for the 4 challenge channels
ALIASES = {"paper": ["paper trail", "paper", "business", "fraud", "collapse"], "history": ["history"],
           "science": ["forgotten lab", "science", "lab"], "clips": ["hot mic", "clip", "podcast"],
           "streams": ["chat lost it", "stream", "twitch", "kick"]}


def _guess_channel(name: str) -> str:
    name = name.lower().strip()
    if not name:
        return ""
    chans = channel_stats.load_config()["channels"]
    for c in chans:
        if c["name"].lower() in name or name in c["name"].lower():
            return c["id"]
    for c in chans:
        if any(a in name for a in ALIASES.get(c["id"], [])):
            return c["id"]
    return ""


def wayne_videos() -> list[dict]:
    """Finished videos (and their auto-made Shorts) in both Wayne Factory apps' content folders."""
    queued = {i["file"] for i in load_queue()}
    out = []
    for base in CONTENT_DIRS:
        if not base.is_dir():
            continue
        app = "Wayne Factory Lite" if "wayne-factory-lite" in str(base) else "Wayne Factory"
        for d in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            video = next((d / n for n in ("final_edited.mp4", "final.mp4") if (d / n).exists()), None)
            if not video:
                continue
            try:
                meta = json.loads((d / "metadata.json").read_text(encoding="utf-8")).get("youtube", {})
            except (OSError, json.JSONDecodeError):
                meta = {}
            channel_line = ""
            try:
                channel_line = (d / "notes.txt").read_text(encoding="utf-8").splitlines()[0].split(" - ")[0]
            except (OSError, IndexError):
                pass
            title = meta.get("title") or d.name.replace("-", " ").capitalize()
            kind = "short" if _probe_vertical(video) else "long"
            item = {"file": str(video), "title": title[:100], "description": meta.get("description") or title,
                    "tags": [str(t) for t in meta.get("tags") or []][:30],
                    "thumb": str(d / "thumbnail.jpg") if (d / "thumbnail.jpg").exists() else "",
                    "kind": kind, "cid": _guess_channel(channel_line), "source": f"{app}: {d.name}",
                    "queued": str(video) in queued}
            out.append(item)
            try:  # Wayne Factory Lite also cuts each long video into Shorts
                shorts = json.loads((d / "shorts" / "shorts.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                shorts = []
            for i, sh in enumerate(shorts if isinstance(shorts, list) else [], start=1):
                f = d / "shorts" / f"short_{i}.mp4"
                if f.exists():
                    st = str(sh.get("title") or f"{title} - Part {i}")[:90]
                    out.append({"file": str(f), "title": st, "kind": "short", "cid": item["cid"], "thumb": "",
                                "description": f"{st}\n\nThe full story is on our channel.\n\n#Shorts",
                                "tags": item["tags"][:10] + ["shorts"], "source": f"{app}: {d.name} (Short {i})",
                                "queued": str(f) in queued})
    return out


def add_items(items: list[dict]) -> int:
    q = load_queue()
    have = {i["file"] for i in q}
    added = 0
    for it in items:
        f = str(it.get("file") or "")
        if not f or f in have or not Path(f).exists():
            continue
        q.append({"id": uuid.uuid4().hex[:10], "cid": it.get("cid") or "", "kind": it.get("kind") or "short", "file": f,
                  "title": str(it.get("title") or Path(f).stem)[:100], "description": str(it.get("description") or "")[:4900],
                  "tags": [str(t)[:40] for t in it.get("tags") or []][:30], "thumb": it.get("thumb") or "", "cover": it.get("cover") or "",
                  "source": it.get("source") or "", "when": "", "status": "waiting", "video_id": "", "url": "",
                  "error": "", "added": time.strftime("%Y-%m-%d %H:%M")})
        have.add(f)
        added += 1
    save_queue(q)
    return added


def update_item(item_id: str, changes: dict) -> dict:
    q = load_queue()
    for it in q:
        if it["id"] == item_id:
            for k in ("cid", "kind", "title", "description", "when", "status"):
                if k in changes and changes[k] is not None:
                    it[k] = str(changes[k])[:4900] if k == "description" else str(changes[k])[:100]
            if "tags" in changes and isinstance(changes["tags"], list):
                it["tags"] = [str(t)[:40] for t in changes["tags"]][:30]
            if changes.get("status") == "waiting":
                it["error"] = ""
            save_queue(q)
            return it
    raise PublishError("That item isn't in the queue any more.")


def remove_item(item_id: str) -> None:
    save_queue([i for i in load_queue() if i["id"] != item_id])


# ---------- scheduling ----------

def short_plan(slots: list[dict]) -> str:
    """Which SHORT_PLANS choice a channel's slots match ("" = custom)."""
    mine = [r for r in slots if r["kind"] == "short"]
    return next((k for k, v in SHORT_PLANS.items() if v == mine), "")


def set_short_plan(cid: str, plan: str) -> None:
    if plan not in SHORT_PLANS:
        raise PublishError("unknown plan")
    ch = next((c for c in channels() if c["id"] == cid), None)
    if not ch:
        raise PublishError("unknown channel")
    s = load_settings()
    s["slots"][cid] = [r for r in ch["slots"] if r["kind"] != "short"] + SHORT_PLANS[plan]
    save_settings(s)


def _candidates(slots: list[dict], kind: str, start: dt.datetime, gap: int, days: int = 60):
    """(time, slot) pairs in time order. A fixed slot (e.g. 12:00) may slide 1-3 gaps later when another
    channel already posts then; an "every N minutes" rule simply offers every step."""
    rules = [r for r in slots if r["kind"] == kind] or slots
    out = []
    for d in range(days + 1):
        day = (start + dt.timedelta(days=d)).date()
        for r in rules:
            if day.weekday() not in r["days"]:
                continue
            if r.get("every"):
                t = dt.datetime.combine(day, dt.time(*(int(x) for x in r.get("from", "09:00").split(":"))))
                last = dt.datetime.combine(day, dt.time(*(int(x) for x in r.get("to", "23:00").split(":"))))
                while t <= last:
                    if t > start:
                        out.append((t, t))
                    t += dt.timedelta(minutes=max(15, int(r["every"])))
            else:
                base = dt.datetime.combine(day, dt.time(*(int(x) for x in r["time"].split(":"))))
                for k in range(4 if gap else 1):
                    t = base + dt.timedelta(minutes=gap * k)
                    if t > start and t.date() == day:
                        out.append((t, base))
    return sorted(set(out))


def _busy(q: list[dict]):
    """Every planned post time (all channels) and the slots each channel already uses."""
    live = [i for i in q if i.get("when") and i["status"] != "failed"]
    times = sorted(dt.datetime.fromisoformat(i["when"]) for i in live)
    slots = {(i["cid"], i.get("base") or i["when"]) for i in live}
    return times, slots


def _is_free(t: dt.datetime, times: list, gap: int) -> bool:
    g = dt.timedelta(minutes=max(1, gap))
    i = bisect.bisect_left(times, t - g + dt.timedelta(seconds=1))
    return not (i < len(times) and times[i] < t + g)


def _assign(it: dict, slots: list[dict], start: dt.datetime, gap: int, times: list, used: set) -> bool:
    for t, base in _candidates(slots, it["kind"], start, gap):
        key = (it["cid"], base.strftime(ISO))
        if key in used or not _is_free(t, times, gap):
            continue
        it["when"], it["base"] = t.strftime(ISO), key[1]
        used.add(key)
        bisect.insort(times, t)
        return True
    return False


def fill_schedule(now: Optional[dt.datetime] = None, replan: bool = False) -> int:
    """Give every waiting item without a time the next free slot of its channel, keeping at least
    `gap` minutes between any two posts. replan=True first clears the times of all to-do items."""
    now = now or dt.datetime.now()
    start = now + dt.timedelta(minutes=30)
    q = load_queue()
    gap = int(load_settings()["gap"])
    chans = {c["id"]: c for c in channels()}
    if replan:
        for it in q:
            if it["status"] == "waiting":
                it["when"], it["base"] = "", ""
    times, used = _busy(q)
    filled = 0
    for it in sorted(q, key=lambda i: i["added"]):
        if it["when"] or it["status"] != "waiting" or it["cid"] not in chans:
            continue
        if _assign(it, chans[it["cid"]]["slots"], start, gap, times, used):
            filled += 1
    save_queue(q)
    return filled


def _move_late(item_id: str, now: dt.datetime) -> Optional[str]:
    """A post that missed its time (PC was off) gets the next free time, so late posts never go out all at once."""
    with _lock:
        q = load_queue()
        it = next((i for i in q if i["id"] == item_id), None)
        chans = {c["id"]: c for c in channels()}
        if not it or it["cid"] not in chans:
            return None
        times, used = _busy([i for i in q if i["id"] != item_id])
        if not _assign(it, chans[it["cid"]]["slots"], now + dt.timedelta(minutes=30), int(load_settings()["gap"]), times, used):
            return None
        save_queue(q)
        return it["when"]


def per_day() -> float:
    """Planned posts per day over the coming week (for the quota warning)."""
    now = dt.datetime.now()
    week = [i for i in load_queue() if i["status"] == "waiting" and i.get("when")
            and now <= dt.datetime.fromisoformat(i["when"]) <= now + dt.timedelta(days=7)]
    return round(len(week) / 7, 1)


# ---------- the week, ready for YouTube Studio ----------

def _file_name(title: str) -> str:
    """A Windows-safe file name. YouTube Studio uses the file name as the first title."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title).strip().rstrip(".")
    return name[:90] or "video"


def _place(src: Path, dst: Path) -> None:
    try:
        os.link(src, dst)  # same drive: instant, uses no extra space
    except OSError:
        shutil.copy2(src, dst)


def prepare_week(days: int = 7, now: Optional[dt.datetime] = None) -> list[dict]:
    """Puts each channel's next `days` of to-do videos in to-upload/<channel>/, named by their title,
    plus a list with each video's time, title, description and tags."""
    now = now or dt.datetime.now()
    end = now + dt.timedelta(days=days)
    names = {c["id"]: c["name"] for c in channels()}
    by_ch: dict[str, list[dict]] = {}
    for it in sorted(load_queue(), key=lambda i: i["when"] or ""):
        if it["status"] == "waiting" and it["when"] and it["cid"] in names and Path(it["file"]).exists() \
                and dt.datetime.fromisoformat(it["when"]) <= end:
            by_ch.setdefault(it["cid"], []).append(it)
    shutil.rmtree(WEEK_DIR, ignore_errors=True)  # last week's files go, so nothing gets posted twice
    out = []
    for cid, items in by_ch.items():
        folder = WEEK_DIR / _file_name(names[cid])
        folder.mkdir(parents=True, exist_ok=True)
        used, lines = set(), []
        for n, it in enumerate(items, start=1):
            base = _file_name(it["title"])
            name, k = base, 2
            while name.lower() in used:
                name, k = f"{base} ({k})", k + 1
            used.add(name.lower())
            src = Path(it["file"])
            _place(src, folder / (name + src.suffix.lower()))
            if it["kind"] == "long" and it.get("thumb") and Path(it["thumb"]).exists():
                _place(Path(it["thumb"]), folder / (name + " - thumbnail.jpg"))
            if it.get("cover") and Path(it["cover"]).exists():  # Shorts/Reels cover picture
                _place(Path(it["cover"]), folder / (name + " - cover.jpg"))
            when = dt.datetime.fromisoformat(it["when"])
            lines.append(f"{'=' * 60}\n{n}. {when:%A %d %B, %H:%M}  ({'Short' if it['kind'] == 'short' else 'full video'})\n"
                         f"File: {name}{src.suffix.lower()}\n\nTITLE:\n{it['title']}\n\nDESCRIPTION:\n{it['description']}\n\n"
                         f"TAGS:\n{', '.join(it['tags'])}\n")
        head = (f"{names[cid]} - {len(items)} videos for {now:%d %B} to {end:%d %B}\n\n"
                "In YouTube Studio: Create -> Upload videos -> select all the video files in this folder (up to 15 at a time).\n"
                "For each one: paste the title, description and tags below, then Visibility -> Schedule -> the time below.\n\n")
        (folder / "00 - titles, descriptions, tags.txt").write_text(head + "\n".join(lines), encoding="utf-8")
        out.append({"cid": cid, "name": names[cid], "count": len(items), "folder": str(folder), "ids": [i["id"] for i in items],
                    "first": items[0]["when"], "last": items[-1]["when"]})
    return out


def open_folder(path: Path) -> None:
    if os.name == "nt":
        subprocess.Popen(["explorer", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def mark(ids: list[str], status: str) -> int:
    q = load_queue()
    n = 0
    for it in q:
        if it["id"] in ids and it["status"] == "waiting":
            it["status"] = status
            n += 1
    save_queue(q)
    return n


# ---------- quota ----------

def _pacific_date() -> str:
    # YouTube's quota resets at midnight Pacific time (UTC-8; UTC-7 in summer - close enough here)
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=8)).date().isoformat()


def quota() -> dict:
    s = load_settings()
    used = s["quota"]["used"] if s["quota"].get("date") == _pacific_date() else 0
    return {"used": used, "limit": DAILY_UNITS, "uploads_left": max(0, (DAILY_UNITS - used) // UPLOAD_UNITS)}


def _spend(units: int) -> None:
    s = load_settings()
    today = _pacific_date()
    if s["quota"].get("date") != today:
        s["quota"] = {"date": today, "used": 0}
    s["quota"]["used"] += units
    save_settings(s)


# ---------- uploading ----------

def _rfc3339_utc(local_iso: str) -> str:
    local = dt.datetime.fromisoformat(local_iso)
    return local.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upload_item(item: dict, test: bool = False, progress=None) -> dict:
    """Uploads one queue item. test=True: always private, no publish time."""
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    s = load_settings()
    conn = s["connected"].get(item["cid"])
    if not conn:
        raise PublishError("this channel isn't connected")
    if conn.get("mismatch"):
        raise PublishError(f'the login is for "{conn["title"]}", not this channel - click Connect again and pick the right channel')
    if not Path(item["file"]).exists():
        raise PublishError("the video file isn't there any more")
    if quota()["used"] + UPLOAD_UNITS > DAILY_UNITS:
        raise QuotaError("today's YouTube upload quota is used up - it continues after midnight (US Pacific time)")
    yt = build("youtube", "v3", credentials=_creds(item["cid"]), cache_discovery=False)
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    when = dt.datetime.fromisoformat(item["when"]) if item.get("when") else None
    if not test:
        if when and when > dt.datetime.now() + dt.timedelta(minutes=20):
            status["publishAt"] = _rfc3339_utc(item["when"])  # YouTube makes it public at that moment
        else:
            status["privacyStatus"] = "public"
    title = item["title"] + (" #Shorts" if item["kind"] == "short" and "#shorts" not in item["title"].lower() and len(item["title"]) < 90 else "")
    body = {"snippet": {"title": title[:100], "description": item["description"][:4900], "tags": item["tags"],
                        "categoryId": "24" if item["kind"] == "short" else "27"}, "status": status}
    try:
        req = yt.videos().insert(part="snippet,status", body=body,
                                 media_body=MediaFileUpload(item["file"], chunksize=8 * 1024 * 1024, resumable=True))
        resp = None
        while resp is None:
            st, resp = req.next_chunk()
            if st and progress:
                progress(int(st.progress() * 100))
    except HttpError as exc:
        text = str(exc)
        if "quotaExceeded" in text or "uploadLimitExceeded" in text:
            _spend(DAILY_UNITS)
            raise QuotaError("YouTube's daily upload limit was reached - it continues tomorrow") from exc
        raise PublishError(f"YouTube refused the upload: {re.sub(r'<[^>]+>', '', text)[:300]}") from exc
    _spend(UPLOAD_UNITS)
    vid = resp["id"]
    note = ""
    if item.get("thumb") and Path(item["thumb"]).exists() and item["kind"] == "long":
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(item["thumb"])).execute()
            _spend(THUMB_UNITS)
        except Exception:
            note = "custom thumbnail needs a phone-verified channel (YouTube Studio -> Settings -> Channel -> Feature eligibility)"
    url = f"https://www.youtube.com/shorts/{vid}" if item["kind"] == "short" else f"https://www.youtube.com/watch?v={vid}"
    return {"video_id": vid, "url": url, "note": note, "private_test": test}


def _set(item_id: str, **fields) -> None:
    with _lock:
        q = load_queue()
        for it in q:
            if it["id"] == item_id:
                it.update(fields)
        save_queue(q)


def run_due(now: Optional[dt.datetime] = None) -> int:
    """Uploads everything due (publish time within UPLOAD_AHEAD_DAYS), within the quota. Approved mode only."""
    s = load_settings()
    if not s["approved"] or state["uploading"]:
        return 0
    now = now or dt.datetime.now()
    ok = {cid for cid, c in s["connected"].items() if not c.get("mismatch")}  # a wrong-channel login waits for a reconnect
    due = sorted((i for i in load_queue() if i["status"] == "waiting" and i["when"] and i["cid"] in ok
                  and dt.datetime.fromisoformat(i["when"]) <= now + dt.timedelta(days=UPLOAD_AHEAD_DAYS)),
                 key=lambda i: i["when"])
    done = 0
    for it in due:
        if quota()["uploads_left"] < 1:
            break
        if dt.datetime.fromisoformat(it["when"]) < now + dt.timedelta(minutes=20):
            new = _move_late(it["id"], now)
            if not new:
                continue
            it["when"] = new
        state["uploading"] = it["id"]
        _set(it["id"], status="uploading", error="")
        try:
            res = upload_item(it, progress=lambda p, i=it["id"]: _set(i, progress=p))
            _set(it["id"], status="uploaded", video_id=res["video_id"], url=res["url"], error=res["note"], progress=100,
                 uploaded_at=time.strftime("%Y-%m-%d %H:%M"))
            done += 1
        except QuotaError as exc:
            _set(it["id"], status="waiting", error=str(exc))
            break
        except PublishError as exc:
            _set(it["id"], status="failed", error=str(exc))
        except Exception as exc:
            _set(it["id"], status="failed", error=f"unexpected problem: {exc}"[:300])
        finally:
            state["uploading"] = None
    return done


def start_background() -> None:
    def loop():
        while True:
            try:
                run_due()
                state["last_error"] = None
            except Exception as exc:
                state["last_error"] = str(exc)[:300]
            time.sleep(60)
    threading.Thread(target=loop, daemon=True).start()


# ---------- Google approval (audit) request ----------

def audit_text() -> str:
    chans = [c for c in channels() if c.get("ref") or c.get("connected")]
    names = ", ".join(c["name"] for c in chans) or "my channels"
    per_day = 7
    units = per_day * (UPLOAD_UNITS + THUMB_UNITS) + 500
    return f"""YouTube API Services - Audit and Quota Extension Form: suggested answers
(Form: https://support.google.com/youtube/contact/yt_api_form - choose "I would like to request an API audit / quota extension")

What does your API client do?
  A private desktop tool I run on my own computer to upload videos I made myself to my own YouTube channels ({names}). It uploads each finished video with its title, description, tags and (for long videos) its thumbnail, and schedules it with YouTube's own publishAt setting. It is not offered to anyone else and has no other users.

Which API methods do you use?
  videos.insert (upload my own videos), thumbnails.set (my own thumbnails), channels.list with mine=true (to confirm which of my channels a login belongs to).

Who can use it?
  Only me, the owner of the channels. All logins are my own Google accounts / Brand Accounts.

What user data do you store?
  Only the OAuth tokens for my own channels, stored locally on my computer. No data is shared, sold or sent anywhere else.

Why do you need more quota?
  I publish about {per_day} videos a day across {len(chans) or 4} channels (1 long video + several Shorts). Each upload costs 1,600 units plus 50 for a thumbnail, so I need about {units:,} units per day. The default 10,000 units only allows 6 uploads.

Requested daily quota: {max(20000, (units // 10000 + 1) * 10000):,} units

Tips:
  - Use the same Google Cloud project as your client_secret.json (its project number is in Google Cloud Console -> Dashboard).
  - Google may ask for a short screen recording of the app uploading a video - record the Publish tab doing a Test upload.
  - Approval usually takes 1-4 weeks. Until then Clip Factory works in "schedule it yourself" mode.
"""
