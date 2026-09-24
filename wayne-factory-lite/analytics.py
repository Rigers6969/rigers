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

YouTube ad revenue (Analytics API, OAuth required - a plain API key
cannot read this, only public statistics):
    1. In the same Google Cloud project, enable the "YouTube Analytics API".
    2. Create an OAuth 2.0 Client ID of type "Desktop app" (Credentials >
       Create Credentials > OAuth client ID), download it as
       client_secret.json in this folder.
    3. Run `python youtube_auth_setup.py` once - it opens your browser to
       log in and approve access, then saves token_analytics.json so every
       later read is automatic (no browser, no re-login).
    Revenue is only ever non-zero once the channel is accepted into the
    YouTube Partner Program (1,000 subscribers + 4,000 public watch hours,
    or the Shorts equivalent) - before that this correctly returns $0,
    which is the real number, not a placeholder.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import requests

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
GRAPH_API_VERSION = "v21.0"
REVENUE_SCOPES = ["https://www.googleapis.com/auth/yt-analytics-monetary.readonly"]


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


def fetch_youtube_revenue(
    client_secret_path: str = "client_secret.json", token_path: str = "token_analytics.json"
) -> dict:
    """Returns {total_revenue, currency} of lifetime estimated YouTube ad
    revenue for the logged-in channel, via the YouTube Analytics API's
    monetary scope. Requires a one-time login - see this module's
    docstring or run `python youtube_auth_setup.py`."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_file = Path(token_path)
    if not token_file.exists():
        raise StatsFetchError(
            f"YouTube revenue isn't connected yet - run `python youtube_auth_setup.py` once to log in "
            f"(needs {client_secret_path} from Google Cloud Console; see analytics.py's docstring)."
        )

    creds = Credentials.from_authorized_user_file(str(token_file), REVENUE_SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_file.write_text(creds.to_json())
        else:
            raise StatsFetchError(
                "Your saved YouTube login has expired or been revoked - run `python youtube_auth_setup.py` again."
            )

    yt_analytics = build("youtubeAnalytics", "v2", credentials=creds)
    try:
        response = (
            yt_analytics.reports()
            .query(
                ids="channel==MINE",
                startDate="2005-02-01",  # YouTube's own founding date - covers the channel's whole lifetime
                endDate=date.today().isoformat(),
                metrics="estimatedRevenue",
            )
            .execute()
        )
    except Exception as exc:
        # A channel that isn't in the Partner Program yet (or has zero
        # revenue) is a normal, expected state, not a real error - report
        # it as $0 with a note rather than failing the whole dashboard.
        return {"total_revenue": 0.0, "currency": "USD", "note": f"No revenue data available yet ({exc})"}

    rows = response.get("rows") or []
    total = rows[0][0] if rows and rows[0] else 0.0
    return {"total_revenue": float(total), "currency": response.get("currency", "USD")}
