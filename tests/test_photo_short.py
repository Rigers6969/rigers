"""photo_short.py: only free Wikipedia photos are picked, matched to each scene, with credits."""
import io

from PIL import Image

import photo_short


class FakeResp:
    def __init__(self, data=None, content=b""):
        self._d, self.content = data, content

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


def _info(name, lic, nonfree="false", mime="image/jpeg", w=1200, h=800):
    return {"title": name, "imageinfo": [{"thumburl": "https://x/" + name, "url": "https://x/" + name, "mime": mime,
            "width": w, "height": h, "descriptionurl": "https://commons/" + name,
            "extmetadata": {"LicenseShortName": {"value": lic}, "NonFree": {"value": nonfree}, "Artist": {"value": "<a>Someone</a>"}}}]}


def test_picks_only_free_matching_photos(tmp_path, monkeypatch):
    pages = {"1": _info("File:Radium dial painters.jpg", "Public domain"),
             "2": _info("File:Company logo.png", "Public domain", mime="image/png"),
             "3": _info("File:Court photo.jpg", "Fair use", nonfree="true"),
             "4": _info("File:Undark advert.jpg", "CC BY-SA 4.0"),
             "5": _info("File:Tiny.jpg", "CC0", w=200, h=150)}
    buf = io.BytesIO()
    Image.new("RGB", (50, 40), "red").save(buf, "JPEG")

    class Sess:
        headers = {}

        def get(self, url, params=None, timeout=None):
            return FakeResp({"query": {"pages": pages}}) if params else FakeResp(content=buf.getvalue())

    import requests
    monkeypatch.setattr(requests, "Session", Sess)
    scenes = [{"img": {"pages": ["Radium Girls"], "want": ["undark"]}},
              {"img": None},
              {"img": {"pages": ["Radium Girls"], "want": ["dial"]}},
              {"img": {"pages": ["Radium Girls"], "want": ["court"], "any": False}}]
    photos, credits = photo_short.pick_photos(scenes, tmp_path, None)
    assert [p is not None for p in photos] == [True, False, True, False]
    assert [c["name"] for c in credits] == ["File:Undark advert.jpg", "File:Radium dial painters.jpg"]
    assert credits[0]["artist"] == "Someone" and credits[0]["license"] == "CC BY-SA 4.0"


def test_caption_chunks():
    assert photo_short.chunks("Lip. Dip. Paint.") == [["Lip."], ["Dip."], ["Paint."]]
    assert photo_short.chunks("one two three four") == [["one", "two", "three"], ["four"]]
