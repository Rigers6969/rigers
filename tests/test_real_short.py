"""Real-footage Shorts: word timing and the full build with local test clips and a fake voice."""
import json
import subprocess

import numpy as np

import real_short


def test_word_timings_spread_over_line():
    w = real_short.word_timings(["One TWO three"], [(1.0, 2.5)])
    assert [x["word"] for x in w] == ["One", "TWO", "three"]
    assert w[0]["start"] == 1.0 and abs(w[-1]["end"] - 2.5) < 1e-6


def test_full_build(tmp_path, monkeypatch):
    clips = tmp_path / "clips"
    clips.mkdir()
    for i in range(3):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30", "-t", "4",
                        "-pix_fmt", "yuv420p", str(clips / f"c{i}.mp4")], check=True)
    story = {"slug": "test-real-short", "title": "TEST TITLE", "scenes": [
        {"say": "First line here.", "cap": "First LINE here.", "clips": ["a"]},
        {"say": "Second line now.", "cap": "Second line NOW.", "clips": ["b"]}],
        "upload": {"title": "T", "description": "D", "tags": ["x"], "pinned": "P"}}
    sp = tmp_path / "s.json"
    sp.write_text(json.dumps(story))
    import photo_short
    monkeypatch.setattr(photo_short, "voice_lines", lambda texts, v, r: [np.sin(np.arange(24000 * 2) / 20).astype(np.float32) * 0.3
                                                                        for _ in texts])
    monkeypatch.setattr(real_short, "APP", tmp_path)
    (tmp_path / "fonts").symlink_to(real_short.Path(__file__).resolve().parents[1] / "fonts")
    out = real_short.build(sp, offline_clips=clips)
    import video_assembler as va
    assert va.get_video_dimensions(out) == (1080, 1920)
    assert 4.0 < va.get_duration_seconds(out) < 5.0
    assert (tmp_path / "content" / "test-real-short" / "UPLOAD.txt").exists()
