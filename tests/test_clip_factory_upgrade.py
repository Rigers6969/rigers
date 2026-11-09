"""Clip Factory upgrade: face-tracking crop, speaker detection, energy scoring, strongest-line start, full render."""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "clip-factory"))
import facecrop  # noqa: E402
import moments  # noqa: E402


@pytest.fixture(scope="module")
def red_blue(tmp_path_factory):
    src = tmp_path_factory.mktemp("cf") / "lr.mp4"  # left half red, right half blue, with a tone
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=red:s=640x720:r=25:d=5", "-f", "lavfi",
                    "-i", "color=blue:s=640x720:r=25:d=5", "-f", "lavfi", "-i", "sine=f=300:d=5",
                    "-filter_complex", "[0:v][1:v]hstack[v]", "-map", "[v]", "-map", "2:a", "-t", "5", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", str(src)], check=True)
    return src


def _color(path, t, w, h):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1", "-vf", f"scale={w}:{h}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(h, w, 3).mean(axis=(0, 1))
    return "red" if a[0] > a[2] else "blue"


def test_crop_follows_speaker(red_blue, tmp_path):
    expr = facecrop.x_expression([(i / 5, 0.25 if i < 10 else 0.75) for i in range(25)])
    out = tmp_path / "o.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(red_blue), "-vf", f"crop=w='ih*9/16':h=ih:x='{expr}':y=0", str(out)],
                   check=True)
    assert _color(out, 1.0, 90, 160) == "red" and _color(out, 3.0, 90, 160) == "blue"


def test_speaker_is_the_moving_mouth():
    two_faces = lambda img: [(60, 100, 100, 100), (320, 100, 100, 100)]
    frames = np.zeros((20, 270, 480), np.uint8)
    rng = np.random.default_rng(0)
    for i in range(20):
        frames[i, 160:220, 340:400] = rng.integers(0, 255, (60, 60))  # only the right face's mouth moves
    assert facecrop.speaker_path(frames, detect=two_faces)[-1][1] > 0.6
    assert facecrop.speaker_path(frames, detect=lambda img: []) is None  # no faces -> normal centre crop


def test_real_detector_loads():
    pytest.importorskip("cv2")
    detect = facecrop.make_detector(480, 270)
    assert detect(np.zeros((270, 480), np.uint8)) == []


def test_energy_and_strongest_start():
    c = [{"start": 0, "end": 20, "score": 5.0, "text": "a"}, {"start": 20, "end": 40, "score": 5.0, "text": "b"}]
    words = [{"start": i * 0.3, "end": i * 0.3 + 0.2, "text": "w"} for i in range(130)]
    moments.add_energy(c, [0.05] * 40 + [0.2] * 40, words)
    assert c[1]["score"] > c[0]["score"]
    sents = [{"start": 0, "end": 4, "text": "So yeah, um, okay."}, {"start": 4, "end": 9, "text": "He lost 3 billion dollars in one day!"},
             {"start": 9, "end": 30, "text": "And nobody knew why it happened to him."}]
    assert moments.tighten_start({"start": 0, "end": 30, "text": "", "score": 5}, sents, 15)["start"] == 4
    assert moments.tighten_start({"start": 0, "end": 30, "text": "", "score": 5}, sents, 28)["start"] == 0  # too short then


def test_full_render_with_tracking(red_blue, tmp_path, monkeypatch):
    import renderer

    monkeypatch.setattr(facecrop, "track_expr", lambda src, s, l, offset=0.0: facecrop.x_expression([(0, 0.75), (1, 0.75)]))
    words = [{"start": 0.2 + i * 0.4, "end": 0.5 + i * 0.4, "text": w} for i, w in enumerate("this is a test of the crop".split())]
    out = tmp_path / "clip.mp4"
    renderer.render_clip(red_blue, 0.0, 3.0, words, "Test title", "crop", "hormozi", out, tmp_path / "p.jpg")
    assert _color(out, 1.5, 90, 160) == "blue"  # followed the right-hand speaker
