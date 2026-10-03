"""Captions in another language (e.g. English clips with Albanian captions).

Whisper gives every English word its time. The clip's speech is cut into short lines (a few words,
split at pauses and punctuation), the AI translates the lines, and each translated line is spread
over the time its English line was spoken - so the word-by-word captions still move with the voice.
The voices themselves stay original.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

import requests

LANGS = {
    "sq": "Albanian", "es": "Spanish", "pt": "Brazilian Portuguese", "fr": "French",
    "de": "German", "it": "Italian", "tr": "Turkish",
}
LINE_WORDS = 7       # at most this many English words per caption line
PAUSE = 0.6          # a silence this long starts a new line

PROMPT = """Translate these subtitle lines from a {kind} into natural, spoken {lang} - the way young people talk in \
TikTok and YouTube Shorts captions, not stiff textbook {lang}. Keep the meaning and the energy. Keep names of people, \
games, places and brands unchanged. Keep each line about as short as the original. Replace swear words with ***.
Answer ONLY with JSON: {{"lines": [{{"id": 1, "text": "..."}}]}} - one entry for every id.

Lines:
{lines}
"""


def lines_for(words: list[dict], start: float, end: float) -> list[dict]:
    """The clip's words grouped into short caption lines: [{"start", "end", "text"}]."""
    inside = [w for w in words if start - 0.05 <= w["start"] < end]
    lines, cur = [], []
    for i, w in enumerate(inside):
        cur.append(w)
        nxt = inside[i + 1] if i + 1 < len(inside) else None
        ends_sentence = bool(re.search(r"[.!?,;:]$", w["text"].strip()))
        gap = (nxt["start"] - w["end"]) if nxt else 0
        if not nxt or ends_sentence or gap >= PAUSE or len(cur) >= LINE_WORDS:
            lines.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": " ".join(x["text"].strip() for x in cur)})
            cur = []
    return lines


def translate(brain, lines: list[str], lang: str, kind: str = "") -> list[str | None]:
    """Translated lines in the same order; None where the AI gave nothing usable."""
    out: list[str | None] = [None] * len(lines)
    if brain is None or lang not in LANGS:
        return out
    what = {"stream": "live stream", "podcast": "podcast"}.get(kind, "video")
    for k in range(0, len(lines), 40):
        batch = {i: lines[i] for i in range(k, min(k + 40, len(lines)))}
        for _ in range(3):  # ask again only for the lines that came back missing
            todo = {i: t for i, t in batch.items() if out[i] is None}
            if not todo:
                break
            listing = "\n".join(f"{n}. {t}" for n, t in enumerate(todo.values(), start=1))
            ids = list(todo)
            try:
                raw, _who = brain.ask(PROMPT.format(kind=what, lang=LANGS[lang], lines=listing))
                m = re.search(r"\{.*\}", raw or "", re.S)
                data = json.loads(m.group(0)) if m else {}
            except Exception:
                continue
            for item in (data.get("lines") if isinstance(data, dict) else None) or []:
                try:
                    n = int(item.get("id"))
                except (TypeError, ValueError, AttributeError):
                    continue
                text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
                if 1 <= n <= len(ids) and text:
                    out[ids[n - 1]] = text[:200]
    return out


# a free translator that needs no key (MyMemory: about 5,000 characters a day per PC, more with an email)
FREE_URL = "https://api.mymemory.translated.net/get"
FREE_CODES = {"pt": "pt-BR"}
free_state = {"used_up": False, "error": ""}


def _free_one(text: str, lang: str, email: str = "") -> str | None:
    if free_state["used_up"] or not text.strip():
        return None
    params = {"q": text[:450], "langpair": f"en|{FREE_CODES.get(lang, lang)}"}
    if email:
        params["de"] = email
    try:
        r = requests.get(FREE_URL, params=params, timeout=20)
        data = r.json()
    except Exception as exc:
        free_state["error"] = f"the free translator didn't answer ({type(exc).__name__})"
        return None
    out = str((data.get("responseData") or {}).get("translatedText") or "").strip()
    status = str(data.get("responseStatus"))
    if status == "429" or "MYMEMORY WARNING" in out.upper() or "USED ALL AVAILABLE FREE" in out.upper():
        free_state["used_up"] = True
        free_state["error"] = "the free translator's daily limit is used up (it resets tomorrow)"
        return None
    if status != "200" or not out or out.lower() == text.lower().strip():
        return None
    return re.sub(r"\s+", " ", out)[:200]


def translate_free(lines: list[str], lang: str, email: str = "") -> list[str | None]:
    """The same lines through the free translator (used when no AI engine answers)."""
    if lang not in LANGS:
        return [None] * len(lines)
    free_state.update(used_up=False, error="")
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda t: _free_one(t, lang, email), lines))


def timed_words(lines: list[dict], translated: list[str | None]) -> list[dict]:
    """Translated lines as timed words for the captions: each line's words share its time,
    longer words a little longer. Lines the AI couldn't translate keep their original words."""
    words = []
    for ln, tr in zip(lines, translated):
        text = tr or ln["text"]
        parts = text.split()
        if not parts:
            continue
        span = max(0.2, ln["end"] - ln["start"])
        weights = [len(p) + 2 for p in parts]
        total, t = sum(weights), ln["start"]
        for p, wgt in zip(parts, weights):
            d = span * wgt / total
            words.append({"start": round(t, 3), "end": round(t + d * 0.92, 3), "text": p})
            t += d
    return words


TEMPLATES = {  # the fixed lines of the description, per language: from, full video, subscribe
    "sq": ("Nga", "Videoja e plotë", "Abonohu te {c} për më shumë klipe çdo ditë.", "Abonohu për më shumë klipe çdo ditë."),
    "es": ("De", "Video completo", "Suscríbete a {c} para más clips cada día.", "Suscríbete para más clips cada día."),
    "pt": ("De", "Vídeo completo", "Inscreva-se no {c} para mais clipes todos os dias.", "Inscreva-se para mais clipes todos os dias."),
    "fr": ("Source", "Vidéo complète", "Abonne-toi à {c} pour plus de clips chaque jour.", "Abonne-toi pour plus de clips chaque jour."),
    "de": ("Von", "Ganzes Video", "Abonniere {c} für täglich neue Clips.", "Abonniere für täglich neue Clips."),
    "it": ("Da", "Video completo", "Iscriviti a {c} per altre clip ogni giorno.", "Iscriviti per altre clip ogni giorno."),
    "tr": ("Kaynak", "Videonun tamamı", "Her gün yeni klipler için {c} kanalına abone ol.", "Her gün yeni klipler için abone ol."),
}


def localize_description(desc: str, lang: str, channel_name: str = "") -> str:
    """Swaps the English fixed lines of a built-in description for the chosen language."""
    t = TEMPLATES.get(lang)
    if not t:
        return desc
    desc = re.sub(r"(?m)^From: ", f"{t[0]}: ", desc)
    desc = re.sub(r"(?m)^Full video: ", f"{t[1]}: ", desc)
    desc = re.sub(r"(?m)^Subscribe to .+ for more clips every day\.$", t[2].format(c=channel_name) if channel_name else t[3], desc)
    desc = re.sub(r"(?m)^Subscribe for more clips every day\.$", t[3], desc)
    return desc
