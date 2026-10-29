"""The 100-book library from the 400-day plan.

Free, legal books are downloaded into the books/ folder:
  - "gutenberg": public-domain books from Project Gutenberg, found through the
    Gutendex catalogue (gutendex.com) by title + author, saved as .epub and .txt
  - "link": other free books (OpenStax textbooks, Adobe guides, the Almanack of
    Naval Ravikant) - opened on their own official site
Books that are still under copyright can't be downloaded for free legally;
they get links to borrow (Open Library) or buy.

Reading progress (status, where you stopped) is kept in books_progress.json.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

APP_DIR = Path(__file__).resolve().parent
BOOKS_DIR = APP_DIR / "books"
PROGRESS_FILE = APP_DIR / "books_progress.json"
GUTENDEX = "https://gutendex.com/books/"
USER_AGENT = "WayneFactoryBooks/1.0 (personal reading list)"
PAGE_CHARS = 3500

G, L, B = "gutenberg", "link", "buy"
# (title, author, category, kind, search words or url)
BOOKS = [
    ("The History of the Standard Oil Company", "Ida Tarbell", "Fraud & money", G, "History of the Standard Oil Company"),
    ("Extraordinary Popular Delusions and the Madness of Crowds", "Charles Mackay", "Fraud & money", G, "Extraordinary Popular Delusions"),
    ("Other People's Money", "Louis Brandeis", "Fraud & money", G, "Other People's Money Brandeis"),
    ("The Art of Money Getting", "P. T. Barnum", "Business", G, "Art of Money Getting"),
    ("The Way to Wealth", "Benjamin Franklin", "Business", G, "Way to Wealth Franklin"),
    ("The Autobiography of Benjamin Franklin", "Benjamin Franklin", "Mind", G, "Autobiography of Benjamin Franklin"),
    ("The Richest Man in Babylon", "George S. Clason", "Business", G, "Richest Man in Babylon"),
    ("How to Live on 24 Hours a Day", "Arnold Bennett", "Mind", G, "How to Live on 24 Hours a Day"),
    ("Meditations", "Marcus Aurelius", "Mind", G, "Meditations Marcus Aurelius"),
    ("Letters from a Stoic", "Seneca", "Mind", G, "Seneca Moral Letters Lucilius"),
    ("The Art of War", "Sun Tzu", "History", G, "Art of War Sun"),
    ("The Prince", "Niccolò Machiavelli", "History", G, "The Prince Machiavelli"),
    ("Self-Help", "Samuel Smiles", "Mind", G, "Self-Help Smiles"),
    ("As a Man Thinketh", "James Allen", "Mind", G, "As a Man Thinketh"),
    ("Acres of Diamonds", "Russell Conwell", "Business", G, "Acres of Diamonds"),
    ("The Science of Getting Rich", "Wallace Wattles", "Business", G, "Science of Getting Rich"),
    ("The Jungle", "Upton Sinclair", "History", G, "The Jungle Sinclair"),
    ("The Wealth of Nations", "Adam Smith", "Business", G, "Wealth of Nations"),
    ("The Theory of the Leisure Class", "Thorstein Veblen", "Business", G, "Theory of the Leisure Class"),
    ("The Histories", "Herodotus", "History", G, "Herodotus History"),
    ("The Decline and Fall of the Roman Empire, vol. 1", "Edward Gibbon", "History", G, "History of the Decline and Fall of the Roman Empire Volume 1"),
    ("On the Origin of Species", "Charles Darwin", "Science", G, "On the Origin of Species"),
    ("Relativity: The Special and General Theory", "Albert Einstein", "Science", G, "Relativity Special General Theory"),
    ("The Almanack of Naval Ravikant", "Eric Jorgenson", "Business", L, "https://www.navalmanack.com/"),
    ("Principles of Economics (OpenStax)", "OpenStax", "Business", L, "https://openstax.org/subjects/business"),
    ("Principles of Finance (OpenStax)", "OpenStax", "Business", L, "https://openstax.org/subjects/business"),
    ("U.S. History (OpenStax)", "OpenStax", "History", L, "https://openstax.org/subjects/humanities"),
    ("World History, Volume 1 (OpenStax)", "OpenStax", "History", L, "https://openstax.org/subjects/humanities"),
    ("World History, Volume 2 (OpenStax)", "OpenStax", "History", L, "https://openstax.org/subjects/humanities"),
    ("Astronomy (OpenStax)", "OpenStax", "Science", L, "https://openstax.org/subjects/science"),
    ("Biology (OpenStax)", "OpenStax", "Science", L, "https://openstax.org/subjects/science"),
    ("Psychology (OpenStax)", "OpenStax", "Science", L, "https://openstax.org/subjects/social-sciences"),
    ("Adobe Premiere User Guide", "Adobe", "Editing", L, "https://helpx.adobe.com/premiere-pro/user-guide.html"),
    ("Adobe After Effects User Guide", "Adobe", "Editing", L, "https://helpx.adobe.com/after-effects/user-guide.html"),
    ("Bad Blood", "John Carreyrou", "Fraud & money", B, ""),
    ("The Smartest Guys in the Room", "Bethany McLean & Peter Elkind", "Fraud & money", B, ""),
    ("Billion Dollar Whale", "Tom Wright & Bradley Hope", "Fraud & money", B, ""),
    ("Going Infinite", "Michael Lewis", "Fraud & money", B, ""),
    ("The Big Short", "Michael Lewis", "Fraud & money", B, ""),
    ("Liar's Poker", "Michael Lewis", "Fraud & money", B, ""),
    ("When Genius Failed", "Roger Lowenstein", "Fraud & money", B, ""),
    ("Too Big to Fail", "Andrew Ross Sorkin", "Fraud & money", B, ""),
    ("Barbarians at the Gate", "Bryan Burrough & John Helyar", "Fraud & money", B, ""),
    ("Den of Thieves", "James B. Stewart", "Fraud & money", B, ""),
    ("Super Pumped", "Mike Isaac", "Fraud & money", B, ""),
    ("The Spider Network", "David Enrich", "Fraud & money", B, ""),
    ("Number Go Up", "Zeke Faux", "Fraud & money", B, ""),
    ("The Cult of We", "Eliot Brown & Maureen Farrell", "Fraud & money", B, ""),
    ("Sapiens", "Yuval Noah Harari", "History", B, ""),
    ("Guns, Germs, and Steel", "Jared Diamond", "History", B, ""),
    ("The Silk Roads", "Peter Frankopan", "History", B, ""),
    ("SPQR", "Mary Beard", "History", B, ""),
    ("The Guns of August", "Barbara Tuchman", "History", B, ""),
    ("The Rise and Fall of the Third Reich", "William Shirer", "History", B, ""),
    ("1491", "Charles C. Mann", "History", B, ""),
    ("Team of Rivals", "Doris Kearns Goodwin", "History", B, ""),
    ("A Short History of Nearly Everything", "Bill Bryson", "Science", B, ""),
    ("Cosmos", "Carl Sagan", "Science", B, ""),
    ("The Gene", "Siddhartha Mukherjee", "Science", B, ""),
    ("Astrophysics for People in a Hurry", "Neil deGrasse Tyson", "Science", B, ""),
    ("The Immortal Life of Henrietta Lacks", "Rebecca Skloot", "Science", B, ""),
    ("What If?", "Randall Munroe", "Science", B, ""),
    ("The Disappearing Spoon", "Sam Kean", "Science", B, ""),
    ("Made to Stick", "Chip & Dan Heath", "Story", B, ""),
    ("Contagious", "Jonah Berger", "Story", B, ""),
    ("Save the Cat!", "Blake Snyder", "Story", B, ""),
    ("Story", "Robert McKee", "Story", B, ""),
    ("Storyworthy", "Matthew Dicks", "Story", B, ""),
    ("Influence", "Robert Cialdini", "Story", B, ""),
    ("Hooked", "Nir Eyal", "Story", B, ""),
    ("Building a StoryBrand", "Donald Miller", "Story", B, ""),
    ("Everybody Writes", "Ann Handley", "Story", B, ""),
    ("On Writing Well", "William Zinsser", "Story", B, ""),
    ("In the Blink of an Eye", "Walter Murch", "Editing", B, ""),
    ("The Animator's Survival Kit", "Richard Williams", "Editing", B, ""),
    ("Grammar of the Edit", "Roy Thompson & Christopher Bowen", "Editing", B, ""),
    ("The Non-Designer's Design Book", "Robin Williams", "Editing", B, ""),
    ("Steal Like an Artist", "Austin Kleon", "Editing", B, ""),
    ("Show Your Work!", "Austin Kleon", "Editing", B, ""),
    ("The Creative Act", "Rick Rubin", "Editing", B, ""),
    ("$100M Offers", "Alex Hormozi", "Business", B, ""),
    ("$100M Leads", "Alex Hormozi", "Business", B, ""),
    ("The Psychology of Money", "Morgan Housel", "Business", B, ""),
    ("Rich Dad Poor Dad", "Robert Kiyosaki", "Business", B, ""),
    ("The Millionaire Next Door", "Thomas Stanley & William Danko", "Business", B, ""),
    ("Zero to One", "Peter Thiel", "Business", B, ""),
    ("The Lean Startup", "Eric Ries", "Business", B, ""),
    ("The 4-Hour Workweek", "Tim Ferriss", "Business", B, ""),
    ("Shoe Dog", "Phil Knight", "Business", B, ""),
    ("The Everything Store", "Brad Stone", "Business", B, ""),
    ("Atomic Habits", "James Clear", "Mind", B, ""),
    ("Deep Work", "Cal Newport", "Mind", B, ""),
    ("Can't Hurt Me", "David Goggins", "Mind", B, ""),
    ("The War of Art", "Steven Pressfield", "Mind", B, ""),
    ("Ego Is the Enemy", "Ryan Holiday", "Mind", B, ""),
    ("The Obstacle Is the Way", "Ryan Holiday", "Mind", B, ""),
    ("Thinking, Fast and Slow", "Daniel Kahneman", "Mind", B, ""),
    ("Range", "David Epstein", "Mind", B, ""),
    ("Mindset", "Carol Dweck", "Mind", B, ""),
    ("Four Thousand Weeks", "Oliver Burkeman", "Mind", B, ""),
]
assert len(BOOKS) == 100


class BookError(Exception):
    pass


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]


def _progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _save_progress(data: dict) -> None:
    PROGRESS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def book(n: int) -> dict:
    if not 1 <= n <= len(BOOKS):
        raise BookError("No such book.")
    title, author, cat, kind, extra = BOOKS[n - 1]
    s = slug(title)
    txt = BOOKS_DIR / f"{n:03d}-{s}.txt"
    epub = BOOKS_DIR / f"{n:03d}-{s}.epub"
    q = urllib.parse.quote_plus(f"{title} {author}")
    links = {"openlibrary": f"https://openlibrary.org/search?q={q}"}
    if kind == L:
        links["site"] = extra
    if kind == B:
        links["buy"] = f"https://www.google.com/search?tbm=bks&q={q}"
    return {"n": n, "title": title, "author": author, "category": cat, "kind": kind,
            "downloaded": txt.exists(), "has_epub": epub.exists(), "txt": txt, "epub": epub,
            "search": extra if kind == G else "", "links": links}


def library() -> dict:
    prog = _progress()
    out = []
    for n in range(1, len(BOOKS) + 1):
        b = book(n)
        p = prog.get(str(n), {})
        pages = 0
        if b["downloaded"]:
            pages = max(1, -(-b["txt"].stat().st_size // PAGE_CHARS))
        out.append({k: v for k, v in b.items() if k not in ("txt", "epub", "search")} |
                   {"status": p.get("status", "todo"), "page": p.get("page", 0), "pages": pages,
                    "finished": p.get("finished")})
    done = sum(1 for b in out if b["status"] == "done")
    return {"books": out, "done": done, "reading": sum(1 for b in out if b["status"] == "reading"),
            "downloaded": sum(1 for b in out if b["downloaded"]), "free": sum(1 for b in out if b["kind"] == G),
            "job": dict(_job)}


def set_status(n: int, status: str) -> dict:
    if status not in ("todo", "reading", "done"):
        raise BookError("Unknown status.")
    book(n)
    prog = _progress()
    p = prog.setdefault(str(n), {})
    p["status"] = status
    p["finished"] = datetime.now(timezone.utc).isoformat() if status == "done" else None
    _save_progress(prog)
    return library()


# ---------- downloading (Project Gutenberg via Gutendex) ----------

def _get(url: str, **kw) -> requests.Response:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30, **kw)
    r.raise_for_status()
    return r


GUTENBERG = "https://www.gutenberg.org"


def _gutendex(search: str) -> list[dict]:
    """Gutendex is a free catalogue that is sometimes down (503) - try it twice."""
    for attempt in range(2):
        try:
            return _get(GUTENDEX, params={"search": search, "languages": "en"}).json().get("results") or []
        except requests.RequestException:
            if attempt == 0:
                time.sleep(3)
    raise BookError("Gutendex is down")


def _gutenberg_search(search: str, author: str) -> Optional[dict]:
    """Backup: Project Gutenberg's own search feed, then its standard download links."""
    import feedparser

    feed = feedparser.parse(_get(f"{GUTENBERG}/ebooks/search.opds/", params={"query": search}).content)
    last = author.split()[-1].lower()
    hits = []
    for e in feed.entries:
        ids = [m.group(1) for l in e.get("links", []) for m in [re.search(r"/ebooks/(\d+)", l.get("href", ""))] if m]
        if not ids:
            continue
        text = " ".join(str(e.get(k, "")) for k in ("title", "author", "summary", "content")).lower()
        hits.append((last in text, int(ids[0]), e.get("title", "")))
    if not hits:
        return None
    hits.sort(key=lambda h: not h[0])  # right author first, keep Gutenberg's order otherwise
    num = hits[0][1]
    return {"id": num, "title": hits[0][2], "formats": {
        "text/plain; charset=utf-8": f"{GUTENBERG}/ebooks/{num}.txt.utf-8",
        "application/epub+zip": f"{GUTENBERG}/ebooks/{num}.epub3.images"}}


def find_gutenberg(search: str, author: str) -> Optional[dict]:
    try:
        results = _gutendex(search)
    except BookError:
        return _gutenberg_search(search, author)
    last = author.split()[-1].lower()
    for r in results:  # prefer the right author
        if any(last in (a.get("name") or "").lower() for a in r.get("authors", [])):
            return r
    return results[0] if results else None


def _strip_gutenberg(text: str) -> str:
    """Cuts the Project Gutenberg licence header/footer, keeps the book."""
    start = re.search(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", text, re.I)
    end = re.search(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG", text, re.I)
    body = text[start.end() if start else 0: end.start() if end else len(text)]
    return body.strip() + "\n\n(From Project Gutenberg - www.gutenberg.org - free to read and share.)\n"


def download(n: int) -> dict:
    b = book(n)
    if b["kind"] != G:
        raise BookError("This book isn't free to download - use the links.")
    if b["downloaded"]:
        return {"n": n, "already": True}
    found = find_gutenberg(b["search"], b["author"])
    if not found:
        raise BookError(f"Not found on Project Gutenberg: {b['title']}")
    formats = found.get("formats") or {}
    txt_url = next((u for k, u in formats.items() if k.startswith("text/plain") and not u.endswith(".zip")), None)
    epub_url = formats.get("application/epub+zip")
    if not txt_url and not epub_url:
        raise BookError("Project Gutenberg has no text version of this one.")
    BOOKS_DIR.mkdir(exist_ok=True)
    if epub_url:
        b["epub"].write_bytes(_get(epub_url).content)
    if txt_url:
        resp = _get(txt_url)
        resp.encoding = resp.encoding or "utf-8"
        b["txt"].write_text(_strip_gutenberg(resp.text), encoding="utf-8")
    return {"n": n, "gutenberg_id": found.get("id"), "title": found.get("title")}


_job = {"status": "idle", "message": "", "failed": []}
_lock = threading.Lock()


def download_all() -> bool:
    with _lock:
        if _job["status"] == "running":
            return False
        _job.update(status="running", message="Starting...", failed=[])

    def run():
        todo = [n for n in range(1, len(BOOKS) + 1) if BOOKS[n - 1][3] == G and not book(n)["downloaded"]]
        for i, n in enumerate(todo, 1):
            _job["message"] = f"Downloading {i}/{len(todo)}: {BOOKS[n - 1][0]}"
            try:
                download(n)
            except Exception as exc:
                _job["failed"].append(f"{BOOKS[n - 1][0]} ({exc})")
            time.sleep(1.5)  # be polite to Project Gutenberg
        _job.update(status="done", message=f"Done - {len(todo) - len(_job['failed'])} downloaded.")
    threading.Thread(target=run, daemon=True).start()
    return True


# ---------- reading ----------

def read_page(n: int, page: Optional[int] = None) -> dict:
    b = book(n)
    if not b["downloaded"]:
        raise BookError("Download the book first.")
    text = b["txt"].read_text(encoding="utf-8", errors="replace")
    pages = max(1, -(-len(text) // PAGE_CHARS))
    prog = _progress()
    p = prog.setdefault(str(n), {})
    if page is None:
        page = p.get("page", 0)
    page = max(0, min(int(page), pages - 1))
    start = page * PAGE_CHARS
    # move the cut to the next paragraph so pages don't start mid-sentence
    if page:
        nl = text.find("\n\n", start)
        start = nl + 2 if 0 <= nl - start < 600 else start
    end = (page + 1) * PAGE_CHARS
    nl = text.find("\n\n", end)
    end = nl if 0 <= nl - end < 600 else end
    p["page"] = page
    if p.get("status", "todo") == "todo":
        p["status"] = "reading"
    _save_progress(prog)
    return {"n": n, "title": b["title"], "author": b["author"], "page": page, "pages": pages,
            "text": text[start:end].strip(), "status": p["status"]}
