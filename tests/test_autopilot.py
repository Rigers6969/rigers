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


def test_finds_googles_long_key_name(ap, monkeypatch, tmp_path):
    import json as _j
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    monkeypatch.setattr(autopilot, "APP_DIR", tmp_path / "app")
    monkeypatch.setattr(autopilot, "CLIENT_SECRET", tmp_path / "app" / "client_secret.json")
    (tmp_path / "app").mkdir()
    monkeypatch.setattr(autopilot.Path, "home", staticmethod(lambda: home))
    assert autopilot.find_client_secret() is None
    (home / "Downloads" / "client_secret_123-abc.apps.googleusercontent.com.json.json").write_text(_j.dumps({"installed": {"client_id": "x"}}))
    found = autopilot.find_client_secret()
    assert found == tmp_path / "app" / "client_secret.json" and "installed" in found.read_text()


def test_brief_skips_research_and_steps_move_forward(ap, monkeypatch, tmp_path):
    import producer, researcher, studio_api
    monkeypatch.setattr(producer, "CONTENT_ROOT", tmp_path / "c")
    monkeypatch.setattr(researcher, "research_channel", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no research")))
    monkeypatch.setattr(studio_api, "make_writer", lambda e, d: object())
    seen = {}
    def fake_produce(topic, channel, writer, **kw):
        seen.update(topic=topic, **kw)
        kw["progress"]("Writing script...")
        kw["progress"]("Generating voiceover...")
        d = tmp_path / "c" / "x"; d.mkdir(parents=True)
        (d / "final.mp4").write_bytes(b"x"); (d / "metadata.json").write_text("{}")
        return {"slug": "x", "video_error": None}
    monkeypatch.setattr(producer, "produce_video", fake_produce)
    chan = {**autopilot.load_settings()["channels"][0], "length": "short"}
    autopilot._status["step"] = 0
    autopilot.make_one(chan, autopilot.load_settings(), autopilot.load_state(), autopilot._progress,
                       brief="Enron scandal\nHow they hid billions.")
    assert seen["topic"].startswith("Enron scandal") and seen["length"] == "short"
    labels = [l for _k, l, _w in autopilot.STEPS]
    assert labels[autopilot._status["step"]] == "Record the voice"
    assert autopilot.review_list()[0]["topic"] == "Enron scandal"


def test_all_videos_lists_states(ap, monkeypatch):
    import producer
    root = ap / "content"
    monkeypatch.setattr(producer, "CONTENT_ROOT", root)
    for slug in ("waiting-one", "done-one", "broken-one", "_tmp"):
        (root / slug).mkdir(parents=True)
    (root / "waiting-one" / "final.mp4").write_bytes(b"x")
    (root / "done-one" / "final.mp4").write_bytes(b"x")
    (root / "done-one" / "metadata.json").write_text(json.dumps({"youtube": {"title": "Done video"}}))
    (root / "done-one" / "notes.txt").write_text("History - something\n")
    autopilot._save_state({"log": [{"slug": "done-one", "url": "https://youtu.be/abc", "msg": "Uploaded"}],
                           "review": [{"slug": "waiting-one", "channel": "Paper Trail", "title": "W"}],
                           "channels": {}})
    vids = {v["slug"]: v for v in autopilot.all_videos()}
    assert set(vids) == {"waiting-one", "done-one", "broken-one"}
    assert vids["waiting-one"]["state"] == "review"
    assert vids["done-one"]["state"] == "uploaded" and vids["done-one"]["title"] == "Done video"
    assert vids["done-one"]["channel"] == "History" and vids["done-one"]["url"].endswith("abc")
    assert vids["broken-one"]["state"] == "failed" and not vids["broken-one"]["has_video"]
