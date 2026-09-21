"""Library of Congress search API (loc.gov/search). LOC's rights metadata
per item is inconsistent - some carry an explicit "no known restrictions"
statement, many don't say anything usable. Rather than guess, this source
leaves `license` empty when it can't find a clear public-domain/no-known-
restrictions statement, and the pipeline hard-rejects anything with an
unclear license (logged with its reason) instead of silently including it.
"""
from __future__ import annotations

from typing import List

from ..models import RawCandidate
from .base import BaseSource

API_URL = "https://www.loc.gov/search/"


def _best_image_url(urls: list) -> str:
    # LOC returns a list of image URLs at increasing sizes; the last one
    # is the largest available.
    return urls[-1] if urls else ""


def _license_from_item(item: dict) -> str:
    rights = item.get("rights") or item.get("rights_advisory") or ""
    if isinstance(rights, list):
        rights = "; ".join(str(r) for r in rights if r)
    rights_lower = str(rights).lower()
    if "no known restriction" in rights_lower:
        return "Public Domain / No Known Restrictions"
    if "public domain" in rights_lower:
        return "Public Domain"
    return ""


class LocSource(BaseSource):
    name = "loc"

    def search(self, query: str) -> List[RawCandidate]:
        limit = min(self.max_results, 100)
        data = self.http.get_json(API_URL, params={
            "q": query,
            "fo": "json",
            "c": limit,
            "fa": "online-format:image",
        })
        candidates = []
        for item in (data.get("results") or [])[: self.max_results]:
            direct_url = _best_image_url(item.get("image_url") or [])
            if not direct_url:
                continue
            title = item.get("title") or "Untitled"
            landing_url = item.get("id") or item.get("url") or ""
            candidates.append(RawCandidate(
                source=self.name,
                media_id=str(item.get("id", direct_url)),
                title=title,
                direct_url=direct_url,
                landing_url=landing_url,
                license=_license_from_item(item),
                license_url="https://www.loc.gov/legal/",
                attribution=f'"{title}", Library of Congress ({landing_url})',
                width=None,
                height=None,
            ))
        return candidates
