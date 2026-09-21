"""Tests for shot-list parsing, the manifest/rejection-log writers, and a
full run_shot() pass wired up with fake sources and a fake similarity
scorer so no network, no real images, and no sentence-transformers model
are needed."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shotsource.config import load_config  # noqa: E402
from shotsource.manifest import manifest_row, write_manifest  # noqa: E402
from shotsource.models import RawCandidate, ScoredCandidate, Shot  # noqa: E402
from shotsource.pipeline import parse_shots, run_shot  # noqa: E402
from shotsource.rejection_log import RejectionLog  # noqa: E402
from shotsource.sources.base import BaseSource  # noqa: E402


class TestParseShots(unittest.TestCase):
    def test_parses_json_list_of_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shots.json"
            path.write_text(json.dumps(["shot one", "shot two"]), encoding="utf-8")
            shots = parse_shots(str(path))
            self.assertEqual([s.description for s in shots], ["shot one", "shot two"])
            self.assertEqual(shots[0].id, "shot-001")

    def test_parses_json_list_of_objects_with_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shots.json"
            path.write_text(json.dumps([{"id": "cafeteria", "description": "1970s cafeteria"}]), encoding="utf-8")
            shots = parse_shots(str(path))
            self.assertEqual(shots[0].id, "cafeteria")
            self.assertEqual(shots[0].description, "1970s cafeteria")

    def test_parses_markdown_bullets_and_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shots.md"
            path.write_text(
                "# Shot list\n"
                "- 1970s university cafeteria\n"
                "* crowded dinner table candlelight\n"
                "1. empty hospital corridor\n"
                "\n"
                "busy newsroom 1980s\n",
                encoding="utf-8",
            )
            shots = parse_shots(str(path))
            self.assertEqual(len(shots), 4)
            self.assertEqual(shots[0].description, "1970s university cafeteria")
            self.assertEqual(shots[2].description, "empty hospital corridor")
            self.assertEqual(shots[3].description, "busy newsroom 1980s")

    def test_blank_lines_and_headings_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shots.md"
            path.write_text("# Title\n\n\n- only shot\n", encoding="utf-8")
            shots = parse_shots(str(path))
            self.assertEqual(len(shots), 1)


class TestManifestAndRejectionLog(unittest.TestCase):
    def test_manifest_row_and_write_round_trip(self):
        candidate = RawCandidate(
            source="openverse", media_id="abc", title="a cafeteria",
            direct_url="https://example.com/img.jpg", landing_url="https://example.com/page",
            license="CC BY 4.0", license_url="https://creativecommons.org/licenses/by/4.0/",
            attribution="photo by someone",
        )
        scored = ScoredCandidate(
            candidate=candidate, local_path="/out/shot-001/01_openverse_abc.jpg",
            width=4000, height=3000, resolution_score=1.0, sharpness_score=0.8,
            caption_similarity_score=0.6, final_score=0.8,
        )
        row = manifest_row("shot-001", "1970s cafeteria", 1, scored)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.csv"
            write_manifest(path, [row])
            with open(path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source"], "openverse")
            self.assertEqual(rows[0]["license"], "CC BY 4.0")
            self.assertEqual(rows[0]["final_score"], "0.8")

    def test_rejection_log_writes_reason_per_row(self):
        candidate = RawCandidate(
            source="loc", media_id="x", title="unclear photo",
            direct_url="https://example.com/x.jpg", landing_url="", license="", license_url="", attribution="",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rejections.csv"
            with RejectionLog(path) as log:
                log.reject("shot-001", "a shot", candidate, "license missing or unclear")
            with open(path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["reason"], "license missing or unclear")
            self.assertEqual(rows[0]["source"], "loc")


def _write_test_image(path: Path, width: int, height: int, seed: int) -> None:
    rng = np.random.RandomState(seed)
    array = rng.randint(0, 256, size=(height, width, 3), dtype=np.uint8)
    Image.fromarray(array, mode="RGB").save(path)


class FakeSource(BaseSource):
    """A source whose search() just returns a fixed list of candidates,
    and whose `.http` downloads from a local temp dir instead of the
    network - lets run_shot() be exercised end-to-end without touching
    any real API or sentence-transformers model."""

    def __init__(self, name: str, candidates, image_dir: Path):
        self.name = name
        self._candidates = candidates
        self.http = _FakeHttpForDownload(image_dir)

    def search(self, query: str):
        return self._candidates


class _FakeHttpForDownload:
    def __init__(self, image_dir: Path):
        self.image_dir = image_dir

    def get_binary(self, url: str) -> Path:
        # In these tests, direct_url is literally the local filename.
        return self.image_dir / url


class FakeSimilarityScorer:
    def __init__(self, score: float = 0.9):
        self._score = score

    def score(self, shot_description: str, caption: str) -> float:
        return self._score


class TestRunShotEndToEnd(unittest.TestCase):
    def test_keeps_top_n_and_logs_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            image_dir = tmp_path / "images"
            image_dir.mkdir()
            output_dir = tmp_path / "output"

            good_names = [f"good_{i}.jpg" for i in range(6)]
            for i, name in enumerate(good_names):
                _write_test_image(image_dir / name, 1920, 1000, seed=100 + i)
            _write_test_image(image_dir / "too_small.jpg", 800, 500, seed=999)

            candidates = [
                RawCandidate(
                    source="fake", media_id=name, title="1970s cafeteria",
                    direct_url=name, landing_url=f"https://example.com/{name}",
                    license="CC BY 4.0", license_url="https://creativecommons.org/licenses/by/4.0/",
                    attribution=f"photo {name}",
                )
                for name in good_names
            ]
            candidates.append(RawCandidate(
                source="fake", media_id="too_small.jpg", title="too small",
                direct_url="too_small.jpg", landing_url="https://example.com/too_small.jpg",
                license="CC BY 4.0", license_url="https://creativecommons.org/licenses/by/4.0/",
                attribution="photo too_small",
            ))
            candidates.append(RawCandidate(
                source="fake", media_id="no_license.jpg", title="no license",
                direct_url="good_0.jpg", landing_url="https://example.com/no_license.jpg",
                license="", license_url="", attribution="",
            ))

            source = FakeSource("fake", candidates, image_dir)
            shot = Shot(id="shot-001", description="1970s university cafeteria")
            config = load_config()

            with RejectionLog(tmp_path / "rejections.csv") as reject_log:
                rows = run_shot(shot, {"fake": source}, FakeSimilarityScorer(), config, output_dir, reject_log)

            self.assertEqual(len(rows), config.top_n_per_shot)
            for row in rows:
                self.assertTrue(Path(row["local_path"]).exists())

            with open(tmp_path / "rejections.csv", newline="", encoding="utf-8") as f:
                reject_rows = list(csv.DictReader(f))
            reasons = {r["media_id"]: r["reason"] for r in reject_rows}
            self.assertIn("too_small.jpg", reasons)
            self.assertIn("width", reasons["too_small.jpg"])
            self.assertIn("no_license.jpg", reasons)
            self.assertIn("license", reasons["no_license.jpg"])
            # One of the 6 valid, differently-licensed candidates should have
            # been cut for the top-N cutoff, not for a hard-reject reason.
            cutoff_reasons = [r for r in reject_rows if r["reason"] == "below top-N cutoff after scoring"]
            self.assertEqual(len(cutoff_reasons), 1)


if __name__ == "__main__":
    unittest.main()
