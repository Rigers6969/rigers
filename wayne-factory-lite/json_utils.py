"""Shared JSON-extraction helper for The Wayne Factory's LLM-calling code.

Lives in its own module (rather than in empire.py) so both empire.py and
branding.py can import it without a circular dependency between them.
"""
from __future__ import annotations

import json
import re
from typing import Optional

# --------------------------------------------------------------------------
# Robust JSON extraction - the actual fix for "no valid viral moments".
#
# LLMs (local models especially) rarely return bare, perfectly-formed JSON.
# Common real-world shapes this has to survive:
#   - ```json ... ``` markdown fences around the array
#   - prose before/after the JSON ("Here are the clips: [...]")
#   - the array wrapped in an object, e.g. {"clips": [...]}
#   - a single object instead of an array when there's only one match
#   - trailing commas before a closing bracket/brace
# --------------------------------------------------------------------------


def extract_json_items(raw: str) -> Optional[list]:
    """Best-effort extraction of a list of dicts from a noisy LLM response."""
    if not raw or not raw.strip():
        return None

    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)

    def to_list(data):
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # A single-key object is almost always a wrapper the model added
            # around the real payload, e.g. {"clips": [...]} - unwrap it.
            # A multi-key object (e.g. a brand kit with several scalar
            # fields plus a "hashtags" list) is the payload itself; unwrapping
            # it here would silently return an unrelated nested list instead.
            if len(data) == 1:
                (value,) = data.values()
                if isinstance(value, list):
                    return value
            return [data]
        return None

    try:
        result = to_list(json.loads(text))
        if result is not None:
            return result
    except json.JSONDecodeError:
        pass

    # Fall back to scanning for the outermost bracket/brace block, since the
    # model may have wrapped valid JSON in explanatory prose.
    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start == -1 or end == -1 or end <= start:
            continue
        candidate = text[start:end + 1]
        for attempt in (candidate, re.sub(r",\s*([\]}])", r"\1", candidate)):
            try:
                result = to_list(json.loads(attempt))
                if result is not None:
                    return result
            except json.JSONDecodeError:
                continue
    return None
