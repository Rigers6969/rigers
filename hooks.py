"""Hook engine: gives every script a strong first 15 seconds.

The AI writes several different openings for the video; each is scored with
simple rules that match what keeps viewers (a number or a name, an open
question, stakes, short sentences, no "welcome back" filler) and the best one
replaces the script's own first paragraph. The other options are saved in
hooks.json so you can swap one in before publishing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HOOK_PROMPT = """You write the first 15 seconds of a YouTube documentary for the channel "{channel}".
Video topic: {topic}

Here is the start of the script:
---
{opening}
---

Write 5 DIFFERENT opening hooks (each 25-55 words, spoken narration only) that make people keep watching.
Rules:
- Start in the middle of the most dramatic moment, or with a shocking number, or with a question nobody can answer yet.
- Name a real person, company, place or amount from the story.
- Create an open loop: promise something the viewer will only learn later in the video.
- Short sentences. No "In this video", no "Welcome", no "Have you ever wondered", no greetings.
- Only use facts that are in the script. Don't invent numbers.
Answer with JSON only: ["hook 1", "hook 2", "hook 3", "hook 4", "hook 5"]"""

BANNED = ("in this video", "welcome", "have you ever wondered", "today we", "let's dive", "hey guys",
          "before we start", "don't forget to subscribe", "in today's", "buckle up")
LOOP_WORDS = ("but", "until", "nobody", "no one", "secret", "never", "why", "how", "what happened",
              "the truth", "later", "only one", "turned out", "except")
STAKES = ("billion", "million", "prison", "dead", "died", "collapse", "lost", "fraud", "war", "disappeared",
          "never", "everything", "first", "last")


def score_hook(text: str) -> float:
    t = text.lower()
    words = text.split()
    s = 0.0
    n = len(words)
    s += 10 if 25 <= n <= 55 else (4 if 15 <= n <= 70 else -10)
    if re.search(r"\d", text):
        s += 8                                         # a number
    if re.search(r"\b[A-Z][a-z]{2,}", " ".join(words[1:])):
        s += 5                                         # a name (not just the first word)
    if "?" in text:
        s += 5
    s += 3 * min(3, sum(1 for w in LOOP_WORDS if re.search(rf"\b{re.escape(w)}\b", t)))
    s += 2 * min(3, sum(1 for w in STAKES if w in t))
    sentences = [x for x in re.split(r"[.!?]+", text) if x.strip()]
    if sentences and sum(len(x.split()) for x in sentences) / len(sentences) <= 14:
        s += 5                                         # short punchy sentences
    s -= 25 * sum(1 for b in BANNED if b in t)
    return s


def _json_list(raw: str) -> list[str]:
    m = re.search(r"\[.*\]", raw or "", re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return [str(x).strip() for x in data if isinstance(x, str) and x.strip()]


def strip_filler_opening(script: str) -> str:
    """Removes greeting-style first sentences ("Welcome back to the channel...")."""
    sentences = re.split(r"(?<=[.!?])\s+", script.strip())
    while sentences and any(b in sentences[0].lower() for b in BANNED):
        sentences.pop(0)
    return " ".join(sentences)


def improve_opening(writer, topic: str, channel: str, script: str, video_dir: Path | None = None) -> tuple[str, dict]:
    """Returns (new script, report). Falls back to the script with only filler removed."""
    script = strip_filler_opening(script)
    paras = [p for p in re.split(r"\n\s*\n", script) if p.strip()]
    opening = "\n\n".join(paras[:2])[:1500]
    hooks = []
    try:
        hooks = _json_list(writer._call_model(HOOK_PROMPT.format(channel=channel, topic=topic, opening=opening),
                                              max_tokens=900))
    except Exception as exc:  # the video still gets made with its own opening
        report = {"hooks": [], "chosen": None, "error": str(exc)}
        return script, report
    scored = sorted(((score_hook(h), h) for h in hooks), reverse=True)
    report = {"hooks": [{"text": h, "score": round(sc, 1)} for sc, h in scored], "chosen": None}
    if scored and scored[0][0] > score_hook(paras[0] if paras else ""):
        best = scored[0][1]
        report["chosen"] = best
        # the hook replaces the first paragraph; the story continues from paragraph two
        script = best + "\n\n" + "\n\n".join(paras[1:] if len(paras) > 1 else paras)
    if video_dir:
        (video_dir / "hooks.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return script, report
