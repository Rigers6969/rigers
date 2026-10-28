"""pro_thumbnails.py: picks the best picture, makes 3 looks, texts from the writer or the title."""
import json

from PIL import Image, ImageDraw

import pro_thumbnails as pt


def _photo(path, busy):
    im = Image.new("RGB", (1280, 720), (90, 90, 90))
    if busy:
        d = ImageDraw.Draw(im)
        for i in range(0, 1280, 40):
            d.rectangle([i, 200, i + 20, 600], fill=(200, 40 + i % 200, 30))
    im.save(path)


def test_three_thumbnails_from_best_photo(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    _photo(media / "flat.jpg", False)
    _photo(media / "busy.jpg", True)
    class W:
        def _call_model(self, p, max_tokens=0):
            return '["$70 BILLION GONE", "HE KNEW", "NOBODY NOTICED"]'
    out = pt.make_thumbnails(tmp_path, "How Enron Lost $70 Billion", "Enron fraud", "Paper Trail", W())
    assert [p.name for p in out] == ["thumb_1.jpg", "thumb_2.jpg", "thumb_3.jpg"]
    assert Image.open(out[0]).size == (1280, 720)
    meta = json.loads((tmp_path / "thumbs.json").read_text())
    assert meta[0]["text"] == "$70 BILLION GONE" and meta[2]["look"] == "stamp"
    assert pt.best_images(tmp_path, 1)  # the busy photo ranks first
    assert pt.image_score(Image.open(media / "busy.jpg")) > pt.image_score(Image.open(media / "flat.jpg"))


def test_texts_without_writer_and_stamp_word():
    texts = pt.make_texts("How Enron Lost $70 Billion in 16 Months", "", "")
    assert texts[0].startswith("$70 BILLION")
    assert pt.stamp_word("The Ponzi king", "") == "PONZI"
    assert pt.stamp_word("A quiet story", "") == "EXPOSED"


def test_no_pictures_no_thumbnails(tmp_path):
    assert pt.make_thumbnails(tmp_path, "Title") == []
