"""Pexels (api.pexels.com) - requires a free API key. Silently returns no
results if the key isn't set, rather than erroring the whole pipeline, so
this source can just be left enabled with no key and it's a no-op."""
from __future__ import annotations

import os
from typing import List

from ..models import RawCandidate
from .base import BaseSource

API_URL = "https://api.pexels.com/v1/search"


class PexelsSource(BaseSource):
    name = "pexels"

    def __init__(self, http, max_results: int, api_key_env: str = "PEXELS_API_KEY"):
        super().__init__(http, max_results)
        self.api_key = os.environ.get(api_key_env, "")

    def search(self, query: str) -> List[RawCandidate]:
        if not self.api_key:
            return []
        per_page = min(self.max_results, 80)
        data = self.http.get_json(
            API_URL,
            params={"query": query, "per_page": per_page},
            headers={"Authorization": self.api_key},
        )
        candidates = []
        for photo in (data.get("photos") or [])[: self.max_results]:
            direct_url = (photo.get("src") or {}).get("original", "")
            if not direct_url:
                continue
            photographer = photo.get("photographer") or "Unknown photographer"
            landing_url = photo.get("url", "")
            candidates.append(RawCandidate(
                source=self.name,
                media_id=str(photo.get("id", "")),
                title=photo.get("alt") or "",
                direct_url=direct_url,
                landing_url=landing_url,
                license="Pexels License",
                license_url="https://www.pexels.com/license/",
                attribution=f"Photo by {photographer} on Pexels ({landing_url})",
                width=photo.get("width"),
                height=photo.get("height"),
            ))
        return candidates
