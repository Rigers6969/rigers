"""archive.org via its advancedsearch + metadata APIs. Only items that
carry an explicit `licenseurl` are kept - archive.org hosts a huge amount
of material with no clear rights statement, and this tool only wants
openly-licensed media, not "unknown, probably fine"."""
from __future__ import annotations

from typing import List, Optional, Tuple

from ..models import RawCandidate
from .base import BaseSource

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/{identifier}"

_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff")


def _license_name(license_url: str) -> str:
    lowered = license_url.lower()
    if "publicdomain" in lowered or "/pdm" in lowered or "zero" in lowered:
        return "Public Domain"
    if "creativecommons.org/licenses" in lowered:
        parts = license_url.rstrip("/").split("/")
        for i, part in enumerate(parts):
            if part == "licenses" and i + 1 < len(parts):
                return f"CC {parts[i + 1].upper()}"
    return "Open License"


class ArchiveOrgSource(BaseSource):
    name = "archive_org"

    def search(self, query: str) -> List[RawCandidate]:
        rows = min(self.max_results * 2, 100)  # over-fetch: many docs get skipped for missing license/files
        data = self.http.get_json(SEARCH_URL, params={
            "q": f"{query} AND mediatype:image",
            "fl[]": ["identifier", "title", "licenseurl"],
            "rows": rows,
            "page": 1,
            "output": "json",
        })
        docs = ((data.get("response") or {}).get("docs")) or []
        candidates = []
        for doc in docs:
            license_url = doc.get("licenseurl") or ""
            identifier = doc.get("identifier")
            if not license_url or not identifier:
                continue
            file_info = self._best_image_file(identifier)
            if not file_info:
                continue
            filename, width, height = file_info
            title = doc.get("title") or identifier
            candidates.append(RawCandidate(
                source=self.name,
                media_id=identifier,
                title=title,
                direct_url=f"https://archive.org/download/{identifier}/{filename}",
                landing_url=f"https://archive.org/details/{identifier}",
                license=_license_name(license_url),
                license_url=license_url,
                attribution=f'"{title}", via archive.org ({identifier}), licensed under {license_url}',
                width=width,
                height=height,
            ))
            if len(candidates) >= self.max_results:
                break
        return candidates

    def _best_image_file(self, identifier: str) -> Optional[Tuple[str, Optional[int], Optional[int]]]:
        meta = self.http.get_json(METADATA_URL.format(identifier=identifier))
        best = None
        best_size = -1
        for f in meta.get("files") or []:
            name = f.get("name", "")
            if not name.lower().endswith(_IMAGE_EXTS):
                continue
            try:
                size = int(f.get("size", 0))
            except (TypeError, ValueError):
                size = 0
            if size > best_size:
                best_size = size
                width = int(f["width"]) if str(f.get("width", "")).isdigit() else None
                height = int(f["height"]) if str(f.get("height", "")).isdigit() else None
                best = (name, width, height)
        return best
