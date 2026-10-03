"""My channels - views, subscribers and the goal, for all your channels together.

Every few hours (and on "Refresh now") it takes a snapshot of each channel:
subscribers, total views, and the views of its recent videos/Shorts. Views
gained = the difference between snapshots, so it can say "this week: 100K
views, +40% on last week" and how far you are from the goal (e.g. 10M views
by December 1).

Where the numbers come from:
  - a YouTube Data API key, if you have one (exact numbers; it's found
    automatically in Wayne Factory's config.json, or paste one in)
  - otherwise yt-dlp reads the channel pages (no setup; YouTube rounds
    those numbers, e.g. "1.2K", so small changes can look bumpy)
Watch hours aren't public - YouTube Studio's Earn tab shows those.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Optional

import requests

import trends

APP_DIR = Path(__file__).resolve().parent
CONFIG_FILE = APP_DIR / "my_channels.json"
SNAP_FILE = APP_DIR / "channel_snapshots.json"
API = os.environ.get("CF_YT_API_BASE", "https://www.googleapis.com/youtube/v3")
on_snapshot: list = []    # called with each new snapshot (phone alerts use it)
MAX_SNAPSHOTS = 400        # ~4 months at a few a day
VIDEOS_PER_CHANNEL = 50    # recent uploads tracked one by one
SHORT_MAX_S = 180          # Shorts can be up to 3 minutes

DEFAULT_CONFIG = {
    "channels": [
        {"id": "paper", "name": "Paper Trail", "ref": ""},
        {"id": "history", "name": "History", "ref": ""},
        {"id": "science", "name": "Science", "ref": ""},
        {"id": "clips", "name": "Hot Mic Moments", "ref": ""},
        {"id": "streams", "name": "Chat Lost It", "ref": ""},
    ],
    "goal_views": 10_000_000,
    "start": "2026-10-03",
    "deadline": "2026-12-01",
    "api_key": "",
    "added": [],   # channels added to everyone's list once (removing one later keeps it removed)
}
NEW_CHANNELS = [{"id": "streams", "name": "Chat Lost It", "ref": ""}]
_lock = threading.Lock()


class StatsError(Exception):
    pass


# ---------- config ----------

def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            cfg.update({k: v for k, v in saved.items() if k in DEFAULT_CONFIG})
            new = [c for c in NEW_CHANNELS if c["id"] not in cfg["added"]]
            if new:  # a channel added after this list was saved: put it in once
                for c in new:
                    if all(x["id"] != c["id"] for x in cfg["channels"]) and len(cfg["channels"]) < 8:
                        cfg["channels"].append(dict(c))
                    cfg["added"].append(c["id"])
                CONFIG_FILE.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        pass
    return cfg


def save_config(update: dict) -> dict:
    with _lock:
        cfg = load_config()
        if isinstance(update.get("channels"), list):
            chans = []
            for i, c in enumerate(update["channels"][:8]):
                name = str(c.get("name") or "").strip()[:40] or f"Channel {i + 1}"
                cid = re.sub(r"[^a-z0-9]+", "-", str(c.get("id") or name).lower()).strip("-")[:20] or f"ch{i + 1}"
                chans.append({"id": cid, "name": name, "ref": str(c.get("ref") or "").strip()[:200]})
            cfg["channels"] = chans
        for key in ("goal_views",):
            if key in update:
                try:
                    cfg[key] = max(1000, int(float(update[key])))
                except (TypeError, ValueError):
                    pass
        for key in ("start", "deadline"):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(update.get(key) or "")):
                cfg[key] = update[key]
        if "api_key" in update and update["api_key"] is not None:
            cfg["api_key"] = str(update["api_key"]).strip()[:100]
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return cfg


def api_key(cfg: dict) -> tuple[str, str]:
    """(key, where it came from) - the pasted one, else Wayne Factory's."""
    if cfg.get("api_key"):
        return cfg["api_key"], "pasted here"
    for path in (APP_DIR.parent / "wayne-factory-lite" / "config.json", APP_DIR.parent / "config.json"):
        try:
            key = json.loads(path.read_text(encoding="utf-8")).get("YOUTUBE_API_KEY") or ""
        except (OSError, json.JSONDecodeError, AttributeError):
            key = ""
        if key and "YOUR" not in key.upper():
            return key, f"found in {path.parent.name}/config.json"
    return "", ""


# ---------- fetching ----------

def _api(path: str, key: str, **params) -> dict:
    try:
        resp = requests.get(f"{API}/{path}", params=dict(params, key=key), timeout=20)
    except requests.RequestException as exc:
        raise StatsError(f"can't reach YouTube: {exc}") from exc
    if resp.status_code in (400, 403):
        msg = ""
        try:
            msg = resp.json().get("error", {}).get("message", "")
        except ValueError:
            pass
        if "quota" in msg.lower():
            raise StatsError("the API key's daily quota is used up - numbers come back tomorrow")
        raise StatsError(f"YouTube refused the API key ({re.sub('<[^>]+>', '', msg)[:120] or resp.status_code})")
    resp.raise_for_status()
    return resp.json()


def _iso_seconds(d: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    days, h, mi, s = (int(x or 0) for x in m.groups())
    return days * 86400 + h * 3600 + mi * 60 + s


def fetch_api(ref: str, key: str) -> dict:
    ref = ref.strip()
    m = re.search(r"(UC[\w-]{22})", ref)
    handle = trends.channel_url(ref).rsplit("/", 1)[-1]
    params = {"part": "statistics,contentDetails,snippet"}
    if m:
        params["id"] = m.group(1)
    elif handle.startswith("@"):
        params["forHandle"] = handle
    else:
        raise StatsError("use the channel's @handle or its link")
    items = _api("channels", key, **params).get("items") or []
    if not items:
        raise StatsError("YouTube doesn't know that channel - check the @handle")
    ch = items[0]
    st = ch.get("statistics", {})
    uploads = ch.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    vids = {}
    if uploads:
        pl = _api("playlistItems", key, part="contentDetails", playlistId=uploads, maxResults=VIDEOS_PER_CHANNEL)
        ids = [it["contentDetails"]["videoId"] for it in pl.get("items") or [] if it.get("contentDetails", {}).get("videoId")]
        if ids:
            for v in _api("videos", key, part="statistics,contentDetails,snippet", id=",".join(ids)).get("items") or []:
                secs = _iso_seconds(v.get("contentDetails", {}).get("duration", ""))
                sn = v.get("snippet", {})
                src = re.search(r"(?m)^From:\s*(.+?)(?:\s*\(@[\w.\-]+\))?\s*$", sn.get("description") or "")
                vids[v["id"]] = {"t": sn.get("title", "")[:120], "v": int(v.get("statistics", {}).get("viewCount", 0)),
                                 "s": secs <= SHORT_MAX_S, "p": (sn.get("publishedAt") or "")[:10],
                                 # for "Learn what works": length, exact posting time, who the clip is from
                                 "d": secs, "pt": sn.get("publishedAt") or "", "src": src.group(1)[:60] if src else ""}
    return {"title": ch.get("snippet", {}).get("title", ""), "subs": int(st.get("subscriberCount", 0)),
            "views": int(st.get("viewCount", 0)), "videos": int(st.get("videoCount", 0)), "source": "api", "vids": vids}


def fetch_public(ref: str) -> dict:
    """No API key: read the channel's own pages (Videos, Shorts, Live tabs)."""
    base = trends.channel_url(ref)
    vids, title, subs, loaded = {}, "", 0, False
    for tab in ("videos", "shorts", "streams"):
        try:
            with trends._ydl_flat(VIDEOS_PER_CHANNEL) as ydl:
                info = ydl.extract_info(f"{base}/{tab}", download=False) or {}
        except Exception as exc:
            if tab == "videos" and not loaded:
                last = trends.clean_error(exc)
            continue
        loaded = True
        title = title or info.get("channel") or info.get("uploader") or ""
        subs = subs or int(info.get("channel_follower_count") or 0)
        for e in info.get("entries") or []:
            if isinstance(e, dict) and e.get("id") and e.get("view_count") is not None:
                ts = e.get("timestamp")
                vids[e["id"]] = {"t": (e.get("title") or "")[:120], "v": int(e["view_count"]),
                                 "s": tab == "shorts" or (e.get("duration") or 999) <= SHORT_MAX_S,
                                 "p": dt.date.fromtimestamp(ts).isoformat() if ts else "",
                                 "d": e.get("duration") or 0}
    if not loaded:
        raise StatsError(f"couldn't read that channel ({locals().get('last', 'not found')}) - check the @handle")
    return {"title": title, "subs": subs, "views": sum(v["v"] for v in vids.values()), "videos": len(vids),
            "source": "public", "vids": vids}


# ---------- snapshots ----------

def load_snapshots() -> list[dict]:
    try:
        data = json.loads(SNAP_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def take_snapshot() -> dict:
    """Read every configured channel now and store the result."""
    cfg = load_config()
    key, _where = api_key(cfg)
    snap = {"at": dt.datetime.now().isoformat(timespec="seconds"), "channels": {}, "errors": {}}
    for c in cfg["channels"]:
        if not c["ref"]:
            continue
        try:
            snap["channels"][c["id"]] = fetch_api(c["ref"], key) if key else fetch_public(c["ref"])
        except StatsError as exc:
            if key and "refused" in str(exc):
                try:  # a bad key shouldn't stop the numbers - fall back to the public pages
                    snap["channels"][c["id"]] = fetch_public(c["ref"])
                    snap["errors"][c["id"]] = f"{exc} - used the public pages instead"
                    continue
                except StatsError:
                    pass
            snap["errors"][c["id"]] = str(exc)
        except Exception as exc:
            snap["errors"][c["id"]] = f"unexpected problem: {trends.clean_error(exc)}"
    with _lock:
        snaps = load_snapshots()
        snaps.append(snap)
        SNAP_FILE.write_text(json.dumps(snaps[-MAX_SNAPSHOTS:]), encoding="utf-8")
    for hook in on_snapshot:
        try:
            hook(snap)
        except Exception:
            pass
    return snap


# ---------- analysis ----------

def _t(s: dict) -> dt.datetime:
    return dt.datetime.fromisoformat(s["at"])


def _at_or_before(snaps: list[dict], when: dt.datetime, cid: str) -> Optional[dict]:
    """The last snapshot of a channel at or before `when` (or the first one after, if none before)."""
    have = [s for s in snaps if cid in s["channels"]]
    before = [s for s in have if _t(s) <= when]
    return before[-1] if before else (have[0] if have else None)


def _gain(snaps, cid, frm: dt.datetime, to: dt.datetime) -> Optional[int]:
    a, b = _at_or_before(snaps, frm, cid), _at_or_before(snaps, to, cid)
    if not a or not b or _t(b) <= _t(a):
        return None
    return max(0, b["channels"][cid]["views"] - a["channels"][cid]["views"])


def _video_gains(snaps, cid, frm, to) -> dict:
    a, b = _at_or_before(snaps, frm, cid), _at_or_before(snaps, to, cid)
    if not a or not b or a is b:
        return {}
    old, new = a["channels"][cid]["vids"], b["channels"][cid]["vids"]
    out = {}
    for vid, v in new.items():
        base = old.get(vid, {}).get("v", 0 if vid not in old else v["v"])
        out[vid] = dict(v, gain=max(0, v["v"] - base), new=vid not in old)
    return out


def analyze(now: Optional[dt.datetime] = None) -> dict:
    cfg = load_config()
    snaps = load_snapshots()
    now = now or dt.datetime.now()
    start = dt.datetime.fromisoformat(cfg["start"])
    deadline = dt.datetime.fromisoformat(cfg["deadline"]) + dt.timedelta(days=1)
    week_ago, two_weeks = now - dt.timedelta(days=7), now - dt.timedelta(days=14)
    latest = snaps[-1] if snaps else None
    channels, top = [], []
    totals = {"week": 0, "prev_week": 0, "since_start": 0, "week_shorts": 0, "week_long": 0,
              "all_time": 0, "subs": 0, "new_week_views": 0, "new_week_videos": 0}
    recent_top = []
    week_ago_date = (now - dt.timedelta(days=7)).date().isoformat()
    have_week = have_prev = False
    for c in cfg["channels"]:
        cid = c["id"]
        last = next((s["channels"][cid] for s in reversed(snaps) if cid in s["channels"]), None)
        err = latest["errors"].get(cid) if latest else None
        week = _gain(snaps, cid, week_ago, now)
        prev = _gain(snaps, cid, two_weeks, week_ago)
        since = _gain(snaps, cid, start, now)
        gains = _video_gains(snaps, cid, week_ago, now)
        shorts = sum(v["gain"] for v in gains.values() if v["s"])
        longs = sum(v["gain"] for v in gains.values() if not v["s"])
        best = max(gains.items(), key=lambda kv: kv[1]["gain"], default=None)
        for vid, v in gains.items():
            if v["gain"] > 0:
                top.append({"id": vid, "channel": c["name"], "cid": cid, "title": v["t"], "gain": v["gain"], "short": v["s"], "views": v["v"]})
        if week is not None:
            have_week = True
            totals["week"] += week
        if prev is not None:
            have_prev = True
            totals["prev_week"] += prev
        totals["since_start"] += since or 0
        # these work from a single check: lifetime numbers and videos posted in the last 7 days
        new_vids = [v for v in (last["vids"].values() if last else []) if v.get("p") and v["p"] >= week_ago_date]
        new_views = sum(v["v"] for v in new_vids)
        if last:
            totals["all_time"] += last["views"]
            totals["subs"] += last["subs"]
            totals["new_week_views"] += new_views
            totals["new_week_videos"] += len(new_vids)
            for vid, v in last["vids"].items():
                recent_top.append({"id": vid, "channel": c["name"], "cid": cid, "title": v["t"], "views": v["v"],
                                   "short": v["s"], "posted": v.get("p") or ""})
        totals["week_shorts"] += shorts
        totals["week_long"] += longs
        channels.append({
            "id": cid, "name": c["name"], "ref": c["ref"], "title": last["title"] if last else "",
            "subs": last["subs"] if last else None, "views": last["views"] if last else None,
            "videos": last["videos"] if last else None, "source": last["source"] if last else None,
            "week": week, "prev_week": prev, "since_start": since, "error": err,
            "week_shorts": shorts, "week_long": longs,
            "new_week_views": new_views if last else None, "new_week_videos": len(new_vids) if last else None,
            "best": {"id": best[0], "title": best[1]["t"], "gain": best[1]["gain"], "short": best[1]["s"]} if best and best[1]["gain"] > 0 else None,
        })
    # daily views per channel for the last 14 days (gain between the last snapshots of consecutive days)
    days = []
    for back in range(13, -1, -1):
        day = (now - dt.timedelta(days=back)).date()
        end = dt.datetime.combine(day, dt.time.max)
        begin = dt.datetime.combine(day, dt.time.min) - dt.timedelta(seconds=1)
        row = {"date": day.isoformat()}
        for c in cfg["channels"]:
            g = _gain(snaps, c["id"], begin, min(end, now))
            row[c["id"]] = g if g is not None else None
        days.append(row)
    days_left = max(0, (deadline - now).days)
    pace = totals["week"] / 7 if have_week else None
    need = max(0, cfg["goal_views"] - totals["since_start"])
    goal = {
        "views": cfg["goal_views"], "start": cfg["start"], "deadline": cfg["deadline"], "done": totals["since_start"],
        "days_left": days_left, "needed_per_day": round(need / days_left) if days_left else need,
        "pace_per_day": round(pace) if pace is not None else None,
        "projection": round(totals["since_start"] + pace * days_left) if pace is not None else None,
    }
    top.sort(key=lambda v: -v["gain"])
    recent_top.sort(key=lambda v: -v["views"])
    key, where = api_key(cfg)
    first_snap = snaps[0]["at"] if snaps else None
    return {
        "channels": channels, "totals": totals, "goal": goal, "days": days, "top": top[:8], "recent_top": recent_top[:8],
        "have_week": have_week, "have_prev": have_prev, "latest_at": latest["at"] if latest else None,
        "first_at": first_snap, "snapshots": len(snaps), "source": "api" if key else "public", "key_where": where,
        "config": {k: v for k, v in cfg.items() if k != "api_key"} | {"api_key_set": bool(cfg.get("api_key"))},
    }


# ---------- coach ----------

COACH_PROMPT = """You are a YouTube growth coach. A creator runs these channels and has a goal of {goal:,} views across all of them by {deadline} ({days_left} days left). Views so far since {start}: {done:,}. Needed per day from now: {need:,}. Current pace: {pace} per day.

This week, channel by channel:
{rows}

Top videos this week (views gained):
{top}

Give the 3 most useful actions for next week, specific to these numbers (which channel to push, which video to make more of, Shorts vs long videos). Plain simple English for a beginner.
Answer ONLY with JSON: {{"headline": "one sentence: are they on track?", "actions": ["...", "...", "..."]}}"""


def coach(report: dict, brain=None) -> dict:
    g = report["goal"]
    rows = "\n".join(
        f"- {c['name']}: {c['week'] or 0:,} views this week (last week {c['prev_week'] or 0:,}), "
        f"{c['subs'] or 0:,} subscribers, Shorts {c['week_shorts']:,} / long videos {c['week_long']:,}"
        for c in report["channels"] if c["ref"])
    top = "\n".join(f"- [{v['channel']}] {v['title']} ({'Short' if v['short'] else 'long video'}): +{v['gain']:,}"
                    for v in report["top"][:6]) or "- (not enough data yet)"
    if brain is not None and report["have_week"]:
        prompt = COACH_PROMPT.format(goal=g["views"], deadline=g["deadline"], days_left=g["days_left"], start=g["start"],
                                     done=g["done"], need=g["needed_per_day"], pace=f"{g['pace_per_day']:,}" if g["pace_per_day"] is not None else "unknown",
                                     rows=rows, top=top)
        for _ in range(3):
            try:
                raw, who = brain.ask(prompt)
                d = json.loads(raw) if raw.strip().startswith("{") else json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            except Exception:
                continue
            acts = [str(a).strip()[:300] for a in d.get("actions") or [] if str(a).strip()]
            if d.get("headline") and len(acts) >= 2:
                return {"headline": str(d["headline"])[:300], "actions": acts[:4], "by": who}
    # built-in coach
    acts, chans = [], [c for c in report["channels"] if c["ref"] and c["week"] is not None]
    if not report["have_week"]:
        return {"headline": "Collecting numbers - the coach needs about a day of snapshots to compare.",
                "actions": ["Keep Clip Factory running; it checks your channels every 3 hours.", "Click Refresh now once a day."], "by": "built-in"}
    if chans:
        best = max(chans, key=lambda c: c["week"])
        acts.append(f"{best['name']} brought the most views this week ({best['week']:,}). Give it extra uploads next week.")
        weak = min(chans, key=lambda c: c["week"])
        if weak is not best:
            acts.append(f"{weak['name']} is slowest ({weak['week']:,}). Copy the topic and thumbnail style of its best video, or post more Shorts from its videos.")
    if report["top"]:
        t = report["top"][0]
        acts.append(f"Your top video this week was \"{t['title']}\" on {t['channel']} (+{t['gain']:,}). Make 2 more on the same topic.")
    tot = report["totals"]
    if tot["week_shorts"] > 2 * max(1, tot["week_long"]):
        acts.append("Most views come from Shorts - end every Short by pointing to the full video so viewers also build watch hours.")
    g = report["goal"]
    on_track = g["projection"] is not None and g["projection"] >= g["views"]
    head = (f"On track: at this pace you'd reach {g['projection']:,} views by {g['deadline']}." if on_track else
            f"Behind the goal: you need about {g['needed_per_day']:,} views a day; this week averaged {g['pace_per_day'] or 0:,}.")
    return {"headline": head, "actions": acts[:4], "by": "built-in"}


# ---------- background refresh ----------

_refresh_state = {"running": False, "last_error": None}


def refresh_async() -> bool:
    if _refresh_state["running"]:
        return False
    _refresh_state["running"] = True

    def work():
        try:
            take_snapshot()
            _refresh_state["last_error"] = None
        except Exception as exc:
            _refresh_state["last_error"] = str(exc)
        finally:
            _refresh_state["running"] = False

    threading.Thread(target=work, daemon=True).start()
    return True


def start_background(every_hours: float = 3) -> None:
    """Snapshot on start-up (if there's any channel set), then every few hours while the app runs."""
    def loop():
        while True:
            if any(c["ref"] for c in load_config()["channels"]):
                last = load_snapshots()[-1:] or [None]
                if not last[0] or time.time() - _t(last[0]).timestamp() > every_hours * 3600 - 60:
                    refresh_async()
            time.sleep(600)

    threading.Thread(target=loop, daemon=True).start()


def refresh_running() -> bool:
    return _refresh_state["running"]
