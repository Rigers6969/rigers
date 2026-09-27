"""Free, no-API-key signal for topic invention: what are other channels
in this niche posting right now, and is anyone searching for a given
topic at all. Feeds into producer.py's generate_topic_idea() as extra
context, the same way video_reviewer.py's "lessons" do - just sourced
from outside the app instead of from your own past videos.

Deliberately free instead of the YouTube Data API's search.list (which
would cost 100 quota units per call against a shared 10,000/day budget -
too expensive to run per topic):

- Competitor channels' recent uploads: YouTube's own per-channel RSS
  feed (feeds/videos.xml?channel_id=...) - official, free, no API key.
  Limit: channel-level only, ~15 most recent titles, no search across
  YouTube by keyword and no view counts.
- Google Trends search interest: via the unofficial pytrends library.
  Free, but unofficial and unmaintained (the project was archived in
  2025) - it can break or get rate-limited without warning, so every
  call here is wrapped and treated as optional; a failure here should
  never stop a video from being produced.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import feedparser

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"

_HEADERS_AGENT = "WayneFactoryLite-TrendScout/1.0 (personal project; contact via YouTube channel)"

MAX_TITLES_PER_CHANNEL = 8
MAX_TITLES_TOTAL = 15


def _read_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_competitor_ids(channel_name: str) -> list[str]:
    """The competitor YouTube channel IDs configured for `channel_name`,
    or [] if none are set up yet."""
    config = _read_config()
    for entry in config.get("CHANNELS", []) or []:
        if isinstance(entry, dict) and entry.get("name") == channel_name:
            ids = entry.get("COMPETITOR_CHANNEL_IDS", [])
            return [str(i).strip() for i in ids if str(i).strip()] if isinstance(ids, list) else []
    return []


def load_all_competitors() -> list[dict]:
    """Every channel's name + competitor IDs, for the Trend Scout panel
    to display and edit - includes channels that only have competitors
    set up (no YOUTUBE_CHANNEL_ID yet), unlike the Dashboard's stats
    list which requires one."""
    config = _read_config()
    out = []
    for entry in config.get("CHANNELS", []) or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        ids = entry.get("COMPETITOR_CHANNEL_IDS", [])
        out.append({
            "name": name,
            "competitor_channel_ids": [str(i).strip() for i in ids if str(i).strip()] if isinstance(ids, list) else [],
        })
    return out


def save_competitor_ids(channel_name: str, competitor_ids: list[str]) -> None:
    """Writes `competitor_ids` for `channel_name` into config.json,
    creating a CHANNELS entry for it if one doesn't exist yet (a
    channel can use Trend Scout without having Dashboard stats set up)."""
    config = _read_config()
    channels = config.get("CHANNELS")
    if not isinstance(channels, list):
        channels = []
    cleaned = [str(i).strip() for i in competitor_ids if str(i).strip()]

    for entry in channels:
        if isinstance(entry, dict) and entry.get("name") == channel_name:
            entry["COMPETITOR_CHANNEL_IDS"] = cleaned
            break
    else:
        channels.append({"name": channel_name, "YOUTUBE_CHANNEL_ID": "", "COMPETITOR_CHANNEL_IDS": cleaned})

    config["CHANNELS"] = channels
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def fetch_channel_recent_titles(channel_id: str, limit: int = MAX_TITLES_PER_CHANNEL) -> list[str]:
    """This channel's most recent upload titles, via YouTube's own free
    per-channel RSS feed. Returns [] on any failure (bad ID, network
    down, empty feed) rather than raising - this is optional context,
    never a reason to fail a video."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        feed = feedparser.parse(url, agent=_HEADERS_AGENT)
    except Exception:
        return []
    titles = [str(getattr(e, "title", "")).strip() for e in getattr(feed, "entries", [])]
    return [t for t in titles if t][:limit]


def fetch_trend_note(topic: str) -> Optional[str]:
    """A short, best-effort read on whether `topic` has any current
    Google Trends search interest. Returns None on any failure - the
    underlying pytrends library is unofficial, unmaintained, and gets
    rate-limited unpredictably, so this is a bonus signal, never a
    dependency."""
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(timeout=(5, 10))
        pytrends.build_payload([topic[:80]], timeframe="now 7-d")
        data = pytrends.interest_over_time()
        if data is None or data.empty:
            return None
        recent_avg = data[topic[:80]].mean()
        if recent_avg >= 40:
            return f'Google Trends: "{topic[:80]}" has notable current search interest.'
        return None
    except Exception:
        return None


def build_scout_guidance(channel_name: str) -> str:
    """Recent titles from this channel's configured competitors,
    formatted for the topic-idea prompt. Returns "" if no competitors
    are configured or none of their feeds were reachable - the prompt
    template treats that as "no scouting data available"."""
    competitor_ids = load_competitor_ids(channel_name)
    if not competitor_ids:
        return ""

    all_titles: list[str] = []
    for channel_id in competitor_ids:
        all_titles.extend(fetch_channel_recent_titles(channel_id))
        if len(all_titles) >= MAX_TITLES_TOTAL:
            break

    if not all_titles:
        return ""

    lines = "\n".join(f"- {t}" for t in all_titles[:MAX_TITLES_TOTAL])
    return (
        "Other channels in this niche have recently posted videos with these titles "
        "(for a sense of what's current - don't copy them, but topics in a similar vein "
        "are worth considering):\n" + lines
    )
