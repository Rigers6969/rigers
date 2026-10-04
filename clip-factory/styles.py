"""Viral caption styles and emoji pops (on top of the classic word-by-word captions).

  pop    1-2 huge words at a time; the spoken word pops in and turns yellow, strong words are green
  box    the spoken word sits in a coloured box (TikTok style)
  story  kinetic typography: key words huge, bold and slanted, small words small, lines that build up
         word by word, the last key word underlined (the podcast-clip look)
Emoji pops: an emoji jumps in above the captions when a matching word is said (laugh -> 😂, money -> 💰...).
Emoji pictures: Twemoji by Twitter, Inc. and contributors, CC-BY 4.0 (see emoji/LICENSE.txt).
"""
from __future__ import annotations

import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
EMOJI_DIR = APP_DIR / "emoji"
FONTS_DIR = APP_DIR / "fonts"
STYLES = ("pop", "box", "story")

WHITE, YELLOW, GREEN, BLACK = "&H00FFFFFF&", "&H0000E5FF&", "&H005AFF3C&", "&H00000000&"
VIOLET = "&H00F65C8B&"  # the box colour (stands out on most videos, unlike yellow)
SMALL = {"is", "a", "an", "the", "to", "of", "and", "or", "in", "on", "at", "it", "its", "be", "so", "but", "for", "with",
         "that", "this", "was", "are", "am", "as", "if", "by", "from", "up", "into", "than", "then", "do", "did", "just"}
STRONG = {"never", "always", "everything", "nothing", "everyone", "nobody", "best", "worst", "biggest", "first", "last",
          "crazy", "insane", "million", "billion", "money", "dead", "died", "love", "hate", "secret", "truth", "lie",
          "fired", "rich", "broke", "free", "banned", "war", "fight", "won", "lost", "win", "lose", "only", "real",
          "fake", "huge", "impossible", "dangerous", "scared", "angry", "shocked", "why", "how", "stop", "quit"}
EMOJIS = [  # (words that trigger it, Twemoji code)
    (r"laugh|lol|lmao|funny|joke|hilarious|haha", "1f602"), (r"dead|died|dying|kill(ed)?|rip|bro", "1f480"),
    (r"money|cash|dollars?|paid|rich|\$\d", "1f4b0"), (r"million|billion", "1f4b5"), (r"fire|insane|crazy|wild|lit", "1f525"),
    (r"shock|what\?*|wow|omg|unbelievable", "1f631"), (r"cry|crying|sad|tears", "1f62d"), (r"angry|mad|furious|rage", "1f621"),
    (r"mind|genius|brain", "1f92f"), (r"look|watch|see", "1f440"), (r"love|heart", "2764"), (r"win|won|champion|best", "1f3c6"),
    (r"think|wonder|why", "1f914"), (r"cool|chill|easy", "1f60e"), (r"please|pray|god|thank", "1f64f"),
    (r"hundred|perfect|exactly|facts", "1f4af"), (r"game|gaming|play(ing)?", "1f3ae"), (r"fast|quick|speed", "26a1"),
    (r"police|alert|emergency|warning", "1f6a8"), (r"awkward|cringe|oops", "1f62c"), (r"clown|stupid|dumb", "1f921"),
    (r"king|queen|boss|goat", "1f451"), (r"embarrass|blush", "1f633"),
]


def clean(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def strong(word: str) -> bool:
    w = re.sub(r"[^\w$%']", "", word.lower())
    return bool(re.search(r"[\d$%]", word)) or w in STRONG or len(w) >= 9


def emoji_moments(words: list[dict], duration: float, gap: float = 4.0, limit: int = 4) -> list[tuple[float, float, str]]:
    """(start, end, code) for up to `limit` emoji pops, at least `gap` seconds apart."""
    out, last = [], -gap
    for w in words:
        token = w["text"].lower().strip(".,!?\"'")
        if w["start"] - last < gap or len(out) >= limit:
            continue
        for pattern, code in EMOJIS:
            if re.fullmatch(pattern, token) and (EMOJI_DIR / f"{code}.png").exists():
                start = max(0.0, w["start"] - 0.05)
                out.append((round(start, 2), round(min(duration, start + 1.3), 2), code))
                last = w["start"]
                break
    return out


def fonts_dir_for(out_dir: Path) -> str:
    """The fonts folder as ffmpeg's subtitles filter wants it: relative to where ffmpeg runs (no C:\\ colons)."""
    import os
    try:
        return os.path.relpath(FONTS_DIR, out_dir).replace("\\", "/")
    except ValueError:  # another drive on Windows: no relative path - use the fonts Windows already has
        return ""


def styles_block(cap_size: int) -> str:
    return (
        f"Style: Pop,Anton,{round(cap_size * 1.45)},{WHITE},&H000000FF&,{BLACK},&H96000000&,0,0,0,0,100,100,2,0,1,9,5,2,60,60,0,1\n"
        f"Style: BoxBg,Anton,{round(cap_size * 1.25)},&HFF000000&,&H000000FF&,{VIOLET},{VIOLET},0,0,0,0,100,100,2,0,3,16,0,2,60,60,0,1\n"
        f"Style: BoxText,Anton,{round(cap_size * 1.25)},{WHITE},&H000000FF&,{BLACK},&H80000000&,0,0,0,0,100,100,2,0,1,7,3,2,60,60,0,1\n"
        "Style: Story,Arial,110,&H00FFFFFF&,&H000000FF&,&H20000000&,&H60000000&,0,0,0,0,100,100,0,0,1,6,5,7,0,0,0,1\n"
    )


def _t(seconds: float) -> str:
    cs = int(round(max(0.0, seconds) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def pop_events(groups: list[list[dict]], duration: float, x: int, y: int, an: int) -> list[str]:
    out = []
    for g, group in enumerate(groups):
        g_start = group[0]["start"]
        g_end = max(g_start + 0.2, min(groups[g + 1][0]["start"] if g + 1 < len(groups) else duration, group[-1]["end"] + 0.5, duration))
        texts = [clean(w["text"]).upper() for w in group]
        for k, w in enumerate(group):
            w_start = g_start if k == 0 else w["start"]
            w_end = group[k + 1]["start"] if k + 1 < len(group) else g_end
            if w_end - w_start <= 0.01:
                continue
            parts = []
            for j, t in enumerate(texts):
                if j == k:  # the word being said: pops in big and yellow
                    parts.append(f"{{\\c{YELLOW}\\fscx130\\fscy130\\t(0,110,\\fscx100\\fscy100)}}{t}{{\\r}}")
                else:
                    parts.append(f"{{\\c{GREEN}}}{t}{{\\r}}" if strong(group[j]["text"]) else t)
            out.append(f"Dialogue: 2,{_t(w_start)},{_t(w_end)},Pop,,0,0,0,,{{\\an{an}\\pos({x},{y})}}{' '.join(parts)}\n")
    return out


def box_events(groups: list[list[dict]], duration: float, x: int, y: int, an: int) -> list[str]:
    out = []
    for g, group in enumerate(groups):
        g_start = group[0]["start"]
        g_end = max(g_start + 0.2, min(groups[g + 1][0]["start"] if g + 1 < len(groups) else duration, group[-1]["end"] + 0.5, duration))
        texts = [clean(w["text"]).upper() for w in group]
        pos = f"{{\\an{an}\\pos({x},{y})}}"
        for k, w in enumerate(group):
            w_start = g_start if k == 0 else w["start"]
            w_end = group[k + 1]["start"] if k + 1 < len(group) else g_end
            if w_end - w_start <= 0.01:
                continue
            # the box layer draws a box only behind the spoken word (other words are invisible there)
            box = " ".join(f"{{\\3a&H00&}}{t}" if j == k else f"{{\\3a&HFF&}}{t}" for j, t in enumerate(texts))
            out.append(f"Dialogue: 1,{_t(w_start)},{_t(w_end)},BoxBg,,0,0,0,,{pos}{box}\n")
            out.append(f"Dialogue: 2,{_t(w_start)},{_t(w_end)},BoxText,,0,0,0,,{pos}{' '.join(texts)}\n")
    return out


def _phrases(words: list[dict], max_words: int = 6) -> list[list[dict]]:
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if not nxt or re.search(r"[.!?,;:]$", w["text"].strip()) or (nxt["start"] - w["end"]) > 0.5 or len(cur) >= max_words:
            out.append(cur)
            cur = []
    return out


def story_events(words: list[dict], duration: float, top: int, bottom: int, center_x: int = 540) -> list[str]:
    """Kinetic typography: each phrase builds up word by word, lines stacked and centred inside top..bottom."""
    out = []
    phrases = _phrases(words)
    for p, phrase in enumerate(phrases):
        start = phrase[0]["start"]
        end = max(start + 0.4, min(phrases[p + 1][0]["start"] if p + 1 < len(phrases) else duration, phrase[-1]["end"] + 0.6, duration))
        kinds = []
        longest = max(range(len(phrase)), key=lambda i: len(re.sub(r"\W", "", phrase[i]["text"])))
        for i, w in enumerate(phrase):
            bare = re.sub(r"[^\w']", "", w["text"].lower())
            kinds.append("key" if (strong(w["text"]) or i == longest) and bare not in SMALL else "small" if bare in SMALL else "word")
        last_key = max((i for i, k in enumerate(kinds) if k == "key"), default=-1)
        # lines: a key word stands alone; small words sit in front of the next word
        lines, cur = [], []
        for i, k in enumerate(kinds):
            if k == "key":
                if cur:
                    lines.append(cur)
                lines.append([i])
                cur = []
            else:
                cur.append(i)
                if len(cur) >= 2 and kinds[i] != "small":
                    lines.append(cur)
                    cur = []
        if cur:
            lines.append(cur)

        def size(i):
            n = max(1, len(clean(phrase[i]["text"])))
            if kinds[i] == "key":
                return min(150, int(1700 / n))
            return 64 if kinds[i] == "small" else min(112, int(1900 / n))

        heights = [max(size(i) for i in ln) * 1.08 for ln in lines]
        total = sum(heights)
        y = max(top, int((top + bottom) / 2 - total / 2))
        for li, ln in enumerate(lines):
            parts = []
            for j, i in enumerate(ln):
                w = phrase[i]
                text = clean(w["text"])
                if kinds[i] == "key":
                    look = f"\\fnAnton\\fs{size(i)}\\i1\\b0" + ("\\u1" if i == last_key else "")
                    text = text.upper()
                elif kinds[i] == "small":
                    look = f"\\fnArial\\fs{size(i)}\\i0\\b0"
                else:
                    look = f"\\fnArial\\fs{size(i)}\\i0\\b0"
                delay = int((w["start"] - phrase[ln[0]]["start"]) * 1000)
                appear = f"\\alpha&HFF&\\t({delay},{delay + 90},\\alpha&H00&)" if j else ""
                parts.append(f"{{{look}{appear}}}{text}{{\\u0}}")
            line_start = phrase[ln[0]]["start"]
            out.append(f"Dialogue: 2,{_t(line_start)},{_t(end)},Story,,0,0,0,,{{\\an8\\pos({center_x},{int(y)})\\fad(90,120)\\blur2}}{' '.join(parts)}\n")
            y += heights[li]
    return out
