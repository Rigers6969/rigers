"""Topic researcher for the documentary channels: what's new right now that
would make a good video, for each channel.

Free sources, no key needed:
  - Google News search feeds (each channel's own search words, last 7 days)
  - Wikipedia's "most read yesterday" and "on this day" lists
  - Reddit's top posts of the week from a few subreddits per channel
Optional, with the YOUTUBE_API_KEY from config.json:
  - how many YouTube videos about the topic came out in the last 30 days and
    how many views the best one got - fewer videos + big views = a gap to fill

Headlines that tell the same story (several outlets, same names) are merged
into one topic. A topic scores higher when it's fresh, when many sources carry
it and when it hits the channel's strong words ("fraud", "collapse", "war",
"discovered"...). A source that fails is listed and skipped - the rest still
works.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Callable, Optional

import feedparser
import requests

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
CHANNELS_FILE = APP_DIR / "research_channels.json"
RESULT_FILE = APP_DIR / "research_latest.json"
IDEAS_FILE = APP_DIR / "research_ideas.json"
USER_AGENT = "WayneFactoryResearcher/1.0 (personal YouTube topic research)"
YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
TIMEOUT = 15
MAX_AGE_DAYS = 7
PER_CHANNEL = 25

# a starting setup - every word and subreddit can be changed on the page
DEFAULT_CHANNELS = [
    {
        "name": "Paper Trail",
        "lang": "en",
        "searches": ["fraud charged CEO", "company collapse bankruptcy", "Ponzi scheme", "SEC charges",
                     "accounting scandal", "startup fraud", "embezzlement sentenced"],
        "subreddits": ["business", "finance", "wallstreetbets"],
        "strong": ["fraud", "collapse", "bankrupt", "ponzi", "scam", "charged", "sentenced", "billion",
                   "scandal", "arrested", "lawsuit", "fake", "secret", "hidden"],
        "wiki": False,
    },
    {
        "name": "History",
        "lang": "en",
        "searches": ["archaeologists discover", "ancient ruins found", "historians reveal", "shipwreck found",
                     "lost city", "declassified documents"],
        "subreddits": ["history", "AskHistorians", "todayilearned"],
        "strong": ["ancient", "discovered", "lost", "war", "empire", "secret", "mystery", "king", "battle",
                   "tomb", "found", "declassified"],
        "wiki": True,
    },
    {
        "name": "The Forgotten Lab",
        "lang": "en",
        "searches": ["scientists discover", "new study finds", "breakthrough experiment", "NASA discovery",
                     "physicists", "strange new species"],
        "subreddits": ["science", "space", "Futurology"],
        "strong": ["discover", "first", "breakthrough", "strange", "mystery", "never", "new species",
                   "black hole", "experiment", "brain", "quantum"],
        "wiki": False,
    },
    {
        "name": "Albanian channel",
        "lang": "sq",
        "searches": ["Shqipëri histori", "Tirana", "zbulim arkeologjik Shqipëri", "skandal korrupsioni"],
        "subreddits": ["albania"],
        "strong": ["skandal", "histori", "zbulim", "mister", "luft", "sekret"],
        "wiki": False,
    },
]

GN_LOCALE = {"en": ("en-US", "US", "US:en"), "sq": ("sq", "AL", "AL:sq")}
STOPWORDS = set("""a an the and or of to in on for with at by from as is are was were be been it its this that
these those after before over into about than how why what who new says said will can could would has have had
not no but more most just up out off his her their they he she we you your our de të e i në që për me nga""".split())


class ResearchError(Exception):
    pass


# ---------- settings ----------

def load_channels() -> list[dict]:
    if CHANNELS_FILE.exists():
        try:
            data = json.loads(CHANNELS_FILE.read_text(encoding="utf-8-sig"))
            if isinstance(data, list) and data:
                return [_clean_channel(c) for c in data if isinstance(c, dict) and c.get("name")]
        except (OSError, json.JSONDecodeError):
            pass
    return [dict(c) for c in DEFAULT_CHANNELS]


def _clean_channel(c: dict) -> dict:
    def words(key):
        v = c.get(key) or []
        if isinstance(v, str):
            v = v.split(",")
        return [str(w).strip() for w in v if str(w).strip()][:20]
    return {"name": str(c["name"]).strip()[:60], "lang": "sq" if c.get("lang") == "sq" else "en",
            "searches": words("searches"), "subreddits": [s.lstrip("r/") for s in words("subreddits")],
            "strong": [w.lower() for w in words("strong")], "wiki": bool(c.get("wiki"))}


def save_channels(channels: list[dict]) -> list[dict]:
    clean = [_clean_channel(c) for c in channels if isinstance(c, dict) and str(c.get("name", "")).strip()]
    if not clean:
        raise ResearchError("Add at least one channel.")
    CHANNELS_FILE.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    return clean


def _youtube_key() -> str:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
            value = str(data.get("YOUTUBE_API_KEY") or "").strip()
            if value:
                return value
        except (OSError, json.JSONDecodeError):
            pass
    return os.environ.get("YOUTUBE_API_KEY", "").strip()


# ---------- sources ----------

def _get(url: str, **kw) -> requests.Response:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, **kw)
    resp.raise_for_status()
    return resp


def _clean(text: str, limit: int = 240) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "..."


def _when(entry) -> Optional[datetime]:
    for key in ("published", "updated"):
        if entry.get(key):
            try:
                return parsedate_to_datetime(entry[key]).astimezone(timezone.utc)
            except (TypeError, ValueError):
                pass
    return None


def google_news(query: str, lang: str = "en") -> list[dict]:
    hl, gl, ceid = GN_LOCALE.get(lang, GN_LOCALE["en"])
    url = ("https://news.google.com/rss/search?" +
           urllib.parse.urlencode({"q": f"{query} when:{MAX_AGE_DAYS}d", "hl": hl, "gl": gl, "ceid": ceid}))
    feed = feedparser.parse(_get(url).content)
    items = []
    for e in feed.entries[:15]:
        title = _clean(e.get("title", ""), 200)
        source = ""
        if " - " in title:  # Google News puts " - Outlet" at the end
            title, source = title.rsplit(" - ", 1)
        when = _when(e)
        items.append({"title": title, "source": source or "Google News", "link": e.get("link", ""),
                      "snippet": "", "time": when.isoformat() if when else None, "kind": "news", "query": query})
    return items


def reddit_top(sub: str) -> list[dict]:
    data = _get(f"https://www.reddit.com/r/{urllib.parse.quote(sub)}/top.json",
                params={"t": "week", "limit": 15}).json()
    items = []
    for child in data.get("data", {}).get("children", []):
        p = child.get("data", {})
        if p.get("stickied") or p.get("over_18"):
            continue
        items.append({"title": _clean(p.get("title", ""), 200), "source": f"r/{sub}",
                      "link": "https://www.reddit.com" + p.get("permalink", ""),
                      "snippet": _clean(p.get("selftext", ""), 200),
                      "time": datetime.fromtimestamp(p.get("created_utc", time.time()), timezone.utc).isoformat(),
                      "kind": "reddit", "upvotes": int(p.get("ups", 0))})
    return items


def wikipedia_most_read() -> list[dict]:
    day = datetime.now(timezone.utc) - timedelta(days=1)
    data = _get(f"https://en.wikipedia.org/api/rest_v1/feed/featured/{day:%Y/%m/%d}").json()
    items = []
    for a in (data.get("mostread") or {}).get("articles", [])[:30]:
        title = a.get("normalizedtitle") or a.get("title", "")
        if title in ("Main Page",) or title.startswith(("Special:", "Wikipedia:")):
            continue
        items.append({"title": title, "source": "Wikipedia most read", "kind": "wiki",
                      "link": (a.get("content_urls") or {}).get("desktop", {}).get("page", ""),
                      "snippet": _clean(a.get("extract", ""), 200), "time": day.isoformat(),
                      "views": int(a.get("views", 0))})
    return items


def wikipedia_on_this_day(days_ahead: int = 14) -> list[dict]:
    """Anniversaries in the next two weeks - time a history video to land on the date."""
    items = []
    for offset in range(0, days_ahead, 7):
        day = datetime.now(timezone.utc) + timedelta(days=offset)
        data = _get(f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/selected/{day:%m/%d}").json()
        for ev in data.get("selected", [])[:10]:
            pages = ev.get("pages") or [{}]
            items.append({"title": _clean(ev.get("text", ""), 200), "source": f"On this day: {day:%d %b} {ev.get('year', '')}",
                          "kind": "anniversary",
                          "link": (pages[0].get("content_urls") or {}).get("desktop", {}).get("page", ""),
                          "snippet": _clean(pages[0].get("extract", ""), 200), "time": None,
                          "date": day.strftime("%d %b"), "year": ev.get("year")})
    return items


def youtube_gap(topic: str, key: str) -> Optional[dict]:
    """How crowded the topic is on YouTube in the last 30 days."""
    after = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    found = _get(f"{YOUTUBE_API}/search", params={"key": key, "q": topic, "part": "snippet", "type": "video",
                                                  "publishedAfter": after, "maxResults": 10,
                                                  "order": "viewCount"}).json()
    ids = [i["id"]["videoId"] for i in found.get("items", []) if i.get("id", {}).get("videoId")]
    total = (found.get("pageInfo") or {}).get("totalResults", 0)
    best = None
    if ids:
        stats = _get(f"{YOUTUBE_API}/videos", params={"key": key, "id": ",".join(ids),
                                                      "part": "statistics,snippet"}).json()
        vids = sorted(stats.get("items", []), key=lambda v: -int(v["statistics"].get("viewCount", 0)))
        if vids:
            v = vids[0]
            best = {"title": v["snippet"]["title"], "channel": v["snippet"]["channelTitle"],
                    "views": int(v["statistics"].get("viewCount", 0)),
                    "url": f"https://www.youtube.com/watch?v={v['id']}"}
    return {"videos_30d": int(total), "best": best}


# ---------- merging and scoring ----------

def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[\wëçË]+", text.lower()) if len(w) > 2 and w not in STOPWORDS}


def _names(text: str) -> set[str]:
    """Capitalised words (people, companies, places) - the best sign two headlines tell one story."""
    return {w.lower() for w in re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", text)} - STOPWORDS


def cluster(items: list[dict]) -> list[list[dict]]:
    groups: list[dict] = []
    for it in items:
        w, n = _words(it["title"]), _names(it["title"])
        for g in groups:
            shared = len(w & g["words"])
            if (len(n & g["names"]) >= 2) or (n & g["names"] and shared >= 3) or shared >= 5:
                g["items"].append(it)
                g["words"] |= w
                g["names"] |= n
                break
        else:
            groups.append({"items": [it], "words": set(w), "names": set(n)})
    return [g["items"] for g in groups]


def score(group: list[dict], strong: list[str], now: Optional[datetime] = None) -> float:
    now = now or datetime.now(timezone.utc)
    text = " ".join(i["title"] + " " + i.get("snippet", "") for i in group).lower()
    sources = {i["source"] for i in group}
    s = 10 * min(len(sources), 6)                                   # many outlets carry it
    s += 6 * sum(1 for w in strong if w and w in text)              # the channel's strong words
    times = [datetime.fromisoformat(i["time"]) for i in group if i.get("time")]
    if times:
        hours = max(1.0, (now - max(times)).total_seconds() / 3600)
        s += max(0.0, 30 - hours / 6)                               # fresh beats old
    s += min(20, sum(i.get("upvotes", 0) for i in group) / 1000)    # reddit love
    s += min(20, sum(i.get("views", 0) for i in group) / 50000)     # wikipedia readers
    if any(i["kind"] == "anniversary" for i in group):
        s += 15
    return round(s, 1)


def topic_from(group: list[dict], strong: list[str], now: Optional[datetime] = None) -> dict:
    lead = max(group, key=lambda i: (i["kind"] == "news", len(i["title"])))
    return {"title": lead["title"], "score": score(group, strong, now), "kind": lead["kind"],
            "sources": sorted({i["source"] for i in group})[:8], "count": len(group),
            "items": [{k: i.get(k) for k in ("title", "source", "link", "snippet", "time", "date")} for i in group[:6]],
            "angle": angle(lead["title"], strong)}


def angle(title: str, strong: list[str]) -> str:
    """A quick idea for how to turn the headline into a video."""
    t = title.lower()
    if any(w in t for w in ("fraud", "ponzi", "scam", "charged", "sentenced", "embezzl", "scandal")):
        return "The full story: how it started, how the money moved, who noticed, how it fell apart."
    if any(w in t for w in ("bankrupt", "collapse", "layoff", "shut")):
        return "Rise and fall: the peak, the mistakes, the last 30 days."
    if any(w in t for w in ("discover", "found", "reveal", "unearth", "zbulim")):
        return "What they found, why it matters, the mystery that is still open."
    if any(w in t for w in ("war", "battle", "empire", "king", "luft")):
        return "Map-driven story: who, where, the turning point, what it changed."
    return "Explain it simply: what happened, why people care, what happens next."


# ---------- the run ----------

_state = {"status": "idle", "message": "", "error": None}
_lock = threading.Lock()


def state() -> dict:
    out = dict(_state)
    if RESULT_FILE.exists():
        try:
            out["result"] = json.loads(RESULT_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            out["result"] = None
    return out


def research_channel(ch: dict, progress: Callable[[str], None] = lambda m: None,
                     yt_key: str = "", wiki_cache: Optional[dict] = None) -> dict:
    jobs = [("Google News: " + q, lambda q=q: google_news(q, ch["lang"])) for q in ch["searches"]]
    jobs += [("Reddit r/" + s, lambda s=s: reddit_top(s)) for s in ch["subreddits"]]
    if ch.get("wiki"):
        jobs += [("Wikipedia most read", lambda: (wiki_cache or {}).get("mostread") or wikipedia_most_read()),
                 ("Wikipedia on this day", lambda: (wiki_cache or {}).get("onthisday") or wikipedia_on_this_day())]
    items, failed = [], []
    progress(f"{ch['name']}: reading {len(jobs)} sources...")
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [(label, pool.submit(fn)) for label, fn in jobs]
        for label, fut in futures:
            try:
                items += fut.result()
            except Exception as exc:  # one dead feed never stops the rest
                failed.append(f"{label} ({type(exc).__name__})")
    seen, unique = set(), []
    for it in items:
        k = it["title"].lower()[:90]
        if it["title"] and k not in seen:
            seen.add(k)
            unique.append(it)
    if ch.get("wiki"):  # most-read pages only count when they match the channel
        unique = [i for i in unique if i["kind"] != "wiki" or any(w in (i["title"] + i["snippet"]).lower()
                                                                    for w in ch["strong"])]
    topics = sorted((topic_from(g, ch["strong"]) for g in cluster(unique)), key=lambda t: -t["score"])[:PER_CHANNEL]
    if yt_key:
        progress(f"{ch['name']}: checking YouTube for the top topics...")
        for t in topics[:8]:
            try:
                t["youtube"] = youtube_gap(t["title"], yt_key)
            except Exception as exc:
                t["youtube"] = {"error": type(exc).__name__}
    return {"name": ch["name"], "topics": topics, "failed": failed, "items": len(unique)}


def run(progress: Callable[[str], None] = lambda m: None) -> dict:
    channels = load_channels()
    key = _youtube_key()
    wiki_cache = {}
    if any(c.get("wiki") for c in channels):
        for name, fn in (("mostread", wikipedia_most_read), ("onthisday", wikipedia_on_this_day)):
            try:
                wiki_cache[name] = fn()
            except Exception:
                pass
    result = {"updated": datetime.now(timezone.utc).isoformat(), "youtube_checked": bool(key),
              "channels": [research_channel(c, progress, key, wiki_cache) for c in channels]}
    RESULT_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def start() -> bool:
    """Runs in the background; False if a run is already going."""
    with _lock:
        if _state["status"] == "running":
            return False
        _state.update(status="running", message="Starting...", error=None)

    def job():
        try:
            run(lambda m: _state.update(message=m))
            _state.update(status="done", message="Done.")
        except Exception as exc:
            _state.update(status="error", error=f"{type(exc).__name__}: {exc}")
    threading.Thread(target=job, daemon=True).start()
    return True


# ---------- saved ideas ----------

def load_ideas() -> list[dict]:
    if IDEAS_FILE.exists():
        try:
            data = json.loads(IDEAS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            pass
    return []


def save_idea(channel: str, title: str, angle_text: str = "", link: str = "") -> list[dict]:
    if not title.strip():
        raise ResearchError("The idea needs a title.")
    ideas = load_ideas()
    ideas.insert(0, {"channel": channel[:60], "title": title.strip()[:200], "angle": angle_text[:300],
                     "link": link[:500], "saved": datetime.now(timezone.utc).isoformat(), "done": False})
    IDEAS_FILE.write_text(json.dumps(ideas[:500], indent=2, ensure_ascii=False), encoding="utf-8")
    return ideas


def update_idea(index: int, done: Optional[bool] = None, delete: bool = False) -> list[dict]:
    ideas = load_ideas()
    if not 0 <= index < len(ideas):
        raise ResearchError("That idea is gone.")
    if delete:
        ideas.pop(index)
    elif done is not None:
        ideas[index]["done"] = bool(done)
    IDEAS_FILE.write_text(json.dumps(ideas, indent=2, ensure_ascii=False), encoding="utf-8")
    return ideas
