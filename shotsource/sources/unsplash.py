"""Unsplash (api.unsplash.com) - requires a free API "Access Key" from an
Unsplash developer app. Silently returns no results if the key isn't set,
same as the Pexels/Pixabay sources."""
from __future__ import annotations

import os
from typing import List

from ..models import RawCandidate
from .base import BaseSource

API_URL = "https://api.unsplash.com/search/photos"


class UnsplashSource(BaseSource):
    name = "unsplash"

    def __init__(self, http, max_results: int, api_key_env: str = "UNSPLASH_ACCESS_KEY"):
        super().__init__(http, max_results)
        self.api_key = os.environ.get(api_key_env, "")

    def search(self, query: str) -> List[RawCandidate]:
        if not self.api_key:
            return []
        per_page = min(self.max_results, 30)
        data = self.http.get_json(
            API_URL,
            params={"query": query, "per_page": per_page},
            headers={"Authorization": f"Client-ID {self.api_key}"},
        )
        candidates = []
        for photo in (data.get("results") or [])[: self.max_results]:
            direct_url = (photo.get("urls") or {}).get("full", "")
            if not direct_url:
                continue
            user = (photo.get("user") or {}).get("name") or "Unknown photographer"
            user_url = ((photo.get("user") or {}).get("links") or {}).get("html", "")
            landing_url = (photo.get("links") or {}).get("html", "")
            candidates.append(RawCandidate(
                source=self.name,
                media_id=str(photo.get("id", "")),
                title=photo.get("alt_description") or "",
                direct_url=direct_url,
                landing_url=landing_url,
                license="Unsplash License",
                license_url="https://unsplash.com/license",
                attribution=f"Photo by {user} ({user_url}) on Unsplash",
                width=photo.get("width"),
                height=photo.get("height"),
            ))
        return candidates
