"""Commentary intro: a narrator says one hook line before the clip starts ("This man put Jack in his place.").

The AI writes one short line per clip (from what is said in it); without an AI the clip's title is read out.
The voice is Microsoft's free neural voices (edge-tts - no account, no key), the same engine the voice generator
uses. While the narrator talks, the clip's first picture stands still (zoomed in), then the clip plays.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

VOICES = {  # natural-sounding narrators
    "en-US-AndrewNeural": "Andrew (US, male - calm narrator)",
    "en-US-BrianNeural": "Brian (US, male - casual)",
    "en-US-ChristopherNeural": "Christopher (US, male - deep)",
    "en-US-AvaNeural": "Ava (US, female)",
    "en-US-EmmaNeural": "Emma (US, female - friendly)",
    "en-GB-RyanNeural": "Ryan (British, male)",
}
DEFAULT_VOICE = "en-US-AndrewNeural"
LANG_VOICES = {"sq": "sq-AL-IlirNeural", "es": "es-ES-AlvaroNeural", "pt": "pt-BR-AntonioNeural", "fr": "fr-FR-HenriNeural",
               "de": "de-DE-ConradNeural", "it": "it-IT-DiegoNeural", "tr": "tr-TR-AhmetNeural"}  # for translated clips

PROMPT = """You are the narrator of viral {what} Shorts. For each clip below, write ONE short spoken hook line that is read \
out BEFORE the clip plays, like commentary channels do: "This man put Jack in his place.", "She had no idea who she \
was talking to.", "He didn't expect this question.". Rules: 6 to 14 words, simple spoken English{lang}, makes people \
want to watch, true to what happens in the clip (never invent facts), no hashtags, no emojis, no quotes from the clip, \
don't start with "In this clip".
Answer ONLY with JSON: {{"lines": [{{"id": 1, "line": "..."}}]}}

Clips:
{clips}
"""


class VoiceError(Exception):
    pass


def write_lines(brain, clips: list[dict], kind: str = "", lang_name: str = "") -> dict[int, str]:
    """{clip number: hook line} from the AI for clips [{"n", "title", "text"}]; missing ones are left out."""
    out: dict[int, str] = {}
    if brain is None or not clips:
        return out
    what = {"stream": "streamer", "podcast": "podcast"}.get(kind, "video")
    for k in range(0, len(clips), 10):
        batch = clips[k:k + 10]
        listing = "\n".join(f'{i}. Title: {c["title"]}\n   What is said: {c["text"][:700]}' for i, c in enumerate(batch, start=1))
        try:
            raw, _who = brain.ask(PROMPT.format(what=what, clips=listing, lang=f" (in {lang_name})" if lang_name else ""))
            m = re.search(r"\{.*\}", raw or "", re.S)
            data = json.loads(m.group(0)) if m else {}
        except Exception:
            continue
        for item in (data.get("lines") if isinstance(data, dict) else None) or []:
            try:
                i = int(item.get("id"))
            except (TypeError, ValueError, AttributeError):
                continue
            line = re.sub(r"\s+", " ", str(item.get("line") or "")).strip().strip('"')
            if 1 <= i <= len(batch) and 3 <= len(line.split()) <= 20:
                out[batch[i - 1]["n"]] = line[:160]
    return out


def fallback_line(title: str) -> str:
    """No AI: the narrator reads the title."""
    t = re.sub(r"\s+", " ", title).strip()
    return (t if t.endswith((".", "!", "?")) else t + ".") if t else "Watch what happens next."


def speak(text: str, out_path: Path, voice: str = DEFAULT_VOICE) -> dict:
    """Says `text` with a free neural voice into out_path (mp3).
    Returns {"path", "duration", "words": [{"start", "end", "text"}]} (word times for the captions)."""
    try:
        import edge_tts
    except ImportError as exc:
        raise VoiceError("The free voice isn't installed - close the app and double-click start.bat again.") from exc
    voice = voice if voice in VOICES or voice in LANG_VOICES.values() else DEFAULT_VOICE

    async def run() -> list[dict]:
        try:
            comm = edge_tts.Communicate(text, voice, rate="+8%", boundary="WordBoundary")
        except TypeError:  # older edge-tts: word boundaries are the default
            comm = edge_tts.Communicate(text, voice, rate="+8%")
        words, audio = [], bytearray()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append({"start": round(start, 3), "end": round(start + chunk["duration"] / 1e7, 3), "text": chunk["text"]})
        if not audio:
            raise VoiceError("the voice service sent no audio")
        out_path.write_bytes(bytes(audio))
        return words

    try:
        words = asyncio.run(run())
    except VoiceError:
        raise
    except Exception as exc:
        raise VoiceError(f"The free voice didn't answer ({type(exc).__name__}) - check the internet connection.") from exc
    import renderer
    duration = renderer.media_duration(out_path) or (words[-1]["end"] + 0.3 if words else 2.0)
    if not words:  # no word times: spread the words over the speech
        parts = text.split()
        step = duration / max(1, len(parts))
        words = [{"start": round(i * step, 3), "end": round((i + 1) * step * 0.95, 3), "text": p} for i, p in enumerate(parts)]
    return {"path": str(out_path), "duration": round(duration, 3), "words": words}
