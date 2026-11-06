"""Stock video clips: picking from Pexels/Pixabay (faked), skipping old-history shots, cutting a clip, saving keys."""
import subprocess

import pytest

import autopilot
import video_assembler as va
from shotsource import video_clips as vc


class Resp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


PEXELS = {"videos": [
    {"id": 1, "duration": 12, "url": "https://www.pexels.com/video/man-counting-money-123/", "user": {"name": "Ann"},
     "video_files": [{"file_type": "video/mp4", "width": 3840, "height": 2160, "link": "https://v/4k.mp4"},
                     {"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "https://v/hd.mp4"},
                     {"file_type": "video/mp4", "width": 640, "height": 360, "link": "https://v/sd.mp4"}]},
    {"id": 2, "duration": 2, "url": "https://www.pexels.com/video/too-short-9/", "user": {},
     "video_files": [{"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "https://v/short.mp4"}]},
]}
PIXABAY = {"hits": [{"id": 7, "duration": 9, "tags": "cat, kitten, pet", "pageURL": "https://pixabay.com/x", "user": "bob",
                     "videos": {"large": {"url": "https://p/l.mp4", "width": 3840, "height": 2160},
                                "medium": {"url": "https://p/m.mp4", "width": 1920, "height": 1080}}}]}


class Sim:
    def score_many(self, desc, titles):
        return [len(set(desc.lower().split()) & set(t.lower().replace(",", "").split())) / 3 for t in titles]


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "k" * 20)
    monkeypatch.setenv("PIXABAY_API_KEY", "p" * 20)
    monkeypatch.setattr(vc.requests, "get", lambda url, **kw: Resp(PEXELS if "pexels" in url else PIXABAY))


def test_picks_1080p_and_best_match(keys):
    clip = vc.best_clip("a man counting money", Sim(), used=set())
    assert clip["url"] == "https://v/hd.mp4" and clip["source"] == "pexels_video"   # 1080p, not 4K
    assert "Pexels" in clip["credit"]
    cat = vc.best_clip("a cute cat kitten", Sim(), used=set())
    assert cat["url"] == "https://p/m.mp4"                                          # Pixabay medium (1080p)
    assert vc.best_clip("a man counting money", Sim(), used={"pexels-1"}) is None    # never the same clip twice


def test_skips_history_and_no_keys(keys, monkeypatch):
    assert vc.is_historical("Charles Ponzi in Boston, 1920") and vc.is_historical("Victorian London street")
    assert not vc.is_historical("Costco food court today")
    assert vc.best_clip("money counting in 1920", Sim(), used=set()) is None
    monkeypatch.delenv("PEXELS_API_KEY")
    monkeypatch.delenv("PIXABAY_API_KEY")
    assert not vc.have_keys() and vc.best_clip("a man counting money", Sim(), used=set()) is None


def test_clip_segment_is_cut_and_reframed(tmp_path):
    src = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=25", "-t", "2",
                    "-c:v", "libx264", str(src)], check=True)
    out = tmp_path / "seg.mp4"
    va._make_segment(src, 3.5, out, width=1080, height=1920)  # longer than the clip -> loops; vertical crop
    assert va.get_video_dimensions(out) == (1080, 1920)
    assert abs(va.get_duration_seconds(out) - 3.5) < 0.15


def test_media_keys_saved_to_env_never_returned(tmp_path, monkeypatch):
    monkeypatch.setattr(autopilot, "ENV_FILE", tmp_path / ".env")
    (tmp_path / ".env").write_text("OTHER=1\nPEXELS_API_KEY=old\n")
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    r = autopilot.save_media_keys({"pexels": "A" * 30, "pixabay": ""})
    assert r == {"pexels": True, "pixabay": False}
    text = (tmp_path / ".env").read_text()
    assert "OTHER=1" in text and f"PEXELS_API_KEY={'A' * 30}" in text and "=old" not in text
    with pytest.raises(autopilot.AutopilotError):
        autopilot.save_media_keys({"pixabay": "bad key with spaces"})


def test_finder_uses_clip_and_skips_photo_search(tmp_path, monkeypatch):
    from shotsource import pipeline

    shots = tmp_path / "shots.md"
    shots.write_text("- a man counting money\n- Boston street in 1920\n")
    clip_src = tmp_path / "c.mp4"
    clip_src.write_bytes(b"x")
    monkeypatch.setattr(vc, "have_keys", lambda: True)
    monkeypatch.setattr(vc, "download", lambda clip, cache: clip_src)
    monkeypatch.setattr(vc, "search", lambda q, portrait=False: [
        {"source": "pexels_video", "id": "pexels-1", "title": "man counting money", "url": "u", "page": "p",
         "width": 1920, "height": 1080, "credit": "Video by Ann on Pexels", "license": "Pexels License", "license_url": "l"}])
    monkeypatch.setattr(pipeline, "CaptionSimilarityScorer", lambda name: Sim())
    asked = []
    monkeypatch.setattr(pipeline, "_collect_candidates", lambda shot, sources: asked.append(shot.description) or [])
    manifest = pipeline.run_pipeline(str(shots), output_dir_override=str(tmp_path / "out"))
    rows = manifest.read_text().splitlines()
    assert len(rows) == 2 and "pexels_video" in rows[1] and rows[1].rstrip().endswith(".mp4")
    assert asked == ["Boston street in 1920"]  # photo search only for the old-history shot
