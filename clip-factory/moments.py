"""Finding the viral moments in a long video's transcript.

1. Candidates: sentence-aligned windows of MIN..MAX seconds, overlapping,
   covering the whole video - so a clip never starts or ends mid-sentence.
2. Scoring: Ollama rates each candidate's viral potential (1-10) and gives
   it a short hook title. Ollama is forced into strict JSON mode, every
   answer is checked, anything missing or invalid is asked for again, and
   if the model still can't give a usable answer the built-in heuristic
   score is used instead - so a run never fails because of the AI.
3. Picking: highest scores first, never overlapping another picked clip.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

import requests

ProgressCB = Callable[[str], None]

BATCH_SIZE = 8  # candidates per Ollama call - small enough for a small model to do well
MAX_ATTEMPTS = 3

PROMPT = """You are a viral short-form video editor (TikTok, YouTube Shorts, Reels).
Below are {n} candidate clips cut from a longer video.{hint} Rate each one's potential to go viral as a standalone short, from 1 (boring) to 10 (extremely engaging).

A great clip: opens with a hook (a surprising claim, a question, emotion, conflict, a funny moment), makes sense without the rest of the video, and delivers a payoff.
A bad clip: starts mid-thought, is filler, small talk, an intro/outro, or needs earlier context.
Give a LOW score (1-2) to anything that breaks YouTube's rules or kills ad revenue: slurs or hate, sexual content, graphic violence, dangerous acts or challenges, drug use, or harassing a real person.

Titles must be honest about what happens in the clip (no clickbait lies) and must not contain swear words.

For EVERY clip, also write a punchy title of at most 7 words that would make someone stop scrolling.

Answer ONLY with JSON in exactly this shape, one entry per clip id:
{{"clips": [{{"id": 1, "score": 7, "title": "..."}}]}}

Clips:
{clips}
"""

HOOK_WORDS = {
    "secret", "never", "always", "why", "how", "what", "nobody", "everyone", "shocking", "crazy", "insane",
    "money", "million", "billion", "dead", "died", "kill", "war", "love", "hate", "truth", "lie", "mistake",
    "worst", "best", "first", "last", "only", "real", "actually", "imagine", "wait", "stop", "warning",
    "biggest", "dangerous", "illegal", "free", "rich", "poor", "fail", "won", "lost", "fight", "scary",
}


def split_sentences(words: list[dict], max_len: float = 60) -> list[dict]:
    """Groups words into sentences. Whisper sometimes returns long
    stretches with no full stops, so overly long sentences are also broken
    at commas/pauses - otherwise no clip could ever fit between two ends."""
    hard = min(25.0, max_len * 0.5)  # past this it's broken no matter what (speech with no punctuation)
    soft = hard * 0.6               # past this it's also broken at a comma or a pause
    sentences, current = [], []

    def close():
        if current:
            sentences.append({"start": current[0]["start"], "end": current[-1]["end"], "text": " ".join(x["text"] for x in current)})
            current.clear()

    for k, w in enumerate(words):
        current.append(w)
        text = w["text"].rstrip('"\')')
        length = w["end"] - current[0]["start"]
        gap = words[k + 1]["start"] - w["end"] if k + 1 < len(words) else 0.0
        if (text.endswith((".", "!", "?"))
                or (length >= soft and (text.endswith((",", ";", ":")) or gap >= 0.35))
                or length >= hard):
            close()
    close()
    return sentences


def make_candidates(sentences: list[dict], min_s: float, max_s: float) -> list[dict]:
    """Sentence-aligned windows aiming for the middle of min..max. A new
    window starts roughly every third of a window, so good moments are
    rarely split across two candidates."""
    target = (min_s + max_s) / 2
    candidates, i = [], 0
    while i < len(sentences):
        start = sentences[i]["start"]
        j = i
        while j + 1 < len(sentences) and sentences[j + 1]["end"] - start <= max_s and sentences[j]["end"] - start < target:
            j += 1
        duration = sentences[j]["end"] - start
        if min_s <= duration <= max_s:
            candidates.append({
                "first": i, "last": j, "start": start, "end": sentences[j]["end"],
                "text": " ".join(s["text"] for s in sentences[i:j + 1]),
            })
        # the next window starts ~40% of a window later: overlapping, so a good
        # moment is rarely cut in two, without making Ollama read everything 3x
        next_i = i + 1
        while next_i < len(sentences) and sentences[next_i]["start"] - start < target * 0.4:
            next_i += 1
        i = next_i
    for n, c in enumerate(candidates, start=1):
        c["id"] = n
    return candidates


def heuristic_score(text: str) -> float:
    """1-10 from simple signals: hook words, questions, exclamations,
    numbers, and a strong opening line."""
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if not words:
        return 1.0
    hooks = sum(1 for w in words if w in HOOK_WORDS)
    first_sentence = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    score = 3.0
    score += min(3.0, hooks / max(len(words), 1) * 60)
    score += min(1.5, text.count("?") * 0.5)
    score += min(1.0, text.count("!") * 0.5)
    score += min(1.0, len(re.findall(r"\d", text)) * 0.2)
    if first_sentence.endswith("?") or any(w in HOOK_WORDS for w in re.findall(r"[a-z']+", first_sentence.lower())[:6]):
        score += 1.0
    return round(max(1.0, min(10.0, score)), 1)


DANGLING = {"and", "but", "or", "so", "the", "a", "an", "to", "of", "in", "on", "at", "for", "with", "that",
            "about", "my", "your", "his", "her", "their", "our", "is", "was", "i", "you", "it", "because", "if"}


def heuristic_title(text: str) -> str:
    """The clip's opening words, cut at a natural break and never ending
    on a dangling 'and', 'the', 'about'..."""
    first = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    head = re.split(r"[,;:]", first, maxsplit=1)[0]
    source = (head if len(head.split()) >= 3 else first).split()
    words = source[:7]
    while words != source and len(words) > 2 and words[-1].lower().strip(".,!?;:'\"") in DANGLING:
        words.pop()
    return " ".join(words).rstrip(",;:") or "Watch this"


def _clean_title(title) -> str:
    title = re.sub(r"\s+", " ", str(title or "")).strip().strip('"').strip()
    return " ".join(title.split()[:9])[:70]


class OllamaUnavailable(Exception):
    pass


def check_ollama(host: str, model: str, timeout: float = 5) -> str:
    """Returns the exact installed model name to use ("llama3" ->
    "llama3:latest"), or raises OllamaUnavailable with a plain-English fix."""
    try:
        resp = requests.get(f"{host.rstrip('/')}/api/tags", timeout=timeout)
        resp.raise_for_status()
        names = [m.get("name", "") for m in resp.json().get("models", [])]
    except Exception as exc:
        raise OllamaUnavailable(f"Ollama isn't running at {host} - open the Ollama app (or run: ollama serve)") from exc
    if model in names:
        return model
    for name in names:
        if name.split(":")[0] == model.split(":")[0] and (":" not in model or name == model):
            return name
    installed = ", ".join(names) or "none"
    raise OllamaUnavailable(f"The model '{model}' isn't installed (installed: {installed}) - run: ollama pull {model}")


def list_models(host: str) -> list[str]:
    try:
        resp = requests.get(f"{host.rstrip('/')}/api/tags", timeout=4)
        resp.raise_for_status()
        return sorted(m.get("name", "") for m in resp.json().get("models", []) if m.get("name"))
    except Exception:
        return []


def _ask_ollama(host: str, model: str, prompt: str, timeout: float) -> str:
    try:
        resp = requests.post(
            f"{host.rstrip('/')}/api/generate",
            json={
                "model": model, "prompt": prompt, "stream": False,
                "format": "json",  # Ollama's own JSON mode: the reply is always valid JSON
                "options": {"temperature": 0.2, "num_ctx": 8192},
                "keep_alive": "15m",
            },
            timeout=timeout,
        )
    except requests.ConnectionError as exc:
        raise OllamaUnavailable(f"lost the connection to Ollama at {host}") from exc
    resp.raise_for_status()
    return resp.json().get("response", "")


def parse_scores(raw: str, wanted_ids: set[int]) -> dict[int, dict]:
    """Strictly validated {id: {score, title}} for the wanted ids only."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        match = re.search(r"\{.*\}", raw or "", re.S)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    items = data.get("clips") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return {}
    out = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            cid = int(item.get("id"))
            score = float(item.get("score"))
        except (TypeError, ValueError):
            continue
        title = _clean_title(item.get("title"))
        if cid in wanted_ids and 0 <= score <= 10 and title:
            out[cid] = {"score": round(max(1.0, score), 1), "title": title}
    return out


KIND_HINTS = {
    "stream": "\nThis video is a live stream (Twitch, Kick or YouTube live). The best stream clips are: a huge reaction (screaming, rage, laughing fit), a clutch or epic fail moment, a funny or awkward interaction with chat, a guest or collab, a donation/TTS message that causes a reaction, a prank, a shocking IRL moment, or a heated argument. Waiting, loading screens, quiet gameplay, reading chat with no reaction, AFK breaks, \"starting soon\" screens and sponsor reads are bad clips.",
    "podcast": "\nThis video is a podcast conversation. The best podcast clips are: a strong or controversial opinion, a surprising personal story, a funny exchange or punchline, a heated debate, a shocking fact, or advice people will want to share. Small talk, ad reads, sponsor segments and \"welcome to the show\" intros are bad clips.",
}


def score_candidates(
    candidates: list[dict], brain=None,
    progress: Optional[ProgressCB] = None, cancelled: Callable[[], bool] = lambda: False,
    kind: str = "",
) -> dict:
    """Fills in each candidate's score/title/source. Returns stats.

    brain: an ai.Brain (asks Gemini/Groq/Ollama, whichever answers), or None
    for the built-in scorer only. Every candidate starts with the built-in
    score, so whatever happens with the AIs, each one ends up valid."""
    def report(msg):
        if progress:
            progress(msg)

    for c in candidates:
        c["heuristic"] = heuristic_score(c["text"])
        c["score"], c["title"], c["source"] = c["heuristic"], heuristic_title(c["text"]), "heuristic"
    stats = {"ai_scored": 0, "fallback": len(candidates), "ai_error": None, "by": {}}
    if brain is None or not candidates:
        return stats

    size = getattr(brain, "batch_size", BATCH_SIZE)
    batches = [candidates[k:k + size] for k in range(0, len(candidates), size)]
    for b, batch in enumerate(batches, start=1):
        if cancelled():
            break
        report(f"AI is rating moments: batch {b} of {len(batches)}")
        missing = {c["id"]: c for c in batch}
        stop = False
        for _attempt in range(MAX_ATTEMPTS):
            if not missing:
                break
            todo = list(missing.values())
            # ids are renumbered 1..n inside each prompt - models handle that far better
            local = {n: c for n, c in enumerate(todo, start=1)}
            listing = "\n\n".join(f"Clip {n} ({c['end'] - c['start']:.0f}s):\n{c['text']}" for n, c in local.items())
            try:
                raw, who = brain.ask(PROMPT.format(n=len(local), clips=listing, hint=KIND_HINTS.get(kind, "")))
            except Exception as exc:  # every AI is down or out of free use (the brain already retried)
                stats["ai_error"], stop = str(exc), True
                break
            for n, result in parse_scores(raw, set(local)).items():
                c = local[n]
                # blend in a little of the built-in score to break ties sensibly
                c["score"] = round(result["score"] * 0.85 + c["heuristic"] * 0.15, 2)
                c["title"] = result["title"]
                c["source"] = who
                missing.pop(c["id"], None)
        if stop:
            report(f"No AI is answering ({stats['ai_error']}) - the built-in scorer rates the rest.")
            break

    for c in candidates:
        if c["source"] != "heuristic":
            stats["by"][c["source"]] = stats["by"].get(c["source"], 0) + 1
    stats["ai_scored"] = sum(stats["by"].values())
    stats["fallback"] = len(candidates) - stats["ai_scored"]
    return stats


def pick_best(candidates: list[dict], count: int, gap: float = 0.5) -> list[dict]:
    """Highest score first; never overlapping an already picked clip."""
    picked = []
    for c in sorted(candidates, key=lambda c: (-c["score"], c["start"])):
        if all(c["end"] + gap <= p["start"] or c["start"] >= p["end"] + gap for p in picked):
            picked.append(c)
            if len(picked) >= count:
                break
    return picked
