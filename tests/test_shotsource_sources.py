"""Tests for each source's JSON-parsing logic, using canned API responses
instead of real network calls - same pattern as tests/test_branding.py's
ScriptedBrandGenerator."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shotsource.sources.archive_org import ArchiveOrgSource  # noqa: E402
from shotsource.sources.loc import LocSource  # noqa: E402
from shotsource.sources.openverse import OpenverseSource  # noqa: E402
from shotsource.sources.pexels import PexelsSource  # noqa: E402
from shotsource.sources.wikimedia import WikimediaSource  # noqa: E402


class FakeHttp:
    """Stands in for CachedSession: records requested URLs and returns
    pre-scripted JSON per URL, so each source class can be tested against a
    frozen sample of what its real API actually returns."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.requested = []

    def get_json(self, url, params=None, headers=None):
        self.requested.append((url, params, headers))
        if url not in self.responses:
            raise AssertionError(f"no scripted response for {url}")
        response = self.responses[url]
        return response(params) if callable(response) else response


class TestOpenverseSource(unittest.TestCase):
    def test_parses_results_into_candidates(self):
        from shotsource.sources.openverse import API_URL

        response = {
            "results": [{
                "id": "abc123",
                "title": "1970s cafeteria",
                "url": "https://example.com/image.jpg",
                "foreign_landing_url": "https://example.com/page",
                "license": "by",
                "license_version": "4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "attribution": "photo by someone",
                "creator": "Someone",
                "provider": "flickr",
                "width": 4000,
                "height": 3000,
            }]
        }
        http = FakeHttp({API_URL: response})
        source = OpenverseSource(http, max_results=10)
        candidates = source.search("1970s cafeteria")
        self.assertEqual(len(candidates), 1)
        c = candidates[0]
        self.assertEqual(c.direct_url, "https://example.com/image.jpg")
        self.assertEqual(c.license, "BY 4.0")
        self.assertEqual(c.width, 4000)

    def test_results_missing_url_are_skipped(self):
        from shotsource.sources.openverse import API_URL

        http = FakeHttp({API_URL: {"results": [{"id": "x", "title": "no url"}]}})
        source = OpenverseSource(http, max_results=10)
        self.assertEqual(source.search("query"), [])


class TestWikimediaSource(unittest.TestCase):
    def test_parses_pages_with_imageinfo(self):
        from shotsource.sources.wikimedia import API_URL

        response = {
            "query": {
                "pages": {
                    "123": {
                        "pageid": 123,
                        "title": "File:Cafeteria 1975.jpg",
                        "imageinfo": [{
                            "url": "https://upload.wikimedia.org/cafeteria.jpg",
                            "width": 3000,
                            "height": 2000,
                            "extmetadata": {
                                "LicenseShortName": {"value": "Public domain"},
                                "LicenseUrl": {"value": "https://creativecommons.org/publicdomain/mark/1.0/"},
                                "Artist": {"value": "<span>John Doe</span>"},
                            },
                        }],
                    },
                    "456": {"pageid": 456, "title": "File:NoInfo.jpg", "imageinfo": []},
                }
            }
        }
        http = FakeHttp({API_URL: response})
        source = WikimediaSource(http, max_results=10)
        candidates = source.search("cafeteria")
        self.assertEqual(len(candidates), 1)
        c = candidates[0]
        self.assertEqual(c.license, "Public domain")
        self.assertIn("John Doe", c.attribution)
        self.assertNotIn("<span>", c.attribution)


class TestLocSource(unittest.TestCase):
    def test_recognizes_no_known_restrictions(self):
        from shotsource.sources.loc import API_URL

        response = {"results": [{
            "id": "https://www.loc.gov/item/1234/",
            "title": "University cafeteria",
            "image_url": ["small.jpg", "large.jpg"],
            "rights": "No known restrictions on publication.",
        }]}
        http = FakeHttp({API_URL: response})
        source = LocSource(http, max_results=10)
        candidates = source.search("cafeteria")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].direct_url, "large.jpg")
        self.assertIn("No Known Restrictions", candidates[0].license)

    def test_unclear_rights_leave_license_empty(self):
        from shotsource.sources.loc import API_URL

        response = {"results": [{
            "id": "https://www.loc.gov/item/5678/",
            "title": "Mystery photo",
            "image_url": ["photo.jpg"],
        }]}
        http = FakeHttp({API_URL: response})
        source = LocSource(http, max_results=10)
        candidates = source.search("mystery")
        self.assertEqual(candidates[0].license, "")


class TestArchiveOrgSource(unittest.TestCase):
    def test_skips_docs_without_license_or_files(self):
        from shotsource.sources.archive_org import METADATA_URL, SEARCH_URL

        search_response = {"response": {"docs": [
            {"identifier": "no-license", "title": "No license"},
            {"identifier": "has-license", "title": "Has license", "licenseurl": "https://creativecommons.org/licenses/by/4.0/"},
        ]}}
        metadata_response = {"files": [
            {"name": "thumb.png", "size": "100"},
            {"name": "full.jpg", "size": "500000", "width": "4000", "height": "2000"},
        ]}
        http = FakeHttp({
            SEARCH_URL: search_response,
            METADATA_URL.format(identifier="has-license"): metadata_response,
        })
        source = ArchiveOrgSource(http, max_results=10)
        candidates = source.search("query")
        self.assertEqual(len(candidates), 1)
        c = candidates[0]
        self.assertEqual(c.media_id, "has-license")
        self.assertIn("full.jpg", c.direct_url)
        self.assertEqual(c.width, 4000)
        self.assertEqual(c.license, "CC BY")


class TestPexelsSource(unittest.TestCase):
    def test_returns_empty_without_api_key(self, monkeypatch=None):
        import os

        os.environ.pop("PEXELS_API_KEY", None)
        http = FakeHttp({})
        source = PexelsSource(http, max_results=10)
        self.assertEqual(source.search("query"), [])
        self.assertEqual(http.requested, [])

    def test_parses_photos_with_api_key(self):
        import os

        from shotsource.sources.pexels import API_URL

        os.environ["PEXELS_API_KEY"] = "test-key"
        try:
            response = {"photos": [{
                "id": 99,
                "alt": "dinner table candlelight",
                "src": {"original": "https://images.pexels.com/photo.jpg"},
                "url": "https://www.pexels.com/photo/99/",
                "photographer": "Jane Photographer",
                "width": 5000,
                "height": 3000,
            }]}
            http = FakeHttp({API_URL: response})
            source = PexelsSource(http, max_results=10)
            candidates = source.search("dinner table")
            self.assertEqual(len(candidates), 1)
            self.assertIn("Jane Photographer", candidates[0].attribution)
        finally:
            os.environ.pop("PEXELS_API_KEY", None)


if __name__ == "__main__":
    unittest.main()
