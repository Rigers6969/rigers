"""books.py: the 100-book list, Gutenberg download (mocked), reading pages, progress."""
import pytest

import books


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setattr(books, "BOOKS_DIR", tmp_path / "books")
    monkeypatch.setattr(books, "PROGRESS_FILE", tmp_path / "progress.json")
    return tmp_path


class Resp:
    def __init__(self, data=None, text="", content=b""):
        self._data, self.text, self.content, self.encoding = data, text, content, "utf-8"

    def json(self):
        return self._data


def test_list_has_100_books_and_free_ones(lib):
    data = books.library()
    assert len(data["books"]) == 100 and data["done"] == 0
    assert data["free"] >= 20
    assert all(b["links"]["openlibrary"].startswith("https://openlibrary.org") for b in data["books"])


def test_download_finds_right_author_and_strips_licence(lib, monkeypatch):
    text = "header\n*** START OF THE PROJECT GUTENBERG EBOOK X ***\nChapter 1\n\nHello world.\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\nlicence"
    def fake_get(url, **kw):
        if url == books.GUTENDEX:
            return Resp({"results": [
                {"id": 1, "authors": [{"name": "Someone, Else"}], "formats": {}},
                {"id": 2, "authors": [{"name": "Bennett, Arnold"}],
                 "formats": {"text/plain; charset=utf-8": "https://x/2.txt", "application/epub+zip": "https://x/2.epub"}}]})
        if url.endswith(".txt"):
            return Resp(text=text)
        return Resp(content=b"EPUB")
    monkeypatch.setattr(books, "_get", fake_get)
    out = books.download(8)  # How to Live on 24 Hours a Day - Arnold Bennett
    assert out["gutenberg_id"] == 2
    b = books.book(8)
    body = b["txt"].read_text(encoding="utf-8")
    assert "Hello world." in body and "licence" not in body and "header" not in body
    assert b["epub"].read_bytes() == b"EPUB"
    with pytest.raises(books.BookError):
        books.download(35)  # Bad Blood: not free


def test_reading_saves_page_and_status(lib):
    b = books.book(9)
    b["txt"].parent.mkdir(parents=True)
    b["txt"].write_text(("Paragraph. " * 40 + "\n\n") * 60, encoding="utf-8")
    p = books.read_page(9, 1)
    assert p["page"] == 1 and p["pages"] > 2 and p["status"] == "reading"
    assert books.read_page(9)["page"] == 1  # remembers where you stopped
    data = books.set_status(9, "done")
    assert data["done"] == 1


def test_gutendex_down_uses_gutenberg_search(lib, monkeypatch):
    import requests
    opds = b"""<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom">
    <entry><title>Some Other Book</title><content type="text">by Someone</content>
      <link type="application/atom+xml;profile=opds-catalog" href="/ebooks/111.opds"/></entry>
    <entry><title>The Art of Money Getting</title><content type="text">P. T. Barnum</content>
      <link type="application/atom+xml;profile=opds-catalog" href="/ebooks/8581.opds"/></entry></feed>"""
    calls = []
    def fake_get(url, **kw):
        calls.append(url)
        if url == books.GUTENDEX:
            raise requests.HTTPError("503 Server Error")
        if "search.opds" in url:
            return Resp(content=opds)
        if url.endswith(".txt.utf-8"):
            return Resp(text="*** START OF THE PROJECT GUTENBERG EBOOK X ***\nMoney!\n*** END OF THE PROJECT GUTENBERG EBOOK X ***")
        return Resp(content=b"EPUB")
    monkeypatch.setattr(books, "_get", fake_get)
    monkeypatch.setattr(books.time, "sleep", lambda s: None)
    out = books.download(4)  # The Art of Money Getting - P. T. Barnum
    assert out["gutenberg_id"] == 8581
    assert "Money!" in books.book(4)["txt"].read_text(encoding="utf-8")
    assert calls.count(books.GUTENDEX) == 2  # tried twice before the backup
