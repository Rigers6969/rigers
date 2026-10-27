"""researcher.py: merging headlines into topics, scoring, failing sources, saved ideas, API."""
from datetime import datetime, timedelta, timezone

import pytest

import researcher


NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)


def item(title, source, hours_ago=2, kind="news", **extra):
    return {"title": title, "source": source, "link": "https://example.com/" + source,
            "snippet": "", "time": (NOW - timedelta(hours=hours_ago)).isoformat(), "kind": kind, **extra}


def test_same_story_from_many_outlets_becomes_one_topic():
    items = [
        item("SEC charges Acme Capital CEO John Smith with $400 million Ponzi scheme", "Reuters"),
        item("Acme Capital founder John Smith accused of Ponzi scheme by SEC", "CNBC"),
        item("Apple unveils new iPhone colors", "The Verge"),
    ]
    groups = researcher.cluster(items)
    assert sorted(len(g) for g in groups) == [1, 2]


def test_score_prefers_many_sources_fresh_and_strong_words():
    strong = ["fraud", "ponzi", "charged"]
    big = [item("Ponzi fraud at Acme Capital", s) for s in ("Reuters", "CNBC", "BBC")]
    small = [item("Quiet quarter for Beta Corp", "Blog", hours_ago=140)]
    assert researcher.score(big, strong, NOW) > researcher.score(small, strong, NOW)


def test_topic_has_lead_title_sources_and_angle():
    group = [item("SEC charges Acme Capital CEO with fraud", "Reuters"),
             item("r/finance thread on Acme", "r/finance", kind="reddit", upvotes=5000)]
    t = researcher.topic_from(group, ["fraud"], NOW)
    assert t["title"].startswith("SEC charges")
    assert t["sources"] == ["Reuters", "r/finance"]
    assert "money moved" in t["angle"]


def test_dead_source_is_listed_and_the_rest_still_works(monkeypatch):
    def news(q, lang="en"):
        if q == "bad":
            raise ConnectionError("down")
        return [item(f"Acme Capital fraud {q}", "Reuters")]
    monkeypatch.setattr(researcher, "google_news", news)
    monkeypatch.setattr(researcher, "reddit_top", lambda s: [])
    ch = {"name": "Paper Trail", "lang": "en", "searches": ["good", "bad"], "subreddits": ["finance"],
          "strong": ["fraud"], "wiki": False}
    out = researcher.research_channel(ch)
    assert out["failed"] == ["Google News: bad (ConnectionError)"]
    assert out["topics"] and out["topics"][0]["title"].startswith("Acme Capital fraud")


def test_channels_and_ideas_are_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(researcher, "CHANNELS_FILE", tmp_path / "ch.json")
    monkeypatch.setattr(researcher, "IDEAS_FILE", tmp_path / "ideas.json")
    assert [c["name"] for c in researcher.load_channels()][0] == "Paper Trail"
    saved = researcher.save_channels([{"name": "Test", "searches": "a, b", "subreddits": "r/x", "lang": "sq"}])
    assert saved[0]["searches"] == ["a", "b"] and saved[0]["subreddits"] == ["x"] and saved[0]["lang"] == "sq"
    assert researcher.load_channels()[0]["name"] == "Test"
    with pytest.raises(researcher.ResearchError):
        researcher.save_channels([{"name": " "}])
    researcher.save_idea("Paper Trail", "Acme fraud", "angle")
    ideas = researcher.update_idea(0, done=True)
    assert ideas[0]["done"] is True
    assert researcher.update_idea(0, delete=True) == []


def test_api_routes(tmp_path, monkeypatch):
    from flask import Flask
    import research_api
    monkeypatch.setattr(researcher, "IDEAS_FILE", tmp_path / "ideas.json")
    monkeypatch.setattr(researcher, "RESULT_FILE", tmp_path / "res.json")
    app = Flask(__name__)
    app.register_blueprint(research_api.bp)
    c = app.test_client()
    assert c.get("/api/research").get_json()["status"] in ("idle", "done", "error", "running")
    r = c.post("/api/research/ideas", json={"channel": "History", "title": "Lost city found"})
    assert r.get_json()["ideas"][0]["title"] == "Lost city found"
    assert c.post("/api/research/ideas", json={"title": ""}).status_code == 400
