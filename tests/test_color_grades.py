"""Every colour grade (and a .cube LUT) runs through ffmpeg without errors."""
import subprocess

import pytest

import video_editor as ve


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    p = tmp_path_factory.mktemp("g") / "in.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-t", "1",
                    "-pix_fmt", "yuv420p", str(p)], check=True)
    return p


@pytest.mark.parametrize("grade", [g for g in ve.GRADES if g != "none"])
def test_grade_runs(clip, grade, tmp_path):
    out = tmp_path / "o.mp4"
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(clip), "-vf", ve.grade_filter(grade) + ",format=yuv420p",
                        str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.stat().st_size > 0


def test_lut_option(tmp_path, monkeypatch, clip):
    monkeypatch.setattr(ve, "LUT_DIR", tmp_path)
    lines = ["LUT_3D_SIZE 2"] + [f"{r} {g} {b}" for b in (0, 1) for g in (0, 1) for r in (0, 1)]
    (tmp_path / "Daylight.cube").write_text("\n".join(lines) + "\n")
    assert {"id": "lut:Daylight.cube", "label": "LUT: Daylight"} in ve.grade_options()
    out = tmp_path / "o.mp4"
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(clip), "-vf", ve.grade_filter("lut:Daylight.cube"),
                        str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert ve.grade_filter("lut:missing.cube") == "" and ve.grade_filter("nope") == ""


def test_look_saves_grade(tmp_path, monkeypatch):
    monkeypatch.setattr(ve, "LOOK_FILE", tmp_path / "look.json")
    assert ve.load_look()["grade"] == "doc_warm"
    assert ve.save_look({"grade": "money_gold"})["grade"] == "money_gold"
    assert ve.save_look({"grade": "rm -rf"})["grade"] == "money_gold"   # unknown names are ignored
