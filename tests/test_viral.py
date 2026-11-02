"""viral.py: measuring a video, explaining its formula, and writing an original version (all faked)."""
import json

import pytest

import viral


def W(text, start=0.0, step=0.3):
    out, t = [], start
    for w in text.split():
        out.append({"word": w, "start": round(t, 2), "end": round(t + step, 2)})
        t += step + 0.05
    return out


class FakeWriter:
    def __init__(self, answers):
        self.answers, self.prompts = list(answers), []

    def _call_model(self, prompt, max_tokens):
        self.prompts.append(prompt)
        return self.answers.pop(0)


FORMULA = {"hook_type": "shocking claim", "hook_why": "It promises something impossible.", "structure": ["0-3s claim", "who", "twist"],
           "retention_tricks": ["numbers on screen", "short sentences"], "ending_type": "loop", "why_viral": "Short and surprising.",
           "title_pattern": "The Man Who ___ … Twice", "best_for": "true stories"}

STORY = {"title": "The Man Who Sold the Moon", "description": "D", "tags": ["a", "b"], "pinned": "Q?",
         "scenes": [{"say": f"Line {i}.", "cap": f"LINE {i}.", "pages": ["Moon"], "want": ["moon"],
                     "fx": {"type": "big", "text": "1969", "sub": "the year"} if i == 2 else None} for i in range(1, 9)]}


def test_measure_hook_speed_and_loop():
    words = W("This man sold the Eiffel Tower. Then he did it again. And that is why this man")
    st = viral.measure(words, cuts=[1.0, 2.0, 3.0], duration=8.0, width=1080, height=1920)
    assert st["short"] and st["cuts"] == 3 and st["sec_per_cut"] == 2.0
    assert st["hook_3s"].startswith("This man sold")
    assert st["first_sentence"] == "This man sold the Eiffel Tower."
    assert st["loop_guess"] is True
    assert st["words_per_sec"] == round(len(words) / 8.0, 2)


def test_bad_link():
    with pytest.raises(viral.ViralError):
        viral.start_analyze("hello")


def test_analyze_and_make_version(tmp_path, monkeypatch):
    monkeypatch.setattr(viral, "DATA_DIR", tmp_path / "viral")
    monkeypatch.setattr(viral, "STORIES_DIR", tmp_path / "stories")
    monkeypatch.setattr(viral, "_download", lambda url, folder, p: (folder / "v.mp4", {"title": "Viral one", "view_count": 2_000_000, "duration": 30, "width": 1080, "height": 1920}))
    monkeypatch.setattr(viral, "_transcribe", lambda video, p: W("Would you do this? Nobody did. Until one man tried it and lost everything because"))
    import style_analyzer
    monkeypatch.setattr(style_analyzer, "detect_cuts", lambda v: [float(i) for i in range(1, 12)])
    w = FakeWriter([json.dumps(FORMULA)])
    a = viral.analyze("https://youtube.com/shorts/abcDEF123", writer=w)
    assert a["id"] == "abcDEF123" and a["formula"]["hook_type"] == "shocking claim"
    assert "Would you do this?" in w.prompts[0] and "2000000" in w.prompts[0]
    assert viral.history()[0]["id"] == "abcDEF123"

    built = []
    w2 = FakeWriter(["Sure! " + json.dumps(STORY) + " hope it helps"])
    r = viral.make_version("abcDEF123", "The man who sold the moon", "Paper Trail", writer=w2, build=lambda p: built.append(p))
    prompt = w2.prompts[0]
    assert "never copy" in prompt and "shocking claim" in prompt and "The man who sold the moon" in prompt
    story = json.loads(built[0].read_text())
    assert story["channel"] == "Paper Trail" and story["brand"] == "PAPER TRAIL"
    assert story["upload"]["title"].endswith("#shorts") and story["tail"] == 0.25  # loop ending -> short tail
    assert len(story["scenes"]) == 8 and story["scenes"][1]["fx"] == {"type": "big", "text": "1969", "sub": "THE YEAR", "size": 250}
    assert "fx" not in story["scenes"][0] and story["scenes"][0]["img"]["pages"] == ["Moon"]
    assert r["slug"] == story["slug"]


def test_version_needs_topic_and_good_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(viral, "STORIES_DIR", tmp_path)
    a = {"formula": FORMULA, "stats": {"duration": 30, "short": True, "words_per_sec": 3, "sec_per_cut": 3}}
    with pytest.raises(viral.ViralError, match="topic"):
        viral.write_story(a, "", "Paper Trail", writer=FakeWriter([]))
    with pytest.raises(viral.ViralError, match="format"):
        viral.write_story(a, "Enron", "Paper Trail", writer=FakeWriter(["no json here"]))
    with pytest.raises(viral.ViralError, match="too few"):
        viral.write_story(a, "Enron", "Paper Trail", writer=FakeWriter([json.dumps({"scenes": [{"say": "one"}]})]))
