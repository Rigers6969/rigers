"""Can I clip this channel? - the AI reads what a show says publicly and
finds its clipping rules.

For each channel it reads:
  - the channel's own description (YouTube "About")
  - the full descriptions of its 3 latest videos (where shows usually link
    their clipping program, or say "no reuploads")
then an AI (ai.Brain - Gemini/Groq/.../Ollama) gives a verdict:
  allowed      - the show invites clippers / runs a clipping program
  not_allowed  - the show says not to reupload / will claim
  unclear      - nothing public either way (ask the show before clipping)

Every quote the AI gives as evidence is checked word for word against the
real text - an "allowed" without real proof is downgraded to "unclear",
so it never invents permission. Results are kept for 7 days.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Callable, Optional

import requests

import trends

APP_DIR = Path(__file__).resolve().parent
CACHE_FILE = APP_DIR / "permissions.json"
CACHE_DAYS = 7
VERDICTS = ("allowed", "not_allowed", "unclear")

POSITIVE = re.compile(
    r"clipp(?:ing|ers?)\b|clip (?:our|my|this|the) (?:content|videos?|podcast|show|streams?)|clips? (?:and|&) (?:earn|get paid)|"
    r"get paid (?:to|for) clip|feel free to (?:clip|use|share)|you (?:can|may|are welcome to) (?:clip|use)|"
    r"whop\.com|vyro|content ?rewards|clipfarm|clipify|creator program|clipping program", re.I)
NEGATIVE = re.compile(
    r"do not (?:re-?upload|repost|use|copy)|don'?t (?:re-?upload|repost|steal)|no re-?uploads?|all rights reserved|"
    r"unauthori[sz]ed (?:use|reproduction|upload)|copyright (?:claims?|strikes?|protected)|content ?id|"
    r"without (?:our |my )?(?:prior |written |express )?permission|(?:will|may) be (?:claimed|removed|taken down)", re.I)
URL = re.compile(r"https?://[^\s\"'<>)]+")

PROMPT = """You check whether a YouTube channel allows other people to post clips of its videos (a "clipping program" or clipping permission).
Below is everything the channel says publicly: its channel description and the descriptions of its latest videos.

{text}

Decide:
- "allowed" ONLY if the text clearly invites clippers or links a clipping program.
- "not_allowed" if it clearly says not to reupload/repost, or warns about copyright claims on reuploads.
- "unclear" if it doesn't say either way. Unclear is the right answer when in doubt - never guess "allowed".
Answer ONLY with JSON in exactly this shape:
{{"verdict": "allowed", "summary": "one short sentence for a beginner", "evidence": ["exact sentence copied from the text above"], "join_link": "the clipping program link from the text, or empty", "conditions": ["rules the show sets for clippers, e.g. tag the show, no full episodes"]}}"""


def _key(name: str) -> str:
    return trends.channel_url(name).lower()


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def cached(name: str) -> Optional[dict]:
    hit = _load_cache().get(_key(name))
    if hit and time.time() - hit.get("checked_at", 0) < CACHE_DAYS * 86400:
        return hit
    return None


def _save(result: dict) -> None:
    cache = _load_cache()
    cache[_key(result["name"])] = result
    CACHE_FILE.write_text(json.dumps(cache, indent=1), encoding="utf-8")


def _video_description(video_id: str) -> str:
    """The full description from the watch page (the channel list only has a snippet)."""
    resp = requests.get(
        f"https://www.youtube.com/watch?v={video_id}", timeout=20,
        headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"},
        cookies={"SOCS": "CAI", "CONSENT": "YES+"},  # skips the cookie-consent page in some countries
    )
    resp.raise_for_status()
    m = re.search(r'"shortDescription":("(?:[^"\\]|\\.)*")', resp.text)
    return json.loads(m.group(1)) if m else ""


def gather(name: str) -> dict:
    """{'channel', 'about', 'videos': [{title, description}]} - raises on a channel that doesn't exist."""
    base = trends.channel_url(name)
    with trends._ydl_flat(5) as ydl:
        info = ydl.extract_info(f"{base}/videos", download=False) or {}
    videos = []
    for e in (info.get("entries") or [])[:3]:
        if not isinstance(e, dict) or not e.get("id"):
            continue
        try:
            desc = _video_description(e["id"])
        except Exception:
            desc = e.get("description") or ""
        videos.append({"title": e.get("title") or "", "description": desc})
    return {"channel": info.get("channel") or info.get("uploader") or name, "about": info.get("description") or "", "videos": videos}


def _sentences(text: str, pattern: re.Pattern) -> list[str]:
    out = []
    for part in re.split(r"(?<=[.!?])\s+|\n+", text):
        part = part.strip()
        if part and pattern.search(part) and part not in out:
            out.append(part[:300])
    return out


def _all_text(data: dict) -> str:
    parts = [f"CHANNEL DESCRIPTION:\n{data['about'] or '(empty)'}"]
    for i, v in enumerate(data["videos"], start=1):
        parts.append(f"LATEST VIDEO {i} - {v['title']}:\n{v['description'] or '(empty)'}")
    return "\n\n".join(parts)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def rule_based(data: dict) -> dict:
    text = _all_text(data)
    pos, neg = _sentences(text, POSITIVE), _sentences(text, NEGATIVE)
    links = [u for s in pos for u in URL.findall(s)]
    if pos and not neg:
        verdict = "allowed"
        summary = "The channel mentions clipping or a clipping program - read the quote below to be sure."
    elif neg and not pos:
        verdict = "not_allowed"
        summary = "The channel warns against reuploads or copyright use."
    elif pos and neg:
        verdict = "unclear"
        summary = "The channel mentions clipping but also copyright warnings - read both quotes."
    else:
        verdict = "unclear"
        summary = "The channel doesn't say anything about clipping. Ask the show before clipping it."
    return {"verdict": verdict, "summary": summary, "evidence": (pos + neg)[:4], "join_link": links[0] if links else "",
            "conditions": [], "by": "built-in check"}


def ai_verdict(data: dict, brain) -> Optional[dict]:
    text = _all_text(data)
    norm_text = _norm(text)
    for _ in range(3):
        try:
            raw, who = brain.ask(PROMPT.format(text=text[:12000]))
        except Exception:
            return None
        try:
            d = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            m = re.search(r"\{.*\}", raw or "", re.S)
            try:
                d = json.loads(m.group(0)) if m else None
            except json.JSONDecodeError:
                d = None
        if not isinstance(d, dict) or d.get("verdict") not in VERDICTS:
            continue
        # only quotes that really appear in the channel's text count as evidence
        evidence = [str(q).strip()[:300] for q in d.get("evidence") or []
                    if str(q).strip() and _norm(str(q).strip(" \"'")) in norm_text]
        link = str(d.get("join_link") or "").strip()
        if link and link.lower() not in text.lower():
            link = ""
        verdict = d["verdict"]
        summary = str(d.get("summary") or "")[:300]
        if verdict == "allowed" and not evidence:
            verdict = "unclear"
            summary = "The AI thought clipping is allowed but couldn't quote proof, so treat it as unclear."
        return {"verdict": verdict, "summary": summary, "evidence": evidence[:4], "join_link": link,
                "conditions": [str(c)[:200] for c in d.get("conditions") or []][:5], "by": who}
    return None


def check(name: str, brain=None, force: bool = False) -> dict:
    if not force:
        hit = cached(name)
        if hit:
            return hit
    try:
        data = gather(name)
    except Exception as exc:
        return {"name": name, "verdict": "error", "summary": f"Couldn't read this channel: {trends.clean_error(exc)}",
                "evidence": [], "join_link": "", "conditions": [], "by": "", "checked_at": time.time()}
    result = (ai_verdict(data, brain) if brain is not None else None) or rule_based(data)
    result.update(name=name, channel=data["channel"], checked_at=time.time(),
                  checked_on=time.strftime("%Y-%m-%d"), url=trends.channel_url(name))
    _save(result)
    return result


def check_many(names: list[str], brain=None, force: bool = False,
               progress: Optional[Callable[[str], None]] = None) -> dict:
    out = {}
    for i, name in enumerate(names, start=1):
        if progress:
            progress(f"Reading {name}'s clipping rules ({i} of {len(names)})...")
        out[_key(name)] = check(name, brain, force)
    return out


def all_cached() -> dict:
    now = time.time()
    return {k: v for k, v in _load_cache().items() if now - v.get("checked_at", 0) < CACHE_DAYS * 86400}
