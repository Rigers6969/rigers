"""Phone alerts through ntfy (free app for Android and iPhone, no account).

The phone subscribes to a private topic name; Clip Factory sends messages to it:
  - clips ready            when a clip run finishes
  - your clip went viral   a video on your channels gains a lot of views (checked every 3 hours)
  - clip it now            a streamer's new video is blowing up (checked every 2 hours)
  - post reminder          30 minutes before a post that isn't scheduled in YouTube Studio yet
  - upload problems        automatic mode couldn't upload a video
  - weekly report          Monday morning: views this week and the goal
"""
from __future__ import annotations

import datetime as dt
import json
import secrets
import threading
import time
from pathlib import Path

import requests

import channel_stats
import publisher
import trends

APP_DIR = Path(__file__).resolve().parent
FILE = APP_DIR / "alerts.json"
KINDS = {
    "clips_done": "Clips are ready",
    "viral": "One of my videos is going viral",
    "streamers": "A streamer is blowing up (clip it now)",
    "posts": "30 minutes before a post I haven't scheduled yet",
    "uploads": "An automatic upload failed",
    "weekly": "Weekly report (Monday morning)",
}
MILESTONES = (10_000, 50_000, 100_000, 500_000, 1_000_000, 5_000_000, 10_000_000)
STREAMER_SCAN_HOURS = 2
_lock = threading.Lock()
state = {"last_error": None, "last_sent": None, "scanning": False}


def load() -> dict:
    try:
        cfg = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cfg = {}
    if not cfg.get("topic"):  # a private, hard-to-guess name: only phones that know it get the alerts
        cfg["topic"] = "clipfactory-" + secrets.token_urlsafe(9).replace("_", "x").replace("-", "y")
        cfg.setdefault("on", {k: True for k in KINDS})
        _save(cfg)
    cfg.setdefault("server", "https://ntfy.sh")
    cfg.setdefault("enabled", False)
    cfg.setdefault("on", {k: True for k in KINDS})
    for k in KINDS:
        cfg["on"].setdefault(k, True)
    cfg.setdefault("viral_gain", 10_000)        # views gained between two checks (~3 hours)
    cfg.setdefault("streamer_vph", 20_000)      # a streamer video getting this many views per hour
    cfg.setdefault("sent", {})
    cfg.setdefault("last_scan", 0)
    return cfg


def _save(cfg: dict) -> None:
    with _lock:
        # keep the "already sent" list small: forget entries older than 30 days
        cutoff = time.time() - 30 * 86400
        cfg["sent"] = {k: v for k, v in (cfg.get("sent") or {}).items() if v > cutoff}
        tmp = FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
        tmp.replace(FILE)


def update(changes: dict) -> dict:
    cfg = load()
    if "enabled" in changes:
        cfg["enabled"] = bool(changes["enabled"])
    for k, v in (changes.get("on") or {}).items():
        if k in KINDS:
            cfg["on"][k] = bool(v)
    for key, lo, hi in (("viral_gain", 100, 10_000_000), ("streamer_vph", 100, 10_000_000)):
        if key in changes:
            try:
                cfg[key] = max(lo, min(hi, int(changes[key])))
            except (TypeError, ValueError):
                pass
    if changes.get("new_topic"):
        cfg["topic"] = "clipfactory-" + secrets.token_urlsafe(9).replace("_", "x").replace("-", "y")
    _save(cfg)
    return cfg


def send(title: str, message: str, tags: list[str] | None = None, priority: int = 3, click: str = "",
         force: bool = False) -> None:
    """Sends one notification. Raises on network problems (callers decide whether that matters)."""
    cfg = load()
    if not force and not cfg["enabled"]:
        return
    body = {"topic": cfg["topic"], "title": title[:200], "message": message[:3000], "priority": priority,
            "tags": tags or []}
    if click:
        body["click"] = click
    r = requests.post(cfg["server"].rstrip("/"), json=body, timeout=15)
    if r.status_code >= 400:
        raise RuntimeError(f"ntfy said {r.status_code}: {r.text[:200]}")
    state["last_sent"] = time.strftime("%Y-%m-%d %H:%M")


def _once(key: str) -> bool:
    """True the first time a key is seen (so every alert is sent only once)."""
    cfg = load()
    if key in cfg["sent"]:
        return False
    cfg["sent"][key] = time.time()
    _save(cfg)
    return True


def notify(kind: str, key: str, title: str, message: str, tags=None, priority=3, click="") -> bool:
    cfg = load()
    if not cfg["enabled"] or not cfg["on"].get(kind) or not _once(f"{kind}:{key}"):
        return False
    try:
        send(title, message, tags, priority, click)
        state["last_error"] = None
        return True
    except Exception as exc:
        state["last_error"] = str(exc)[:300]
        return False


def _n(v) -> str:
    return trends._fmt_count(v)


# ---------- the alerts ----------

def clips_done(run: dict) -> None:
    n = len(run.get("clips") or [])
    if n:
        notify("clips_done", run["id"], f"{n} clip{'s' if n != 1 else ''} ready",
               f"From: {run.get('video', '')}\nOpen Clip Factory to post them.", ["white_check_mark"])


def upload_failed(item: dict, error: str) -> None:
    notify("uploads", f"{item['id']}:{error[:40]}", "Upload failed",
           f"{item.get('title', '')}\n{error}", ["warning"], 4)


def check_viral(snap: dict | None = None) -> None:
    """After each channel check: a video that gained a lot since the last check, or passed a milestone."""
    cfg = load()
    snaps = channel_stats.load_snapshots()
    if len(snaps) < 2 or not cfg["enabled"] or not cfg["on"]["viral"]:
        return
    prev, last = snaps[-2], snaps[-1]
    names = {c["id"]: c["name"] for c in channel_stats.load_config()["channels"]}
    hours = max(0.5, (channel_stats._t(last) - channel_stats._t(prev)).total_seconds() / 3600)
    for cid, ch in (last.get("channels") or {}).items():
        old = ((prev.get("channels") or {}).get(cid) or {}).get("vids") or {}
        for vid, v in (ch.get("vids") or {}).items():
            before = old.get(vid, {}).get("v")
            gain = v["v"] - before if before is not None else 0
            passed = [m for m in MILESTONES if before is not None and before < m <= v["v"]]
            url = f"https://www.youtube.com/{'shorts/' if v.get('s') else 'watch?v='}{vid}"
            if passed:
                notify("viral", f"{vid}:{passed[-1]}", f"{_n(passed[-1])} views!",
                       f"{v['t']}\n{names.get(cid, cid)} - now {_n(v['v'])} views (+{_n(gain)} in {hours:.0f}h)",
                       ["fire"], 4, url)
            elif gain >= cfg["viral_gain"]:
                notify("viral", f"{vid}:gain:{v['v'] // cfg['viral_gain']}", "Your clip is going viral",
                       f"{v['t']}\n{names.get(cid, cid)} - +{_n(gain)} views in {hours:.0f}h ({_n(v['v'])} total)",
                       ["fire"], 4, url)


def scan_streamers(force: bool = False) -> int:
    """Checks the streamer list for new videos blowing up. Returns how many alerts went out."""
    cfg = load()
    if not force and (not cfg["enabled"] or not cfg["on"]["streamers"]):
        return 0
    names = trends.load_streamers("streamers")
    if not names or state["scanning"]:
        return 0
    state["scanning"] = True
    try:
        res = trends.scan_streamers(names, 1)
    finally:
        state["scanning"] = False
        cfg = load()
        cfg["last_scan"] = time.time()
        _save(cfg)
    sent = 0
    for v in res.get("videos") or []:
        vph, age = v.get("views_per_hour"), v.get("age_hours")
        if vph and age is not None and age <= 24 and vph >= cfg["streamer_vph"]:
            if notify("streamers", v["id"], f"Clip it now: {v['channel']}",
                      f"{v['title']}\n{_n(v['views'])} views in {age:.0f}h ({_n(vph)}/hour)", ["rotating_light"], 4, v["url"]):
                sent += 1
    return sent


def check_posts(now: dt.datetime | None = None) -> None:
    """30 minutes before a post that is still 'to do' (not scheduled in YouTube Studio, not automatic)."""
    if publisher.load_settings()["approved"]:
        return  # automatic mode uploads by itself
    now = now or dt.datetime.now()
    names = {c["id"]: c["name"] for c in channel_stats.load_config()["channels"]}
    for it in publisher.load_queue():
        if it["status"] != "waiting" or not it.get("when"):
            continue
        t = dt.datetime.fromisoformat(it["when"])
        if now <= t <= now + dt.timedelta(minutes=30):
            notify("posts", f"{it['id']}:{it['when']}", f"Post at {it['when'][11:16]}: {names.get(it['cid'], it['cid'])}",
                   f"{it['title']}\nIt isn't scheduled in YouTube Studio yet.", ["alarm_clock"], 4)


def weekly_report(now: dt.datetime | None = None) -> None:
    now = now or dt.datetime.now()
    if now.weekday() != 0 or now.hour < 9:
        return
    week = now.strftime("%G-W%V")
    cfg = load()
    if not cfg["enabled"] or not cfg["on"]["weekly"] or f"weekly:{week}" in cfg["sent"]:
        return
    try:
        r = channel_stats.analyze(now)
    except Exception:
        return
    t, g = r["totals"], r["goal"]
    lines = [f"Views this week: {_n(t.get('week'))}" + (f" (last week {_n(t.get('prev_week'))})" if t.get("prev_week") else "")]
    if g.get("views"):
        lines.append(f"Goal: {_n(g.get('done'))} of {_n(g['views'])} ({g.get('days_left')} days left)")
    if g.get("needed_per_day") is not None:
        lines.append(f"Needed per day from now: {_n(g['needed_per_day'])}")
    best = (r.get("top") or [None])[0]
    if best:
        lines.append(f"Best video: {best.get('title', '')} (+{_n(best.get('gain'))})")
    notify("weekly", week, "Your week", "\n".join(lines), ["bar_chart"])


# ---------- background ----------

def start_background() -> None:
    channel_stats.on_snapshot.append(check_viral)

    def loop():
        while True:
            try:
                cfg = load()
                if cfg["enabled"]:
                    check_posts()
                    weekly_report()
                    if cfg["on"]["streamers"] and time.time() - cfg["last_scan"] > STREAMER_SCAN_HOURS * 3600 and not state["scanning"]:
                        threading.Thread(target=scan_streamers, daemon=True).start()
            except Exception as exc:
                state["last_error"] = str(exc)[:300]
            time.sleep(60)

    threading.Thread(target=loop, daemon=True).start()
