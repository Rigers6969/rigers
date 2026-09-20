"""Wikimedia Commons (commons.wikimedia.org) via its MediaWiki action API -
generator=search over the file namespace (6), with imageinfo/extmetadata
requested in the same call so no per-result lookup is needed."""
from __future__ import annotations

import re
from typing import List

from ..models import RawCandidate
from .base import BaseSource

API_URL = "https://commons.wikimedia.org/w/api.php"

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: str) -> str:
    return _TAG_RE.sub("", value or "").strip()


class WikimediaSource(BaseSource):
    name = "wikimedia"

    def search(self, query: str) -> List[RawCandidate]:
        limit = min(self.max_results, 50)
        data = self.http.get_json(API_URL, params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap",
            "gsrnamespace": 6,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
        })
        pages = ((data.get("query") or {}).get("pages") or {}).values()
        candidates = []
        for page in pages:
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            info = infos[0]
            direct_url = info.get("url", "")
            if not direct_url:
                continue
            meta = info.get("extmetadata") or {}
            license_name = meta.get("LicenseShortName", {}).get("value", "Unknown")
            license_url = meta.get("LicenseUrl", {}).get("value", "")
            artist = _strip_html(meta.get("Artist", {}).get("value", "")) or "Unknown creator"
            title = (page.get("title") or "").replace("File:", "")
            landing_url = f"https://commons.wikimedia.org/wiki/{(page.get('title') or '').replace(' ', '_')}"
            candidates.append(RawCandidate(
                source=self.name,
                media_id=str(page.get("pageid", "")),
                title=title,
                direct_url=direct_url,
                landing_url=landing_url,
                license=license_name,
                license_url=license_url,
                attribution=f'"{title}" by {artist}, via Wikimedia Commons, licensed {license_name}',
                width=info.get("width"),
                height=info.get("height"),
            ))
        return candidates[: self.max_results]
