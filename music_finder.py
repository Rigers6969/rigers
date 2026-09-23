"""Searches Jamendo (api.jamendo.com) for real, licensed background music -
half a million tracks, each with real Creative Commons license metadata,
via a free API key. Requires a free client_id from
https://devportal.jamendo.com/ - silently returns no results without one,
same "just works once you add a key, no-op until then" pattern as the
image sources in shotsource/.

Jamendo's catalog mixes commercial-safe licenses (CC-BY, CC-BY-SA, CC0)
with non-commercial-only ones (CC-BY-NC, CC-BY-NC-ND, CC-BY-NC-SA) - since
these videos get monetized, every result is checked against its own
license_ccurl and anything NC, or with no clear license, is dropped
rather than risked.
"""
from __future__ import annotations

import os
import re
from typing import Optional

import requests

API_URL = "https://api.jamendo.com/v3.0/tracks/"


def _is_commercial_safe(license_ccurl: str) -> bool:
    if not license_ccurl or not license_ccurl.strip():
        return False
    path = license_ccurl.lower()
    if "creativecommons.org/licenses/" not in path and "creativecommons.org/publicdomain" not in path:
        return False
    return "nc" not in re.split(r"/licenses/|/publicdomain/", path)[-1].split("/")[0]


def search_tracks(query: str, limit: int = 12, client_id: Optional[str] = None) -> dict:
    client_id = client_id or os.environ.get("JAMENDO_CLIENT_ID", "").strip()
    if not client_id:
        return {
            "tracks": [],
            "error": "JAMENDO_CLIENT_ID not set - get a free key at https://devportal.jamendo.com/ and add it to .env.",
        }

    try:
        resp = requests.get(
            API_URL,
            params={
                "client_id": client_id,
                "format": "json",
                "limit": min(max(limit, 1), 50),
                "search": query,
                "audioformat": "mp32",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        return {"tracks": [], "error": f"Could not reach Jamendo: {exc}"}

    if resp.status_code != 200:
        # Surface the real cause (bad client_id, malformed request, Jamendo
        # outage) instead of a generic message - the response body usually
        # says exactly what's wrong.
        return {
            "tracks": [],
            "error": f"Jamendo returned HTTP {resp.status_code}: {resp.text[:300]}",
        }

    try:
        data = resp.json()
    except ValueError:
        return {"tracks": [], "error": f"Jamendo returned a non-JSON response: {resp.text[:300]}"}

    header_status = (data.get("headers") or {}).get("status")
    if header_status and header_status != "success":
        error_message = (data.get("headers") or {}).get("error_message") or "unknown error"
        return {"tracks": [], "error": f"Jamendo API error: {error_message}"}

    raw_results = data.get("results", [])
    tracks = []
    rejected_license = 0
    for item in raw_results:
        license_url = item.get("license_ccurl", "")
        if not _is_commercial_safe(license_url):
            rejected_license += 1
            continue
        download_url = item.get("audiodownload") or item.get("audio")
        if not download_url:
            continue
        tracks.append({
            "id": str(item.get("id", "")),
            "title": item.get("name", "Untitled"),
            "artist": item.get("artist_name", "Unknown artist"),
            "duration": item.get("duration"),
            "license_url": license_url,
            "preview_url": item.get("audio", download_url),
            "download_url": download_url,
        })

    result = {"tracks": tracks, "error": None}
    if not tracks and raw_results:
        # Jamendo found something, but every result was filtered out - say
        # so explicitly rather than looking identical to "nothing found at
        # all", which is a different problem with a different fix (try a
        # different search term).
        result["error"] = (
            f"Jamendo found {len(raw_results)} track(s) for this search, but all "
            f"{rejected_license} were non-commercial-licensed (or had no clear "
            "license) and were excluded. Try a different search term."
        )
    return result
