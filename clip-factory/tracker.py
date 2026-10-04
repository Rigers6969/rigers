"""Posting goals and calendar: e.g. 10 videos per channel per day, counted automatically.

Counting, per channel and day:
  - channels with an @handle (My channels): the videos YouTube shows, read every 3 hours. Every video
    ever seen is remembered here, so the count stays right after it drops out of the latest-50 list.
  - channels without one: Publish-tab posts marked scheduled/uploaded whose time has passed.
  - plus your own +1 / -1 (e.g. for TikTok, or to fix a count).
A goal closes by itself when every channel reaches it: each day (per day), each week (per week), or
once (one-time goal - it then moves to the finished list).
"""
from __future__ import annotations

import datetime as dt
import json
import threading
import time
from collections import Counter
from pathlib import Path

import channel_stats
import publisher

APP_DIR = Path(__file__).resolve().parent
FILE = APP_DIR / "goals.json"
SEEN_FILE = APP_DIR / "posts_seen.json"
PERIODS = ("day", "week", "total")
_lock = threading.Lock()


def load() -> dict:
    try:
        g = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        g = {}
    g.setdefault("target", 10)
    g.setdefault("period", "day")
    g.setdefault("per_channel", {})          # cid -> its own target (else the main one)
    g.setdefault("start", dt.date.today().isoformat())  # one-time goals count from here
    g.setdefault("manual", {})               # "YYYY-MM-DD" -> {cid: +/- n}
    g.setdefault("finished", [])             # one-time goals that were completed
    if "since" not in g:                     # the day tracking began: earlier days are never "missed"
        g["since"] = dt.date.today().isoformat()
        save(g)
    return g


def save(g: dict) -> None:
    with _lock:
        tmp = FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(g, indent=1), encoding="utf-8")
        tmp.replace(FILE)


def update(changes: dict) -> dict:
    g = load()
    if "target" in changes:
        try:
            g["target"] = max(1, min(500, int(changes["target"])))
        except (TypeError, ValueError):
            pass
    if changes.get("period") in PERIODS and changes["period"] != g["period"]:
        g["period"] = changes["period"]
        if g["period"] == "total":
            g["start"] = dt.date.today().isoformat()
    for cid, n in (changes.get("per_channel") or {}).items():
        try:
            n = int(n)
        except (TypeError, ValueError):
            continue
        if n > 0:
            g["per_channel"][cid] = min(500, n)
        else:
            g["per_channel"].pop(cid, None)
    if changes.get("restart"):  # start a new one-time goal from today
        g["start"] = dt.date.today().isoformat()
    save(g)
    return g


def adjust(day: str, cid: str, delta: int) -> dict:
    dt.date.fromisoformat(day)  # raises on a bad date
    g = load()
    m = g["manual"].setdefault(day, {})
    m[cid] = max(-500, min(500, m.get(cid, 0) + int(delta)))
    if not m[cid]:
        m.pop(cid)
    if not m:
        g["manual"].pop(day)
    save(g)
    return g


def _local_day(v: dict) -> str:
    if v.get("pt"):
        try:
            return dt.datetime.fromisoformat(v["pt"].replace("Z", "+00:00")).astimezone().date().isoformat()
        except ValueError:
            pass
    return v.get("p") or ""


def _seen() -> dict:
    """{cid: {video id: day}} - every video ever seen in a channel check, so counts don't shrink."""
    try:
        seen = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        seen = {}
    changed = False
    for snap in channel_stats.load_snapshots()[-20:]:
        for cid, ch in (snap.get("channels") or {}).items():
            box = seen.setdefault(cid, {})
            for vid, v in (ch.get("vids") or {}).items():
                day = _local_day(v)
                if day and box.get(vid) != day:
                    box[vid] = day
                    changed = True
    if changed:
        with _lock:
            SEEN_FILE.write_text(json.dumps(seen), encoding="utf-8")
    return seen


def daily_counts() -> dict[str, Counter]:
    """{cid: Counter(day -> posts)} including your +1/-1."""
    chans = channel_stats.load_config()["channels"]
    seen = _seen()
    now = dt.datetime.now()
    out: dict[str, Counter] = {c["id"]: Counter() for c in chans}
    for c in chans:
        if c.get("ref") and seen.get(c["id"]):  # YouTube knows this channel
            out[c["id"]].update(seen[c["id"]].values())
    for it in publisher.load_queue():  # channels YouTube can't read: count what you marked as posted
        cid = it.get("cid")
        if cid in out and not (next((c for c in chans if c["id"] == cid), {}).get("ref") and seen.get(cid)):
            if it.get("status") in ("scheduled", "uploaded") and it.get("when") and dt.datetime.fromisoformat(it["when"]) <= now:
                out[cid][it["when"][:10]] += 1
    for day, m in load()["manual"].items():
        for cid, n in m.items():
            if cid in out:
                out[cid][day] += n
    return out


def planned() -> dict[str, Counter]:
    """Posts still to come from the Publish schedule: {cid: Counter(day -> n)}."""
    now = dt.datetime.now()
    out: dict[str, Counter] = {}
    for it in publisher.load_queue():
        if it.get("when") and it.get("status") != "failed" and dt.datetime.fromisoformat(it["when"]) > now:
            out.setdefault(it.get("cid") or "", Counter())[it["when"][:10]] += 1
    return out


def _week_start(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def report(weeks: int = 4) -> dict:
    g = load()
    chans = channel_stats.load_config()["channels"]
    counts, plan = daily_counts(), planned()
    today = dt.date.today()
    target = lambda cid: g["per_channel"].get(cid) or g["target"]  # noqa: E731
    first = _week_start(today) - dt.timedelta(weeks=weeks - 2)  # a few weeks back + this week + next week
    days = []
    for i in range(weeks * 7):
        d = first + dt.timedelta(days=i)
        key = d.isoformat()
        row = {"date": key, "future": d > today, "today": d == today, "before": key < g["since"], "channels": {}}
        for c in chans:
            n = max(0, counts[c["id"]][key])
            row["channels"][c["id"]] = {"posted": n, "planned": plan.get(c["id"], Counter())[key]}
        if g["period"] == "day":
            row["closed"] = all(row["channels"][c["id"]]["posted"] >= target(c["id"]) for c in chans) if chans else False
            row["missed"] = not row["closed"] and d < today and not row["before"]
        days.append(row)
    # the current goal: today's, this week's, or the one-time total
    if g["period"] == "day":
        frm, label = today, f"Today ({today:%A %d %B})"
    elif g["period"] == "week":
        frm, label = _week_start(today), f"This week ({_week_start(today):%d %b} - {_week_start(today) + dt.timedelta(days=6):%d %b})"
    else:
        frm, label = dt.date.fromisoformat(g["start"]), f"Since {dt.date.fromisoformat(g['start']):%d %B}"
    to = today if g["period"] != "week" else _week_start(today) + dt.timedelta(days=6)
    current = []
    for c in chans:
        n = sum(max(0, v) for k, v in counts[c["id"]].items() if frm.isoformat() <= k <= to.isoformat())
        current.append({"id": c["id"], "name": c["name"], "posted": n, "target": target(c["id"]),
                        "done": n >= target(c["id"]), "auto": bool(c.get("ref")),
                        "planned": sum(v for k, v in plan.get(c["id"], Counter()).items() if frm.isoformat() <= k <= to.isoformat())})
    all_done = bool(current) and all(x["done"] for x in current)
    if g["period"] == "total" and all_done:  # a one-time goal closes itself and moves to the finished list
        g["finished"].append({"target": g["target"], "start": g["start"], "finished": today.isoformat(),
                              "posted": {x["name"]: x["posted"] for x in current}})
        g["start"] = (today + dt.timedelta(days=1)).isoformat()
        save(g)
    # streak: days (or weeks) in a row with every channel's goal met
    streak = 0
    if g["period"] == "day":
        for row in reversed([r for r in days if not r["future"]]):
            if row["closed"]:
                streak += 1
            elif row["today"]:
                continue  # today isn't over yet
            else:
                break
    return {"goal": {k: g[k] for k in ("target", "period", "per_channel", "start")}, "label": label, "current": current,
            "all_done": all_done, "days": days, "streak": streak, "finished": g["finished"][-10:][::-1],
            "channels": [{"id": c["id"], "name": c["name"], "auto": bool(c.get("ref"))} for c in chans],
            "updated": time.strftime("%H:%M")}
