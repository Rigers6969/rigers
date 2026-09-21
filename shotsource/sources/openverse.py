"""Openverse (api.openverse.org) - aggregates openly-licensed and public
domain images from many providers. No API key required for the volumes
this tool needs; results already carry direct image URLs, dimensions, and
full license metadata, so no extra lookup call is needed per result."""
from __future__ import annotations

from typing import List

from ..models import RawCandidate
from .base import BaseSource

API_URL = "https://api.openverse.org/v1/images/"


class OpenverseSource(BaseSource):
    name = "openverse"

    def search(self, query: str) -> List[RawCandidate]:
        page_size = min(self.max_results, 20)
        data = self.http.get_json(API_URL, params={"q": query, "page_size": page_size, "mature": "false"})
        candidates = []
        for item in (data.get("results") or [])[: self.max_results]:
            direct_url = item.get("url", "")
            if not direct_url:
                continue
            candidates.append(RawCandidate(
                source=self.name,
                media_id=str(item.get("id", "")),
                title=item.get("title") or "",
                direct_url=direct_url,
                landing_url=item.get("foreign_landing_url") or direct_url,
                license=_format_license(item),
                license_url=item.get("license_url", ""),
                attribution=item.get("attribution") or _fallback_attribution(item),
                width=item.get("width"),
                height=item.get("height"),
            ))
        return candidates


def _format_license(item: dict) -> str:
    lic = (item.get("license") or "").upper()
    version = item.get("license_version") or ""
    return f"{lic} {version}".strip()


def _fallback_attribution(item: dict) -> str:
    creator = item.get("creator") or "Unknown creator"
    title = item.get("title") or "Untitled"
    source = item.get("provider") or item.get("source") or "Openverse"
    return f'"{title}" by {creator}, via {source}, licensed {_format_license(item)}'
