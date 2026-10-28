"""autopilot.py: settings, due days, topic picking, the full make-and-upload step (all mocked)."""
import json
from datetime import datetime, timedelta, timezone

import pytest

import autopilot


@pytest.fixture
def ap(tmp_path, monkeypatch):
    for name, fname in (("SETTINGS_FILE", "s.json"), ("STATE_FILE", "st.json")):
        monkeypatch.setattr(autopilot, name, tmp_path / fname)
    monkeypatch.setattr(autopilot, "TOKENS_DIR", tmp_path / "tokens")
    return tmp_path


def test_settings_defaults_and_validation(ap):
    s = autopilot.load_settings()
    assert s["enabled"] is False and s["channels"][0]["name"] == "Paper Trail"
    s = autopilot.save_settings({"enabled": True, "run_time": "03:15", "channels": [{"name": "History", "per_week": 9, "enabled": 1}]})
    assert s["enabled"] and s["run_time"] == "03:15" and s["channels"][0]["per_week"] == 7
    with pytest.raises(autopilot.AutopilotError):
        autopilot.save_settings({"run_time": "25:00"})


def test_due_spacing(ap):
    chan = {"name": "X", "per_week": 2}
    st = {"channels": {}}
    now = datetime(2026, 11, 10, 3)
    assert autopilot.due(chan, st, now)
    st["channels"]["X"] = {"last_made": (now - timedelta(days=2)).isoformat()}
    assert not autopilot.due(chan, st, now)
    st["channels"]["X"]["last_made"] = (now - timedelta(days=4)).isoformat()
    assert autopilot.due(chan, st, now)


def test_publish_time_is_future_utc(ap):
    t = autopilot.publish_time(17, datetime(2026, 11, 10, 18, 0))
    assert t.endswith("Z")
    assert datetime.fromisoformat(t.replace("Z", "+00:00")) > datetime(2026, 11, 10, 18, 0).astimezone(timezone.utc)


def test_make_one_researches_produces_and_uploads(ap, monkeypatch, tmp_path):
    import producer, researcher, publishing, studio_api
    content = tmp_path / "content"
    monkeypatch.setattr(producer, "CONTENT_ROOT", content)
    monkeypatch.setattr(researcher, "load_channels", lambda: [{"name": "Paper Trail", "lang": "en", "searches": [], "subreddits": [], "strong": [], "wiki": False}])
    topics = [{"title": "Old story", "angle": "a"}, {"title": "Acme Ponzi collapse", "angle": "The full story"}]
    monkeypatch.setattr(researcher, "research_channel", lambda *a, **k: {"topics": topics, "failed": []})
    monkeypatch.setattr(studio_api, "make_writer", lambda e, d: object())

    def fake_produce(topic, channel, writer, **kw):
        d = content / "acme"
        d.mkdir(parents=True)
        (d / "final_edited.mp4").write_bytes(b"x")
        (d / "metadata.json").write_text(json.dumps({"youtube": {"title": "The Acme Ponzi", "description": "d", "tags": ["fraud"]}}))
        return {"slug": "acme", "video_error": None}
    monkeypatch.setattr(producer, "produce_video", fake_produce)
    uploads = []
    monkeypatch.setattr(publishing, "upload_to_youtube", lambda path, title, desc, tags, **kw: uploads.append((path.name, title, kw)) or "VID123")

    st = autopilot.load_state()
    st["channels"]["Paper Trail"] = {"used": [autopilot._norm("Old story")]}
    chan = dict(autopilot.load_settings()["channels"][0], publish="schedule")
    autopilot.TOKENS_DIR.mkdir()
    autopilot.token_path("Paper Trail").write_text("{}")
    autopilot.make_one(chan, autopilot.load_settings(), st)
    assert uploads[0][0] == "final_edited.mp4" and uploads[0][1] == "The Acme Ponzi"
    assert uploads[0][2]["publish_at"].endswith("Z")
    st = autopilot.load_state()
    assert st["log"][-1]["url"] == "https://youtu.be/VID123"
    assert autopilot._norm("Acme Ponzi collapse") in st["channels"]["Paper Trail"]["used"]


def test_not_connected_keeps_video_and_says_so(ap, monkeypatch, tmp_path):
    import producer, researcher, studio_api
    monkeypatch.setattr(producer, "CONTENT_ROOT", tmp_path / "c")
    monkeypatch.setattr(researcher, "load_channels", lambda: [{"name": "History", "lang": "en", "searches": [], "subreddits": [], "strong": [], "wiki": True}])
    monkeypatch.setattr(researcher, "research_channel", lambda *a, **k: {"topics": [{"title": "Lost city", "angle": "x"}], "failed": []})
    monkeypatch.setattr(studio_api, "make_writer", lambda e, d: object())
    def fake_produce(*a, **k):
        d = tmp_path / "c" / "lost"; d.mkdir(parents=True)
        (d / "final.mp4").write_bytes(b"x"); (d / "metadata.json").write_text("{}")
        return {"slug": "lost", "video_error": None}
    monkeypatch.setattr(producer, "produce_video", fake_produce)
    st = autopilot.load_state()
    autopilot.make_one({"name": "History", "voice": "en-GB-RyanNeural", "length": "long", "publish": "schedule", "publish_hour": 17}, autopilot.load_settings(), st)
    assert "connect" in autopilot.load_state()["log"][-1]["msg"].lower()


def test_review_waits_for_approve_then_uploads(ap, monkeypatch, tmp_path):
    import producer, researcher, publishing, studio_api
    content = tmp_path / "content"
    monkeypatch.setattr(producer, "CONTENT_ROOT", content)
    monkeypatch.setattr(researcher, "load_channels", lambda: [{"name": "Paper Trail", "lang": "en", "searches": [], "subreddits": [], "strong": [], "wiki": False}])
    monkeypatch.setattr(researcher, "research_channel", lambda *a, **k: {"topics": [{"title": "Acme", "angle": "a"}], "failed": []})
    monkeypatch.setattr(studio_api, "make_writer", lambda e, d: object())
    def fake_produce(*a, **k):
        d = content / "acme"; d.mkdir(parents=True)
        (d / "final.mp4").write_bytes(b"x")
        (d / "metadata.json").write_text(json.dumps({"youtube": {"title": "Acme", "description": "d"}}))
        (d / "hooks.json").write_text(json.dumps({"hooks": [{"text": "h", "score": 1}], "chosen": "h"}))
        return {"slug": "acme", "video_error": None}
    monkeypatch.setattr(producer, "produce_video", fake_produce)
    uploads = []
    monkeypatch.setattr(publishing, "upload_to_youtube", lambda *a, **kw: uploads.append(kw) or "V1")
    chan = autopilot.load_settings()["channels"][0]
    assert chan["publish"] == "review"
    autopilot.make_one(chan, autopilot.load_settings(), autopilot.load_state())
    assert uploads == [] and autopilot.review_list()[0]["chosen_hook"] == "h"
    with pytest.raises(autopilot.AutopilotError):
        autopilot.approve("acme")  # not connected yet
    autopilot.TOKENS_DIR.mkdir()
    autopilot.token_path("Paper Trail").write_text("{}")
    out = autopilot.approve("acme", "Better title")
    assert out["video_id"] == "V1" and uploads[0]["publish_at"].endswith("Z")
    assert autopilot.review_list() == []
