"""Clipping campaign rules (Whop Content Rewards and similar): what every clip must and mustn't have.

  must    a name every title/caption must mention   (e.g. "Preme")
  ban     words no title/caption may contain       (e.g. "Drake") - moments that talk about them are skipped too
  focus   who the clips must be about, for the AI   (e.g. "Preme")
  watermark  the campaign's logo, put over every clip - visible, not at an edge
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

APP_DIR = Path(__file__).resolve().parent
WM_DIR = APP_DIR / "watermarks"
WM_NAME_RE = re.compile(r"^[\w\- ]{1,60}\.png$")
WM_POSITIONS = {"upper": 0.33, "middle": 0.5, "lower": 0.62}   # centre of the logo, as a share of the height


def words(text: str) -> list[str]:
    return [w.strip() for w in re.split(r"[,;\n]+", text or "") if w.strip()][:10]


def _ban_re(ban: list[str]):
    return re.compile(r"(?i)\b(" + "|".join(re.escape(b) for b in ban) + r")('s)?\b") if ban else None


def mentions(text: str, ban: list[str]) -> bool:
    r = _ban_re(ban)
    return bool(r and r.search(text or ""))


def _scrub(text: str, ban: list[str]) -> str:
    r = _ban_re(ban)
    if not r:
        return text
    text = r.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\s+([,.!?])", r"\1", text)).strip()


def _has(text: str, word: str) -> bool:
    return bool(re.search(r"(?i)\b" + re.escape(word) + r"\b", text or ""))


def fix_title(title: str, must: list[str], ban: list[str]) -> str:
    title = _scrub(title, ban) or title
    for m in must:
        if not _has(title, m):
            title = f"{m}: {title}" if len(title) + len(m) + 2 <= 100 else title[: 100 - len(m) - 3].rstrip() + f" | {m}"
    return title[:100]


def fix_upload(up: dict | None, must: list[str], ban: list[str], extra: list[str] | None = None) -> dict | None:
    """Applies the rules to a clip's title, description, tags and hashtags (extra = hashtags the campaign requires)."""
    extra = [re.sub(r"\W+", "", h) for h in extra or [] if re.sub(r"\W+", "", h)]
    if not up or (not must and not ban and not extra):
        return up
    up = dict(up)
    up["title"] = fix_title(up.get("title", ""), must, ban)
    lines = (up.get("description") or "").splitlines()
    while lines and (not lines[-1].strip() or lines[-1].lstrip().startswith("#")):  # the hashtag line is rebuilt below
        lines.pop()
    lines = _scrub("\n".join(lines), ban).splitlines() or [""]
    for m in must:
        if not _has("\n".join(lines), m):
            lines[0] = f"{m}: {lines[0]}".strip()
    hashtags = [h for h in up.get("hashtags") or [] if not mentions(h, ban)]
    for h in reversed(extra):  # required hashtags first, so they survive the 5-hashtag limit
        if h.lower() not in {x.lower() for x in hashtags}:
            hashtags.insert(1 if hashtags and hashtags[0].lower() == "shorts" else 0, h)
    for m in must:
        tag = re.sub(r"\W+", "", m)
        if tag and tag.lower() not in {h.lower() for h in hashtags}:
            hashtags.insert(1 if hashtags else 0, tag)
    hashtags = hashtags[:5]
    if hashtags:
        lines += ["", " ".join("#" + h for h in hashtags)]
    up["description"] = "\n".join(lines).strip()
    up["hashtags"] = hashtags
    tags = [t for t in up.get("tags") or [] if not mentions(t, ban)]
    for m in must:
        if m.lower() not in {t.lower() for t in tags}:
            tags.insert(0, m.lower())
    up["tags"] = tags[:15]
    return up


def ai_hint(focus: list[str], ban: list[str]) -> str:
    out = ""
    if focus:
        out += f"\nOnly pick moments that clearly involve {' and '.join(focus)} (they speak, react, or the moment is about them) - give other moments a low score."
    if ban:
        out += f"\nNever mention {', '.join(ban)} in a title."
    return out


def save_watermark(data: bytes, name: str) -> str:
    """Stores an uploaded logo as PNG (keeps its transparency). Returns the stored name."""
    import io
    WM_DIR.mkdir(exist_ok=True)
    img = Image.open(io.BytesIO(data))
    img.load()
    img = img.convert("RGBA")
    if max(img.size) > 1600:
        img.thumbnail((1600, 1600))
    stem = re.sub(r"[^\w\- ]+", "", Path(name).stem).strip()[:50] or "watermark"
    out = f"{stem}.png"
    img.save(WM_DIR / out)
    return out


def watermark_path(name: str) -> Path | None:
    if not name or not WM_NAME_RE.match(name):
        return None
    p = WM_DIR / name
    return p if p.exists() else None
