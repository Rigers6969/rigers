"""Pixabay (pixabay.com/api) - requires a free API key. Silently returns
no results if the key isn't set, same as the Pexels source."""
from __future__ import annotations

import os
from typing import List

from ..models import RawCandidate
from .base import BaseSource

API_URL = "https://pixabay.com/api/"


class PixabaySource(BaseSource):
    name = "pixabay"

    def __init__(self, http, max_results: int, api_key_env: str = "PIXABAY_API_KEY"):
        super().__init__(http, max_results)
        self.api_key = os.environ.get(api_key_env, "")

    def search(self, query: str) -> List[RawCandidate]:
        if not self.api_key:
            return []
        per_page = max(3, min(self.max_results, 200))  # Pixabay requires 3-200
        data = self.http.get_json(API_URL, params={
            "key": self.api_key,
            "q": query,
            "image_type": "photo",
            "per_page": per_page,
        })
        candidates = []
        for hit in (data.get("hits") or [])[: self.max_results]:
            direct_url = hit.get("largeImageURL", "")
            if not direct_url:
                continue
            user = hit.get("user") or "Unknown photographer"
            landing_url = hit.get("pageURL", "")
            candidates.append(RawCandidate(
                source=self.name,
                media_id=str(hit.get("id", "")),
                title=hit.get("tags") or "",
                direct_url=direct_url,
                landing_url=landing_url,
                license="Pixabay License",
                license_url="https://pixabay.com/service/license/",
                attribution=f"Image by {user} on Pixabay ({landing_url})",
                width=hit.get("imageWidth"),
                height=hit.get("imageHeight"),
            ))
        return candidates
