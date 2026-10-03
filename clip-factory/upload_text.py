"""Upload text for every clip: title, description and tags, ready to paste
into YouTube / TikTok / Instagram.

The description always credits where the clip came from (the show, its
@handle and a link to the full video, when the video was downloaded with
Clip Factory) - good practice, and it helps with YouTube's "reused
content" rule. An AI (ai.Brain) writes the hook line and picks the tags;
without one, a built-in writer does it from the clip's own words. Both are
cleaned by the YouTube rules check (no swear words).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Optional

import policy

STOP = set("""a about above after again against all am an and any are aren't as at be because been before being below
between both but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each few for
from further get got had hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself him
himself his how how's i i'd i'll i'm i've if in into is isn't it it's its itself just know let's like me more most
mustn't my myself no nor not now of off on once only or other ought our ours ourselves out over own really right same
say said she she'd she'll she's should shouldn't so some such than that that's the their theirs them themselves then
there there's these they they'd they'll they're they've thing things think this those through to too under until up
very was wasn't we we'd we'll we're we've were weren't what what's when when's where where's which while who who's
whom why why's will with won't would wouldn't yeah yes you you'd you'll you're you've your yours yourself yourselves
gonna wanna okay going want one two lot kind sort mean actually literally basically something anything everything
people time way back even still also well much many make made go goes went come came see look take thing""".split())

MAX_TAGS_CHARS = 450  # YouTube allows 500 characters of tags in total


def source_for(video: Path) -> dict:
    """What Clip Factory knows about where this video came from (saved next to it when downloaded)."""
    side = video.with_name(video.name + ".source.json")
    try:
        data = json.loads(side.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_source(video: Path, info: dict) -> None:
    data = {
        "title": info.get("title") or "",
        "channel": info.get("channel") or info.get("uploader") or "",
        "handle": info.get("uploader_id") if str(info.get("uploader_id") or "").startswith("@") else "",
        "url": info.get("webpage_url") or info.get("original_url") or "",
    }
    video.with_name(video.name + ".source.json").write_text(json.dumps(data, indent=1), encoding="utf-8")


def _hashtag(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)
    return "".join(w[:1].upper() + w[1:] for w in words)[:30]


def _clean_tags(tags: list[str]) -> list[str]:
    out, seen, total = [], set(), 0
    for t in tags:
        t = re.sub(r"[^\w\s'-]", "", str(t)).strip().lower()
        t = re.sub(r"\s+", " ", t)
        if not t or t in seen or len(t) > 40 or policy.swear_strength(t.split()[0]) or any(policy.swear_strength(w) for w in t.split()):
            continue
        if total + len(t) + 2 > MAX_TAGS_CHARS:
            break
        seen.add(t)
        out.append(t)
        total += len(t) + 2
    return out


def _clean_line(text: str) -> str:
    # swear words are left out completely - YouTube can treat "f***" in a description as swearing too
    text = " ".join(w for w in str(text).split() if not policy.swear_strength(w))
    return re.sub(r"\s+", " ", text).strip()[:300]


def keywords(text: str, n: int = 6, title: str = "") -> list[str]:
    """Search tags from the clip itself: the title's words first, then names
    (Capitalised words in mid-sentence), then words said more than once."""
    out: list[str] = []

    def add(w):
        w = w.lower().strip("'-")
        if len(w) > 3 and w not in STOP and not policy.swear_strength(w) and w not in out:
            out.append(w)

    for w in re.findall(r"[A-Za-z][A-Za-z'-]+", title):
        add(w)
    for w, _ in Counter(re.findall(r"(?<=[a-z,]\s)[A-Z][a-z]{2,}\b", text)).most_common(4):
        add(w)
    counts = Counter(w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", text))
    for w, c in counts.most_common(30):
        if c >= 2:
            add(w)
    if title and len(title.split()) <= 6:
        out.insert(0, title.lower())
    return out[:n]


def base_tags(source: dict, kind: str) -> list[str]:
    tags = ["shorts"]
    if kind == "podcast":
        tags += ["podcast", "podcast clips"]
    elif kind == "stream":
        tags += ["stream highlights", "streamer clips"]
    if source.get("channel"):
        tags += [source["channel"].lower(), f"{source['channel'].lower()} clips"]
    return tags


def compose(clip: dict, hook: str, tags: list[str], hashtags: list[str], source: dict, kind: str, channel_name: str = "") -> dict:
    lines = [_clean_line(hook) or clip["title"]]
    credit = []
    if source.get("channel"):
        credit.append(f"From: {source['channel']}" + (f" ({source['handle']})" if source.get("handle") else ""))
    if source.get("url"):
        credit.append(f"Full video: {source['url']}")
    if credit:
        lines += ["", *credit]
    lines += ["", f"Subscribe to {channel_name} for more clips every day." if channel_name else "Subscribe for more clips every day."]
    tags_all = _clean_tags(list(tags) + base_tags(source, kind))
    tags_all = tags_all[:15]
    hs = []
    for h in ["Shorts"] + (["Podcast"] if kind == "podcast" else ["StreamHighlights"] if kind == "stream" else []) + ([_hashtag(source["channel"])] if source.get("channel") else []) + list(hashtags):
        h = _hashtag(h)
        if h and h.lower() not in {x.lower() for x in hs} and not policy.swear_strength(h):
            hs.append(h)
    hs = hs[:5]  # a few hashtags work best; YouTube ignores all of them past 60
    lines += ["", " ".join("#" + h for h in hs)]
    return {"title": clip["title"], "description": "\n".join(lines).strip(), "tags": tags_all, "hashtags": hs}


def fallback(clip: dict, source: dict, kind: str, channel_name: str = "") -> dict:
    first = re.split(r"(?<=[.!?])\s+", clip["text"].strip(), maxsplit=1)[0]
    hook = first if len(first) <= 160 else first[:157].rsplit(" ", 1)[0] + "..."
    kw = keywords(clip["text"], 6, clip["title"])
    out = compose(clip, hook, kw, [k for k in kw if " " not in k][:2], source, kind, channel_name)
    out["by"] = "built-in"
    return out


PROMPT = """You write YouTube Shorts / TikTok upload text for short clips{about}.
For EACH clip below write:
- "hook": one punchy sentence for the top of the description that makes people want to watch (no swear words, no clickbait lies, max 150 characters)
- "tags": 6-10 search tags (short lowercase phrases people would search for; names of people and topics in the clip)
- "hashtags": 2-3 hashtags without the # sign

Answer ONLY with JSON in exactly this shape, one entry per clip id:
{{"clips": [{{"id": 1, "hook": "...", "tags": ["...", "..."], "hashtags": ["...", "..."]}}]}}

Clips:
{clips}
"""


def ai_batch(brain, clips: list[dict], source: dict, kind: str, channel_name: str = "") -> dict[int, dict]:
    """{clip n: upload text} for the clips the AI answered well; the rest are left out (use fallback)."""
    if brain is None or not clips:
        return {}
    local = {i: c for i, c in enumerate(clips, start=1)}
    about = ""
    if source.get("channel"):
        about = f' from "{source.get("title") or "a video"}" by {source["channel"]}'
    elif kind == "podcast":
        about = " from a podcast"
    elif kind == "stream":
        about = " from a live stream"
    listing = "\n\n".join(f'Clip {i} - title "{c["title"]}":\n{c["text"][:1200]}' for i, c in local.items())
    out: dict[int, dict] = {}
    for _ in range(3):
        missing = {i: c for i, c in local.items() if c["n"] not in out}
        if not missing:
            break
        try:
            raw, who = brain.ask(PROMPT.format(about=about, clips=listing if len(missing) == len(local) else
                                               "\n\n".join(f'Clip {i} - title "{c["title"]}":\n{c["text"][:1200]}' for i, c in missing.items())))
        except Exception:
            break
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            m = re.search(r"\{.*\}", raw or "", re.S)
            try:
                data = json.loads(m.group(0)) if m else {}
            except json.JSONDecodeError:
                data = {}
        for item in (data.get("clips") if isinstance(data, dict) else None) or []:
            if not isinstance(item, dict):
                continue
            try:
                i = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            c = missing.get(i)
            hook = str(item.get("hook") or "").strip()
            tags = [str(t) for t in item.get("tags") or [] if str(t).strip()]
            if not c or not hook or len(tags) < 3:
                continue
            text = compose(c, hook, tags, [str(h) for h in item.get("hashtags") or []], source, kind, channel_name)
            text["by"] = who
            out[c["n"]] = text
    return out


def as_text(upload: dict) -> str:
    """One clip's upload text as a plain .txt (for the zip)."""
    tags = ", ".join(upload.get("tags") or [])
    hashtags = " ".join("#" + h for h in upload.get("hashtags") or [])
    return (f"TITLE:\n{upload.get('title', '')}\n\nDESCRIPTION:\n{upload.get('description', '')}\n\n"
            f"TAGS (paste into YouTube's Tags box):\n{tags}\n\n"
            f"HASHTAGS (Instagram allows 5 at most):\n{hashtags}\n")
