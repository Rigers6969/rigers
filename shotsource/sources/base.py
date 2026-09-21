"""Common interface every media source implements. `http` is a
CachedSession bound to this source's own rate limiter, so a source's
search() and any binary downloads it triggers both respect the same
requests-per-minute limit and the same on-disk cache."""
from __future__ import annotations

from typing import List

from ..cache import CachedSession
from ..models import RawCandidate


class BaseSource:
    name = "base"

    def __init__(self, http: CachedSession, max_results: int):
        self.http = http
        self.max_results = max_results

    def search(self, query: str) -> List[RawCandidate]:
        raise NotImplementedError
