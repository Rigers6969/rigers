"""Flickr (flickr.com) via its REST API - requires a free API key. Flickr
is enormous compared to any single stock site, so this is a real increase
in match rate, not just one more thin source.

Only license ids that permit commercial reuse are requested - Flickr's
NonCommercial-only licenses (1, 2, 3) are excluded outright, since these
videos get monetized. See https://www.flickr.com/services/api/flickr.photos.licenses.getInfo.html
for the full list; the ones kept here are:
    4  Attribution
    5  Attribution-ShareAlike
    6  Attribution-NoDerivs
    7  No known copyright restrictions (Flickr Commons)
    8  United States Government Work
    9  Public Domain Dedication (CC0)
    10 Public Domain Mark
"""
from __future__ import annotations

import os
from typing import List

from ..models import RawCandidate
from .base import BaseSource

API_URL = "https://www.flickr.com/services/rest/"
COMMERCIAL_SAFE_LICENSES = "4,5,6,7,8,9,10"
_LICENSE_NAMES = {
    "4": "CC BY 2.0", "5": "CC BY-SA 2.0", "6": "CC BY-ND 2.0",
    "7": "No known copyright restrictions", "8": "United States Government Work",
    "9": "Public Domain Dedication (CC0)", "10": "Public Domain Mark",
}


class FlickrSource(BaseSource):
    name = "flickr"

    def __init__(self, http, max_results: int, api_key_env: str = "FLICKR_API_KEY"):
        super().__init__(http, max_results)
        self.api_key = os.environ.get(api_key_env, "")

    def search(self, query: str) -> List[RawCandidate]:
        if not self.api_key:
            return []
        per_page = min(self.max_results, 250)
        data = self.http.get_json(API_URL, params={
            "method": "flickr.photos.search",
            "api_key": self.api_key,
            "text": query,
            "license": COMMERCIAL_SAFE_LICENSES,
            "sort": "relevance",
            "content_type": 1,  # photos only
            "media": "photos",
            "per_page": per_page,
            "extras": "url_o,url_l,owner_name,license",
            "format": "json",
            "nojsoncallback": 1,
        })
        photos = ((data.get("photos") or {}).get("photo")) or []
        candidates = []
        for photo in photos[: self.max_results]:
            direct_url = photo.get("url_o") or photo.get("url_l") or ""
            if not direct_url:
                continue
            license_id = str(photo.get("license", ""))
            license_name = _LICENSE_NAMES.get(license_id, "Unknown")
            owner = photo.get("ownername") or "Unknown photographer"
            landing_url = f"https://www.flickr.com/photos/{photo.get('owner', '')}/{photo.get('id', '')}"
            candidates.append(RawCandidate(
                source=self.name,
                media_id=str(photo.get("id", "")),
                title=photo.get("title") or "",
                direct_url=direct_url,
                landing_url=landing_url,
                license=license_name,
                license_url="https://www.flickr.com/creativecommons/",
                attribution=f"Photo by {owner} on Flickr, licensed {license_name} ({landing_url})",
                width=int(photo["width_o"]) if photo.get("width_o") else None,
                height=int(photo["height_o"]) if photo.get("height_o") else None,
            ))
        return candidates
