"""The "text post" layout: the video on top, a short story about it underneath (the news / explainer page look).

The AI writes 2-3 short paragraphs about what happens in the clip and marks the key phrases with **stars**
(they're shown bold and blue). Without an AI, the title and the clip's best sentence are used.
The last line is a call to action, e.g. "Follow **Paper Trail** for more" (the starred part is bold).
"""
from __future__ import annotations

import json
import re

import styles
import translate

PROMPT = """You write the text shown under a short vertical video ({what}) on Instagram Reels, TikTok and \
YouTube Shorts, the way viral news and explainer pages do: the video plays on top, your text sits below it.

What is said in the clip:
\"\"\"{text}\"\"\"
The clip's title: {title}

Write 2 or 3 short paragraphs, 40 to 65 words in total, in simple spoken {lang}: what happens and why it's \
surprising, funny or important. The first sentence must hook the reader. Mark the 4 to 7 most important phrases \
(2 to 5 words each: names, numbers, the shocking part) with **double stars**. Only use facts from the clip, \
no hashtags, no emojis.{extra}
Answer ONLY with JSON: {{"paragraphs": ["...", "..."]}}"""


def write(brain, clip_text: str, title: str, kind: str = "", lang: str = "", extra: str = "") -> list[str] | None:
    """2-3 paragraphs with **key phrases**, or None when there's no AI or it gave nothing usable."""
    if brain is None or not clip_text.strip():
        return None
    what = {"stream": "a live stream clip", "podcast": "a podcast clip"}.get(kind, "a video clip")
    try:
        raw, _who = brain.ask(PROMPT.format(what=what, text=clip_text[:2500], title=title,
                                            lang=translate.LANGS.get(lang, "English"), extra=extra))
        m = re.search(r"\{.*\}", raw or "", re.S)
        data = json.loads(m.group(0)) if m else {}
    except Exception:
        return None
    paras = [re.sub(r"\s+", " ", str(p)).strip() for p in (data.get("paragraphs") if isinstance(data, dict) else None) or []]
    paras = [p[:400] for p in paras if p][:3]
    if not paras or sum(len(p.split()) for p in paras) < 12:
        return None
    return [p if "**" in p else auto_mark(p) for p in paras]


def auto_mark(text: str) -> str:
    """Stars around names, numbers and strong words when the AI didn't mark anything."""
    words = text.split()
    out, marked = [], 0
    for i, w in enumerate(words):
        bare = re.sub(r"[^\w$%']", "", w)
        name = bare[:1].isupper() and i > 0 and not words[i - 1].endswith((".", "!", "?")) and bare.lower() not in styles.SMALL
        if marked < 5 and bare and (styles.strong(w) or name):
            core = re.match(r"^([\"\u201c(]*)(.*?)([.,!?;:\"\u201d)]*)$", w)
            out.append(f"{core.group(1)}**{core.group(2)}**{core.group(3)}")
            marked += 1
        else:
            out.append(w)
    return re.sub(r"\*\* \*\*", " ", " ".join(out))  # neighbours become one phrase


def fallback(clip_text: str, title: str) -> list[str]:
    """No AI: the title, then the clip's most quotable sentence."""
    t = title.strip()
    paras = [auto_mark(t if t.endswith((".", "!", "?")) else t + ".")] if t else []
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clip_text) if 6 <= len(s.split()) <= 30]
    if sentences:
        best = max(sentences[:8], key=lambda s: sum(styles.strong(w) for w in s.split()) * 3 + min(len(s.split()), 20))
        paras.append(f"“{best}”")
    elif clip_text.strip():
        paras.append("“" + " ".join(clip_text.split()[:30]) + "...”")
    return paras or ["Watch this."]


def cta(custom: str, channel_name: str) -> str:
    if custom.strip():
        return custom.strip()[:140]
    return f"Follow **{channel_name}** for more clips like this." if channel_name else "Follow for more clips like this."
