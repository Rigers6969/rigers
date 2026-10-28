"""hooks.py scoring/replacing and story_graphics moment finding."""
import json

import hooks
import story_graphics as sg


class FakeWriter:
    def __init__(self, hooks_list):
        self.hooks = hooks_list

    def _call_model(self, prompt, max_tokens=0):
        return json.dumps(self.hooks)


def test_score_prefers_numbers_names_loops_and_punishes_filler():
    good = "In 2001, Enron told the world it was worth $70 billion. Sixteen months later it was gone. But one memo nobody read had already predicted it."
    bad = "Welcome back to the channel! In this video we will talk about a company called Enron and what happened to it."
    assert hooks.score_hook(good) > hooks.score_hook(bad)


def test_best_hook_replaces_first_paragraph(tmp_path):
    script = "Welcome back to the channel. Enron was a company.\\n\\nIt grew fast in the 1990s.\\n\\nThen it fell."
    best = "In 2001, Enron was worth $70 billion. Sixteen months later it was bankrupt. But the warning was there all along."
    w = FakeWriter(["Enron was a company that existed.", best])
    new, report = hooks.improve_opening(w, "Enron", "Paper Trail", script, tmp_path)
    assert new.startswith(best) and "Welcome" not in new and "It grew fast" in new
    assert json.loads((tmp_path / "hooks.json").read_text())["chosen"] == best


def test_moments_money_percent_date_spaced():
    text = "On October 16, 2001, Enron reported a $618 million loss. " + "filler " * 30 + "About 40 percent were gone. " + "filler " * 30 + "In 1985 it began."
    words, t = [], 0.0
    for x in text.split():
        words.append({"word": " " + x, "start": t, "end": t + 0.3}); t += 0.4
    kinds = [m["kind"] for m in sg.find_moments(words)]
    assert kinds == ["money", "percent", "date"]
    money = sg.find_moments(words)[0]
    assert money["text"] == "$618 MILLION" and money["label"].startswith("LOSS")
