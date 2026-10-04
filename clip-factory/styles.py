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


_font_cache: dict = {}
FONT_FILES = {  # for measuring: Anton is ours; Arial from Windows, or a look-alike with the same widths
    "Anton": [FONTS_DIR / "Anton-Regular.ttf"],
    "Arial": [Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
              Path("/Library/Fonts/Arial.ttf")],
    "ArialBold": [Path("C:/Windows/Fonts/arialbd.ttf"), Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
                  Path("/Library/Fonts/Arial Bold.ttf")],
}


def _font(name: str):
    """(PIL font at size 100, em per unit of ASS font size, baseline as a share of the line) or None."""
    if name not in _font_cache:
        import struct
        from PIL import ImageFont
        _font_cache[name] = None
        for p in FONT_FILES[name]:
            try:
                f = ImageFont.truetype(str(p), 100)
                d = p.read_bytes()
                tables = {d[12 + 16 * i: 16 + 16 * i]: struct.unpack(">I", d[20 + 16 * i: 24 + 16 * i])[0]
                          for i in range(struct.unpack(">H", d[4:6])[0])}
                upem = struct.unpack(">H", d[tables[b"head"] + 18: tables[b"head"] + 20])[0]
                win_a, win_d = struct.unpack(">HH", d[tables[b"OS/2"] + 74: tables[b"OS/2"] + 78])
                # libass makes ASS font size = the font's Windows line height (winAscent + winDescent)
                _font_cache[name] = (f, upem / (win_a + win_d), win_a / (win_a + win_d))
                break
            except (OSError, KeyError, struct.error, ValueError):
                continue
    return _font_cache[name]


def ascent(name: str, fs: float) -> float:
    """How far below the top of an ASS line its baseline sits."""
    f = _font(name)
    return fs * (f[2] if f else 0.8)


def text_width(text: str, name: str, size: float) -> float:
    """Width in screen pixels of text at ASS font size `size`."""
    f = _font(name)
    if f is None:
        return len(text) * size * {"Anton": 0.27}.get(name, 0.46)
    return f[0].getlength(text) / 100 * size * f[1]


STORY_W = 940        # the widest a line may be (the screen is 1080)
KEY_MAX, WORD, SMALL_SIZE = 230, 96, 70


def story_events(words: list[dict], duration: float, top: int, bottom: int, center_x: int = 540) -> list[str]:
    """Kinetic typography, centred: each phrase builds up word by word, e.g.
         PROCRASTINATING      <- key word: huge, bold, slanted
            is choosing       <- normal words together, small words small
           to DELAY           <- the last key word underlined (the line grows in under it)
    """
    out = []
    phrases = _phrases(words)
    for p, phrase in enumerate(phrases):
        start = phrase[0]["start"]
        end = max(start + 0.4, min(phrases[p + 1][0]["start"] if p + 1 < len(phrases) else duration, phrase[-1]["end"] + 0.6, duration))
        bare = [re.sub(r"[^\w']", "", w["text"].lower()) for w in phrase]
        texts = [clean(w["text"]) for w in phrase]
        longest = max(range(len(phrase)), key=lambda i: len(bare[i]) if bare[i] not in SMALL else -1)
        keys = [i for i in range(len(phrase)) if bare[i] not in SMALL and (strong(phrase[i]["text"]) or i == longest)]
        keys = sorted(sorted(keys, key=lambda i: -len(bare[i]))[:2])  # at most 2 big words per phrase
        last_word = max((i for i in range(len(phrase)) if bare[i] and bare[i] not in SMALL), default=-1)
        if len(keys) < 2 and len(phrase) >= 4 and last_word > (keys[-1] if keys else -1) + 1:
            keys.append(last_word)  # the punchline word at the end gets big too ("to DELAY")
        kinds = ["key" if i in keys else "small" if bare[i] in SMALL else "word" for i in range(len(phrase))]
        texts = [t.rstrip(".,;:") or t if kinds[i] == "key" else t for i, t in enumerate(texts)]  # "DELAY", not "DELAY."
        last_key = keys[-1] if keys else -1

        # lines: a key word gets its own line (small words just before it ride along: "to DELAY"),
        # other words go two by two ("is choosing"), and a small word never ends a line
        lines, cur = [], []
        for i, k in enumerate(kinds):
            if k == "key":
                if cur and all(kinds[j] == "small" for j in cur):
                    lines.append(cur + [i])
                else:
                    if cur:
                        lines.append(cur)
                    lines.append([i])
                cur = []
            else:
                if k == "small" and any(kinds[j] == "word" for j in cur):
                    lines.append(cur)  # a small word starts the next line: "is choosing / to delay"
                    cur = []
                cur.append(i)
                if k == "word" and sum(kinds[j] == "word" for j in cur) >= 2:
                    lines.append(cur)
                    cur = []
        if cur:
            if lines and "key" not in [kinds[j] for j in lines[-1]] and len(lines[-1]) + len(cur) <= 4:
                lines[-1] += cur
            else:
                lines.append(cur)

        def sizes(ln):
            """font size per word of a line, shrunk until the line fits the screen"""
            out_sizes = {}
            for i in ln:
                if kinds[i] == "key":
                    w100 = text_width(texts[i].upper(), "Anton", 100) * 1.08  # + room for the slant
                    out_sizes[i] = max(70, min(KEY_MAX, int(100 * STORY_W / max(1.0, w100))))
                else:
                    out_sizes[i] = SMALL_SIZE if kinds[i] == "small" else WORD
            while True:
                width = line_width(ln, out_sizes)
                if width * 1.06 <= STORY_W or min(out_sizes.values()) <= 40:
                    return out_sizes, width
                out_sizes = {i: int(v * 0.92) for i, v in out_sizes.items()}

        def word_w(i, size):
            if kinds[i] == "key":
                return text_width(texts[i].upper(), "Anton", size)
            return text_width(texts[i], "ArialBold" if kinds[i] == "word" else "Arial", size)

        def line_width(ln, sz):
            return sum(word_w(i, sz[i]) for i in ln) + sum(text_width(" ", "Arial", sz[i]) for i in ln[1:])

        laid = [sizes(ln) for ln in lines]
        heights = [max(sz.values()) * (1.0 if any(kinds[i] == "key" for i in ln) else 1.08) + (24 if last_key in ln else 0)
                   for ln, (sz, _) in zip(lines, laid)]
        total = sum(heights)
        y = max(top, int((top + bottom) / 2 - total / 2))
        # a soft dark shade behind the words so they read on bright video
        pad = 60
        out.append(f"Dialogue: 0,{_t(start)},{_t(end)},Story,,0,0,0,,{{\\an7\\pos(0,{int(y - pad)})\\p1\\bord0\\shad0"
                   f"\\c&H000000&\\alpha&HFF&\\t(0,150,\\alpha&HA8&)\\blur40}}m 0 0 l 1080 0 l 1080 {int(total + pad * 2)} l 0 {int(total + pad * 2)}{{\\p0}}\n")
        for li, ln in enumerate(lines):
            sz, width = laid[li]
            line_start = phrase[ln[0]]["start"]
            parts = []
            for j, i in enumerate(ln):
                if kinds[i] == "key":
                    look = f"\\fnAnton\\fs{sz[i]}\\i1\\b0"
                    text = texts[i].upper()
                else:
                    look = f"\\fnArial\\fs{sz[i]}\\i0\\b{1 if kinds[i] == 'word' else 0}"
                    text = texts[i]
                delay = int((phrase[i]["start"] - line_start) * 1000)
                appear = f"\\alpha&HFF&\\t({delay},{delay + 90},\\alpha&H00&)" if j else ""
                parts.append(f"{{{look}{appear}}}{text}")
            pop = "\\fscx118\\fscy118\\t(0,140,\\fscx100\\fscy100)" if kinds[ln[0]] == "key" else ""
            out.append(f"Dialogue: 2,{_t(line_start)},{_t(end)},Story,,0,0,0,,{{\\an8\\pos({center_x},{int(y)})\\fad(90,120){pop}}}{' '.join(parts)}\n")
            if last_key in ln:  # the underline grows in from the left under the last big word
                k_size = sz[last_key]
                x0 = center_x - width / 2 + sum(word_w(i, sz[i]) + text_width(" ", "Arial", sz[i]) for i in ln[: ln.index(last_key)])
                bar_w = text_width(re.sub(r"[!?]+$", "", texts[last_key].upper()) or texts[last_key].upper(), "Anton", k_size)
                bar_h = max(8, int(k_size * 0.075))
                by = int(y + ascent("Anton", k_size) + k_size * 0.04)
                t0 = int((phrase[last_key]["start"] - line_start) * 1000) + 120
                out.append(f"Dialogue: 2,{_t(line_start)},{_t(end)},Story,,0,0,0,,{{\\an7\\pos({int(x0)},{by})\\p1\\c&HFFFFFF&\\bord4\\shad5"
                           f"\\fad(0,120)\\fscx0\\t({t0},{t0 + 230},\\fscx100)}}m 0 0 l {int(bar_w)} 0 l {int(bar_w)} {bar_h} l 0 {bar_h}{{\\p0}}\n")
            y += heights[li]
    return out
