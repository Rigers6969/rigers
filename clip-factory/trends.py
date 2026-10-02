"""What's going viral right now - for picking long videos worth clipping.

Two ways in, both free and without any API key (yt-dlp reads YouTube's own
pages):
  - your streamer list: each channel's latest videos and past live streams
  - a keyword search: YouTube's own "most viewed this week/today" results

Every video gets:
  views/hour  - views divided by hours since upload: how fast it's blowing up
  vs. normal  - views compared with that channel's usual (median) video:
                3.0x means three times what that streamer normally gets
Shorts, upcoming and still-live streams are left out - only full-length
videos you can actually cut into clips.
"""
from __future__ import annotations

import json
import re
import statistics
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

import moments

APP_DIR = Path(__file__).resolve().parent
STREAMERS_FILE = APP_DIR / "streamers.json"
PODCASTS_FILE = APP_DIR / "podcasts.json"

# a starting list - edit it on the page; a name that doesn't load is flagged there
DEFAULT_STREAMERS = ["@IShowSpeed", "@KaiCenat", "@xQc", "@Jynxzi", "@AdinRoss"]
DEFAULT_PODCASTS = ["@PowerfulJRE", "@lexfridman", "@hubermanlab", "@TheDiaryOfACEO", "@flagrant", "@TheoVon", "@ShawnRyanShow", "@impaulsive"]
LISTS = {"streamers": (STREAMERS_FILE, DEFAULT_STREAMERS), "podcasts": (PODCASTS_FILE, DEFAULT_PODCASTS)}
MIN_PODCAST_S = 20 * 60  # a podcast "episode" - anything shorter is usually already a clip

MIN_LONG_VIDEO_S = 240  # anything shorter isn't worth cutting into several Shorts
PER_TAB = 15

# YouTube's own search filters ("sp" parameter): sorted by view count, videos only, uploaded within...
SEARCH_PERIODS = {"hour": "CAMSBAgBEAE=", "today": "CAMSBAgCEAE=", "week": "CAMSBAgDEAE=", "month": "CAMSBAgEEAE="}
# the same, but only long videos (over 20 minutes) - full podcast episodes
EPISODE_PERIODS = {"hour": "CAMSBggBEAEYAg==", "today": "CAMSBggCEAEYAg==", "week": "CAMSBggDEAEYAg==", "month": "CAMSBggEEAEYAg=="}
PERIOD_DAYS = {"hour": 1, "today": 1, "week": 7, "month": 31}


class TrendError(Exception):
    pass


class _QuietLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def _ydl_flat(limit: int):
    try:
        import yt_dlp
    except ImportError as exc:
        raise TrendError("yt-dlp isn't installed - close the app and double-click start.bat again.") from exc
    return yt_dlp.YoutubeDL({
        "extract_flat": "in_playlist", "playlistend": limit, "skip_download": True,
        "quiet": True, "no_warnings": True, "logger": _QuietLogger(),
        # "2 days ago" -> a real date; without this, flat listings have no upload time
        "extractor_args": {"youtubetab": {"approximate_date": [""]}},
        "socket_timeout": 20,
    })


def clean_error(exc: Exception) -> str:
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(exc))
    msg = re.sub(r"^ERROR:\s*", "", msg)
    msg = re.sub(r"^\[[^\]]+\]\s*", "", msg)
    return msg.strip()[:300]


def load_streamers(kind: str = "streamers") -> list[str]:
    path, default = LISTS.get(kind, LISTS["streamers"])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(x) for x in data if str(x).strip()]
    except (OSError, json.JSONDecodeError):
        pass
    return list(default)


def save_streamers(names: list[str], kind: str = "streamers") -> list[str]:
    seen, clean = set(), []
    for n in names:
        n = n.strip()
        if n and n.lower() not in seen:
            seen.add(n.lower())
            clean.append(n)
    LISTS.get(kind, LISTS["streamers"])[0].write_text(json.dumps(clean[:60], indent=2), encoding="utf-8")
    return clean[:60]


def channel_url(text: str) -> str:
    """'@KaiCenat', 'KaiCenat', or any youtube.com/@... /channel/... link -> the channel's base URL."""
    text = text.strip().rstrip("/")
    m = re.match(r"^(?:https?://)?(?:www\.|m\.)?youtube\.com/(@[\w.\-]+|channel/UC[\w\-]{22}|c/[\w.\-]+|user/[\w.\-]+)", text)
    if m:
        return f"https://www.youtube.com/{m.group(1)}"
    if re.fullmatch(r"UC[\w\-]{22}", text):
        return f"https://www.youtube.com/channel/{text}"
    handle = text if text.startswith("@") else "@" + re.sub(r"\s+", "", text)
    return f"https://www.youtube.com/{handle}"


def _video(entry: dict, origin: str, now: float, min_s: int = MIN_LONG_VIDEO_S) -> Optional[dict]:
    vid = entry.get("id")
    if not vid or entry.get("live_status") in ("is_live", "is_upcoming"):
        return None
    url = entry.get("url") or f"https://www.youtube.com/watch?v={vid}"
    duration = entry.get("duration")
    if "/shorts/" in url or (duration is not None and duration < min_s):
        return None
    views = entry.get("view_count")
    ts = entry.get("timestamp")
    age_h = max(0.0, (now - ts) / 3600) if ts else None
    return {
        "id": vid, "url": f"https://www.youtube.com/watch?v={vid}",
        "title": entry.get("title") or "(no title)",
        "channel": entry.get("channel") or entry.get("uploader") or "",
        "duration": duration, "views": views, "age_hours": round(age_h, 1) if age_h is not None else None,
        "views_per_hour": round(views / max(age_h, 1.0)) if (views is not None and age_h is not None) else None,
        "was_live": entry.get("live_status") == "was_live", "origin": origin,
        "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
    }


def _fetch_tab(url: str) -> list[dict]:
    with _ydl_flat(PER_TAB) as ydl:
        info = ydl.extract_info(url, download=False) or {}
    # on a channel's own page the entries often don't repeat the channel's name
    owner = info.get("channel") or info.get("uploader")
    entries = []
    for e in info.get("entries") or []:
        if isinstance(e, dict):
            if owner and not (e.get("channel") or e.get("uploader")):
                e = dict(e, channel=owner)
            entries.append(e)
    return entries


def scan_channel(name: str, days: int, include_streams: bool = True, min_s: int = MIN_LONG_VIDEO_S) -> dict:
    """{name, ok, error, videos} - one streamer's recent long videos/streams."""
    base = channel_url(name)
    now = time.time()
    videos, error = [], None
    tabs = [("videos", True)] + ([("streams", False)] if include_streams else [])
    loaded_any = False
    for tab, required in tabs:
        try:
            entries = _fetch_tab(f"{base}/{tab}")
            loaded_any = True
        except Exception as exc:  # no such channel, no streams tab, network...
            if required:
                error = clean_error(exc)
            continue
        tab_videos = [v for v in (_video(e, name, now, min_s) for e in entries) if v]
        # "vs. normal": compared with this channel's own usual numbers on this tab
        counts = [v["views"] for v in tab_videos if v["views"]]
        median = statistics.median(counts) if len(counts) >= 3 else None
        for v in tab_videos:
            v["vs_normal"] = round(v["views"] / median, 1) if (median and v["views"] is not None) else None
        videos += tab_videos
    if loaded_any:
        error = None
    videos = [v for v in videos if v["age_hours"] is None or v["age_hours"] <= days * 24]
    return {"name": name, "ok": loaded_any, "error": None if loaded_any else (error or "Couldn't load this channel."), "videos": videos}


def scan_streamers(names: list[str], days: int, include_streams: bool = True,
                   progress: Optional[Callable[[str], None]] = None, kind: str = "streamers") -> dict:
    min_s = MIN_PODCAST_S if kind == "podcasts" else MIN_LONG_VIDEO_S
    results, done = [], 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(scan_channel, n, days, include_streams, min_s): n for n in names}
        for fut in futures:
            results.append(fut.result())
            done += 1
            if progress:
                progress(f"Checked {done} of {len(names)} {kind}...")
    videos = [v for r in results for v in r["videos"]]
    failed = [{"name": r["name"], "error": r["error"]} for r in results if not r["ok"]]
    return {"videos": rank(videos), "failed": failed, "checked": len(names)}


def search(query: str, period: str = "week", episodes_only: bool = False) -> dict:
    """episodes_only: only videos over 20 minutes (full podcast episodes)."""
    periods = EPISODE_PERIODS if episodes_only else SEARCH_PERIODS
    sp = periods.get(period, periods["week"])
    url = "https://www.youtube.com/results?" + urllib.parse.urlencode({"search_query": query, "sp": sp})
    try:
        entries = _fetch_tab(url)
    except TrendError:
        raise
    except Exception as exc:  # network, YouTube changed something...
        raise TrendError(f"YouTube search failed: {clean_error(exc)}") from exc
    now = time.time()
    min_s = MIN_PODCAST_S if episodes_only else MIN_LONG_VIDEO_S
    videos = [v for v in (_video(e, f"search: {query}", now, min_s) for e in entries) if v]
    days = PERIOD_DAYS.get(period, 7)
    videos = [v for v in videos if v["age_hours"] is None or v["age_hours"] <= days * 24 + 24]
    for v in videos:
        v.setdefault("vs_normal", None)
    return {"videos": rank(videos), "failed": [], "checked": 1}


def rank(videos: list[dict]) -> list[dict]:
    """Hottest first: views/hour, with a boost for videos far above their channel's normal."""
    seen, unique = set(), []
    for v in videos:
        if v["id"] not in seen:
            seen.add(v["id"])
            unique.append(v)
    for v in unique:
        vph = v["views_per_hour"] or 0
        boost = min(3.0, max(1.0, v["vs_normal"] or 1.0)) ** 0.5
        v["heat"] = round(vph * boost)
    return sorted(unique, key=lambda v: (-(v["heat"] or 0), -(v["views"] or 0)))


# ---------- AI: "what's hot and what should I clip?" ----------

SUMMARY_PROMPT = """You are a YouTube/TikTok trend analyst helping someone choose which long videos to cut into viral Shorts.
Here are the fastest-growing long videos right now (views/hour = how fast it is blowing up; "x normal" = compared with that channel's usual views):

{listing}

Answer ONLY with JSON in exactly this shape:
{{"trends": ["2-4 short bullet points: what topics/kinds of moments are blowing up right now"],
  "picks": [{{"n": 1, "why": "one sentence: why this video should give great Shorts"}}]}}
"picks" must contain exactly 3 different video numbers from the list above, best first."""


def summarize(videos: list[dict], brain) -> dict:
    """{trends: [...], picks: [{n, id, title, why}], source} - always valid,
    falls back to a plain numbers-based answer if no AI can help.
    brain: an ai.Brain (Gemini/Groq/Ollama - whichever answers)."""
    top = videos[:15]
    if not top:
        return {"trends": [], "picks": [], "source": "none"}
    listing = "\n".join(
        f"{n}. \"{v['title']}\" - {v['channel']} - {_fmt_count(v['views'])} views, "
        f"{_fmt_count(v['views_per_hour'])}/hour" + (f", {v['vs_normal']}x normal" if v.get("vs_normal") else "")
        for n, v in enumerate(top, start=1)
    )
    error = None
    try:
        for _attempt in range(moments.MAX_ATTEMPTS):
            raw, who = brain.ask(SUMMARY_PROMPT.format(listing=listing))
            parsed = _parse_summary(raw, len(top))
            if parsed:
                trends, picks = parsed
                return {"trends": trends, "source": who,
                        "picks": [{"n": n, "id": top[n - 1]["id"], "title": top[n - 1]["title"], "why": why} for n, why in picks]}
        error = "the AI's answers didn't make sense 3 times in a row"
    except Exception as exc:  # every AI down
        error = "; ".join(getattr(brain, "problems", [])) or str(exc)
    picks = [{"n": n, "id": v["id"], "title": v["title"],
              "why": f"{_fmt_count(v['views_per_hour'])} views/hour" + (f", {v['vs_normal']}x the channel's normal" if v.get("vs_normal") else "")}
             for n, v in enumerate(top[:3], start=1)]
    return {"trends": [], "picks": picks, "source": "numbers", "error": error}


def _parse_summary(raw: str, count: int):
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    trends = [re.sub(r"\s+", " ", str(t)).strip()[:200] for t in data.get("trends") or [] if str(t).strip()][:4]
    picks, used = [], set()
    for p in data.get("picks") or []:
        if not isinstance(p, dict):
            continue
        try:
            n = int(p.get("n"))
        except (TypeError, ValueError):
            continue
        why = re.sub(r"\s+", " ", str(p.get("why") or "")).strip()[:300]
        if 1 <= n <= count and n not in used and why:
            used.add(n)
            picks.append((n, why))
    if not trends or not picks:
        return None
    return trends, picks[:3]


def _fmt_count(n) -> str:
    if n is None:
        return "?"
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= size:
            return f"{n / size:.1f}".rstrip("0").rstrip(".") + suffix
    return str(int(n))
