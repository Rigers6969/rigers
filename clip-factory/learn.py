"""Learn what works: which of your videos get the most views per day, and what they have in common.

Compares groups of videos (clip length, who the clip is from, title style, posting time, Shorts vs
long, channel) by their median views per day, so one huge outlier can't fool it. A finding needs at
least 3 videos in the group. The results also go back into the AI that picks moments and writes
titles ("on this channel, clips like these did best").
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import statistics
from pathlib import Path
from typing import Optional

import channel_stats
import publisher

APP_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = APP_DIR / "output"
INSIGHTS_FILE = APP_DIR / "insights.json"
MIN_VIDEOS = 6        # fewer than this: "not enough data yet"
MIN_GROUP = 3         # a group needs this many videos to count
MIN_AGE_DAYS = 1.0    # brand-new videos haven't had a fair chance yet
LENGTHS = [(0, 20, "under 20 s"), (20, 35, "20-35 s"), (35, 50, "35-50 s"), (50, 90, "50-90 s"), (90, 10 ** 9, "over 90 s")]
HOURS = [(6, 12, "in the morning (6-12)"), (12, 17, "in the afternoon (12-17)"), (17, 21, "in the evening (17-21)"),
         (21, 24, "at night (21-24)"), (0, 6, "late at night (0-6)")]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower().replace("#shorts", "")).strip()


def _our_clips() -> dict[str, dict]:
    """Normalized title -> what Clip Factory knows about that clip (length, who it's from)."""
    out: dict[str, dict] = {}
    if not OUTPUT_DIR.exists():
        return out
    for run_file in OUTPUT_DIR.glob("*/run.json"):
        try:
            run = json.loads(run_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        src = ""
        try:
            side = Path(run.get("source") or "")
            src = json.loads(side.with_name(side.name + ".source.json").read_text(encoding="utf-8")).get("channel", "")
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        for c in run.get("clips") or []:
            info = {"length": c.get("length"), "src": src, "kind": (run.get("settings") or {}).get("kind", "")}
            for t in (c.get("title"), (c.get("upload") or {}).get("title")):
                if t:
                    out[_norm(t)] = info
    return out


def gather(now: Optional[dt.datetime] = None) -> list[dict]:
    """Every tracked video with its views per day and everything we know about it."""
    now = now or dt.datetime.now()
    names = {c["id"]: c["name"] for c in channel_stats.load_config()["channels"]}
    latest: dict[str, dict] = {}
    for snap in channel_stats.load_snapshots():  # the newest reading of each channel
        for cid, ch in (snap.get("channels") or {}).items():
            latest[cid] = ch
    clips = _our_clips()
    queued = {i.get("video_id"): i for i in publisher.load_queue() if i.get("video_id")}
    out = []
    for cid, ch in latest.items():
        for vid, v in (ch.get("vids") or {}).items():
            when = None
            if v.get("pt"):
                try:
                    when = dt.datetime.fromisoformat(v["pt"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
                except ValueError:
                    when = None
            if when is None and v.get("p"):
                try:
                    when = dt.datetime.fromisoformat(v["p"] + "T12:00")
                except ValueError:
                    continue
            if when is None:
                continue
            age = (now - when).total_seconds() / 86400
            if age < MIN_AGE_DAYS:
                continue
            ours = clips.get(_norm(v.get("t", ""))) or {}
            q = queued.get(vid)
            if q and not ours:
                ours = clips.get(_norm(q.get("title", ""))) or {}
            length = v.get("d") or ours.get("length")
            out.append({
                "id": vid, "cid": cid, "channel": names.get(cid, cid), "title": v.get("t", ""), "views": v["v"],
                "per_day": v["v"] / max(1.0, age), "age_days": round(age, 1), "short": bool(v.get("s")),
                "length": float(length) if length else None, "src": v.get("src") or ours.get("src") or "",
                "hour": when.hour if v.get("pt") else None, "weekday": when.weekday(),
                "url": f"https://www.youtube.com/{'shorts/' if v.get('s') else 'watch?v='}{vid}",
            })
    return out


def _title_traits(title: str) -> list[str]:
    t = title.strip()
    words = t.split()
    traits = []
    if re.search(r"\d", t):
        traits.append("Titles with a number")
    if "?" in t:
        traits.append("Titles that ask a question")
    if any(len(w) > 2 and w.isupper() and w.isalpha() for w in words):
        traits.append("Titles with a word in CAPITALS")
    if len(words) <= 6:
        traits.append("Short titles (6 words or less)")
    elif len(words) >= 11:
        traits.append("Long titles (11+ words)")
    if re.match(r"(?i)^(when|this|how|why|what)\b", t):
        traits.append(f'Titles starting with "{words[0].capitalize()}"')
    return traits


def _groups(videos: list[dict]) -> dict[str, dict[str, list[float]]]:
    g: dict[str, dict[str, list[float]]] = {k: {} for k in ("length", "src", "title", "hour", "weekday", "type", "channel")}
    for v in videos:
        add = lambda dim, key: g[dim].setdefault(key, []).append(v["per_day"])  # noqa: E731
        if v["length"]:
            add("length", next(lbl for lo, hi, lbl in LENGTHS if lo <= v["length"] < hi))
        if v["src"]:
            add("src", v["src"])
        for trait in _title_traits(v["title"]):
            add("title", trait)
        if v["hour"] is not None:
            add("hour", next(lbl for lo, hi, lbl in HOURS if lo <= v["hour"] < hi))
        add("weekday", WEEKDAYS[v["weekday"]])
        add("type", "Shorts" if v["short"] else "Long videos")
        add("channel", v["channel"])
    return g


SENTENCE = {
    "length": "Clips {key} long", "src": "Clips from {key}", "title": "{key}", "hour": "Videos posted {key}",
    "weekday": "Videos posted on {key}", "type": "{key}", "channel": "Videos on {key}",
}


def analyze(cid: str = "", now: Optional[dt.datetime] = None) -> dict:
    videos = [v for v in gather(now) if not cid or v["cid"] == cid]
    if len(videos) < MIN_VIDEOS:
        return {"enough": False, "count": len(videos), "need": MIN_VIDEOS, "findings": [], "best": [], "worst": []}
    base = statistics.median(v["per_day"] for v in videos) or 1.0
    findings = []
    for dim, groups in _groups(videos).items():
        if dim == "channel" and cid:
            continue
        for key, vals in groups.items():
            if len(vals) < MIN_GROUP or len(vals) == len(videos):
                continue
            ratio = statistics.median(vals) / base
            if 0.77 < ratio < 1.3:
                continue
            what = SENTENCE[dim].format(key=key)
            text = (f"{what} get {ratio:.1f}x more views than your average" if ratio >= 1 else
                    f"{what} get {1 / ratio:.1f}x fewer views than your average")
            findings.append({"dim": dim, "key": key, "ratio": round(ratio, 2), "n": len(vals), "good": ratio >= 1,
                             "text": f"{text} ({len(vals)} videos)."})
    # strongest first, but a pattern seen in many videos counts more than one seen in 3
    findings.sort(key=lambda f: -math.log(f["ratio"] if f["good"] else 1 / f["ratio"]) * math.sqrt(f["n"]))
    ranked = sorted(videos, key=lambda v: -v["per_day"])
    rnd = lambda v: dict(v, per_day=round(v["per_day"]))  # noqa: E731
    report = {"enough": True, "count": len(videos), "median_per_day": round(base), "findings": findings[:12],
              "best": [rnd(v) for v in ranked[:5]], "worst": [rnd(v) for v in ranked[-3:][::-1]],
              "advice": _advice(findings, ranked)}
    _save_insights(cid, report)
    return report


def _advice(findings: list[dict], ranked: list[dict]) -> dict:
    """Concrete settings to try, from the strongest good findings."""
    adv: dict = {}
    good = [f for f in findings if f["good"]]
    length = next((f for f in good if f["dim"] == "length"), None)
    if length:
        lo, hi = next((a, b) for a, b, lbl in LENGTHS if lbl == length["key"])
        adv["clip_length"] = [max(10, lo), min(90, hi if hi < 10 ** 9 else 90)]
    adv["creators"] = [f["key"] for f in good if f["dim"] == "src"][:5]
    hour = next((f for f in good if f["dim"] == "hour"), None)
    if hour:
        adv["post_hours"] = hour["key"]
    adv["title_tips"] = [f["key"] for f in good if f["dim"] == "title"][:3]
    adv["best_titles"] = [v["title"] for v in ranked[:5]]
    return adv


def _save_insights(cid: str, report: dict) -> None:
    try:
        data = json.loads(INSIGHTS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    adv = report["advice"]
    parts = []
    if adv.get("best_titles"):
        parts.append("Clips like these got the most views on this channel: " + "; ".join(f'"{t}"' for t in adv["best_titles"][:5]) + ".")
    if adv.get("creators"):
        parts.append("Clips of " + ", ".join(adv["creators"]) + " did especially well.")
    if adv.get("clip_length"):
        parts.append(f"Clips {adv['clip_length'][0]}-{adv['clip_length'][1]} seconds long did best.")
    if adv.get("title_tips"):
        parts.append("Title styles that worked: " + "; ".join(adv["title_tips"]) + ".")
    data[cid or "all"] = {"updated": dt.datetime.now().isoformat(timespec="minutes"), "hint": " ".join(parts)}
    INSIGHTS_FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")


def hint_for(channel_name: str = "") -> str:
    """What the AI should know when making clips for this channel (empty if nothing was learned yet)."""
    try:
        data = json.loads(INSIGHTS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    cid = next((c["id"] for c in channel_stats.load_config()["channels"]
                if channel_name and c["name"].strip().lower() == channel_name.strip().lower()), "")
    entry = data.get(cid) or data.get("all") or {}
    return ("\nWhat worked before: " + entry["hint"]) if entry.get("hint") else ""


def explain(report: dict, brain) -> str:
    """Plain-language advice from the AI, based only on the numbers above."""
    if not report.get("enough") or brain is None:
        return ""
    facts = "\n".join(f["text"] for f in report["findings"]) or "No clear differences yet."
    best = "\n".join(f'- "{v["title"]}" ({v["per_day"]:,} views/day, {v["channel"]})' for v in report["best"])
    prompt = ("You coach a small YouTube Shorts creator. Using ONLY these facts about their own videos, give 4 short, "
              "concrete things to do next week (one sentence each, simple English, no jargon). Don't invent numbers.\n\n"
              f"Facts:\n{facts}\n\nTheir best videos:\n{best}\n\n"
              'Answer ONLY with JSON: {"actions": ["...", "...", "...", "..."]}')
    for _ in range(2):
        try:
            raw, who = brain.ask(prompt)
            m = re.search(r"\{.*\}", raw or "", re.S)
            acts = [str(a).strip() for a in (json.loads(m.group(0)) if m else {}).get("actions") or [] if str(a).strip()]
        except Exception:
            continue
        if acts:
            return "\n".join(f"- {a[:300]}" for a in acts[:5]) + f"\n(written by {who})"
    return ""
