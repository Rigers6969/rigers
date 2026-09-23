"""Fetches real word definitions from the Free Dictionary API
(dictionaryapi.dev) - free, no key, no rate limit, confirmed live and
documented at https://dictionaryapi.dev/.

Words come from common_words.txt (top 300 most common English words,
first20hours/google-10000-english, MIT licensed) - filtered to drop
single-letter entries, which are web-crawl artifacts (truncated
initials, stray characters) rather than real vocabulary.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import requests

API_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
WORDS_FILE = Path(__file__).resolve().parent / "common_words.txt"

ProgressCB = Callable[[str], None]


def load_word_list(limit: Optional[int] = None) -> list[str]:
    words = []
    for line in WORDS_FILE.read_text(encoding="utf-8").splitlines():
        word = line.strip()
        if not word or word.startswith("#") or len(word) < 2:
            continue
        words.append(word)
    return words[:limit] if limit else words


def fetch_word(word: str, timeout: float = 10.0) -> Optional[dict]:
    """Returns {"word", "phonetic", "meanings": [{"part_of_speech",
    "definition", "example"}]} for one word, or None if the API has no
    entry for it (a real, expected outcome for some words - not every
    common word is in every dictionary)."""
    try:
        resp = requests.get(API_URL.format(word=word), timeout=timeout)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None

    try:
        entries = resp.json()
    except ValueError:
        return None
    if not entries or not isinstance(entries, list):
        return None

    entry = entries[0]
    phonetic = entry.get("phonetic", "")
    if not phonetic:
        for p in entry.get("phonetics", []):
            if p.get("text"):
                phonetic = p["text"]
                break

    meanings = []
    for meaning in entry.get("meanings", []):
        part_of_speech = meaning.get("partOfSpeech", "")
        for definition in meaning.get("definitions", [])[:1]:  # top definition per part of speech
            meanings.append({
                "part_of_speech": part_of_speech,
                "definition": definition.get("definition", ""),
                "example": definition.get("example", ""),
            })
        if len(meanings) >= 3:  # a word like "run" has dozens of senses - cap for a readable PDF entry
            break

    if not meanings:
        return None
    return {"word": entry.get("word", word), "phonetic": phonetic, "meanings": meanings}


def fetch_vocabulary(limit: int = 150, progress: Optional[ProgressCB] = None) -> list[dict]:
    words = load_word_list(limit=limit)
    results = []
    for i, word in enumerate(words, start=1):
        if progress:
            progress(f"Vocabulary {i}/{len(words)}: {word}")
        entry = fetch_word(word)
        if entry:
            results.append(entry)
    return results
