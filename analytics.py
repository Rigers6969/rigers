"""Fetches real channel/account statistics for the dashboard's stat cards.

YouTube (Data API v3, read-only, no OAuth needed):
    1. Go to Google Cloud Console, create/select a project.
    2. Enable the "YouTube Data API v3".
    3. Create an API key (Credentials > Create Credentials > API key).
    4. Find your channel ID: it's in your channel's URL, or use
       https://www.youtube.com/account_advanced while logged in.
    This is much simpler than the OAuth flow publishing.py needs for
    uploading - reading public statistics only needs a plain API key.

Instagram (Graph API - requires a Business/Creator account linked to a
Facebook Page, same setup as publishing.py's post_to_instagram):
    Reuse the same access token and Instagram Business Account ID you
    already set up there.
"""
from __future__ import annotations

import requests

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
GRAPH_API_VERSION = "v21.0"


class StatsFetchError(RuntimeError):
    pass


def _parse_json_or_raise_status(resp: requests.Response) -> dict:
    """Both YouTube and the Graph API return a descriptive JSON error body
    (e.g. "API key not valid", "API_KEY_HTTP_REFERRER_BLOCKED") even on a
    4xx status - calling resp.raise_for_status() before reading that body
    throws requests' own generic "400 Client Error: Bad Request for url:
    ..." instead, discarding the one piece of information that actually
    explains what's wrong. Try the JSON body first; only fall back to the
    generic HTTP error if the response isn't JSON at all."""
    try:
        return resp.json()
    except ValueError:
        resp.raise_for_status()
        raise StatsFetchError(f"Unexpected non-JSON response (status {resp.status_code}): {resp.text[:300]}")


def fetch_youtube_stats(channel_id: str, api_key: str) -> dict:
    """Returns {subscriber_count, view_count, video_count, subscriber_count_hidden,
    channel_title}. subscriber_count is None if the channel owner has hidden it -
    that's a real, valid state, not an error."""
    resp = requests.get(
        f"{YOUTUBE_API_BASE}/channels",
        params={"part": "statistics,snippet", "id": channel_id, "key": api_key},
        timeout=15,
    )
    data = _parse_json_or_raise_status(resp)

    if "error" in data:
        raise StatsFetchError(f"YouTube API error: {data['error'].get('message', data['error'])}")
    items = data.get("items", [])
    if not items:
        raise StatsFetchError(f"No YouTube channel found for id {channel_id!r} - check the channel ID.")

    stats = items[0]["statistics"]
    hidden = stats.get("hiddenSubscriberCount", False)
    return {
        "channel_title": items[0].get("snippet", {}).get("title", ""),
        "subscriber_count": None if hidden else int(stats.get("subscriberCount", 0)),
        "subscriber_count_hidden": hidden,
        "view_count": int(stats.get("viewCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
    }


def fetch_instagram_stats(ig_user_id: str, access_token: str) -> dict:
    """Returns {username, followers_count, media_count}."""
    resp = requests.get(
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/{ig_user_id}",
        params={"fields": "username,followers_count,media_count", "access_token": access_token},
        timeout=15,
    )
    data = _parse_json_or_raise_status(resp)

    if "error" in data:
        raise StatsFetchError(f"Instagram API error: {data['error'].get('message', data['error'])}")

    return {
        "username": data.get("username", ""),
        "followers_count": int(data.get("followers_count", 0)),
        "media_count": int(data.get("media_count", 0)),
    }
