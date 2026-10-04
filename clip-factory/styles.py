"""Caption styles, made like the ones on viral Shorts / TikToks / Reels (and emoji pops).

  hormozi  Montserrat Black, ALL CAPS, thick black outline, 2-3 words at a time, ONE key word per chunk in
           yellow (green for money and numbers); each chunk snaps in
  beast    the MrBeast look: comic font, 1-2 huge words, heavy outline and hard shadow, every chunk pops in
           tilted a little, the key word in colour
  highlight  karaoke: 2-3 words, the word being said lights up green
  box      the word being said sits in a coloured box (TikTok look)
  iman     clean and calm (Iman Gadzhi look): lowercase white Montserrat, words turn bold as they're said
  story    kinetic typography (podcast look): key words huge and slanted, small words small, lines build up
           word by word, a thick underline grows under the last big word
Fonts in fonts/: Montserrat, Anton, Bangers (all SIL Open Font License).
Emoji pops: an emoji jumps in above the captions when a matching word is said (laugh -> 😂, money -> 💰...).
Emoji pictures: Twemoji by Twitter, Inc. and contributors, CC-BY 4.0 (see emoji/LICENSE.txt).
"""
from __future__ import annotations

import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
EMOJI_DIR = APP_DIR / "emoji"
FONTS_DIR = APP_DIR / "fonts"
STYLES = ("hormozi", "beast", "highlight", "box", "iman", "story")
ALIASES = {"pop": "hormozi"}  # older saved settings

# ASS colours are &HAABBGGRR
WHITE, YELLOW, GREEN, BLACK = "&H00FFFFFF&", "&H0000E5FF&", "&H0040FF4D&", "&H00000000&"
RED, VIOLET = "&H004B4BFF&", "&H00F65C8B&"
SMALL = {"is", "a", "an", "the", "to", "of", "and", "or", "in", "on", "at", "it", "its", "be", "so", "but", "for", "with",
         "that", "this", "was", "are", "am", "as", "if", "by", "from", "up", "into", "than", "then", "do", "did", "just",
         "i", "you", "he", "she", "we", "they", "me", "my", "your", "his", "her", "our", "their", "them", "us", "not"}
STRONG = {"never", "always", "everything", "nothing", "everyone", "nobody", "best", "worst", "biggest", "first", "last",
          "crazy", "insane", "million", "billion", "money", "dead", "died", "love", "hate", "secret", "truth", "lie",
          "fired", "rich", "broke", "free", "banned", "war", "fight", "won", "lost", "win", "lose", "only", "real",
          "fake", "huge", "impossible", "dangerous", "scared", "angry", "shocked", "why", "how", "stop", "quit"}
MONEY = re.compile(r"(?i)[\d$%€£]|money|cash|million|billion|rich|paid|dollars?")
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
MAX_W = 940  # the widest a caption line may be (the screen is 1080)


def clean(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def caps(text: str) -> str:
    """ALL CAPS without full stops and commas (viral captions don't show them; ? and ! stay)."""
    t = clean(text).upper()
    return t.rstrip(".,;:") or t


def _bare(word: str) -> str:
    return re.sub(r"[^\w$%']", "", word.lower())


def strong(word: str) -> bool:
    w = _bare(word)
    return bool(re.search(r"[\d$%]", word)) or w in STRONG or len(w) >= 9


def key_index(group: list[dict]) -> int:
    """The one word of a chunk worth colouring: a strong word, else the longest real word (or none)."""
    best, score = -1, 0
    for i, w in enumerate(group):
        b = _bare(w["text"])
        if not b or b in SMALL:
            continue
        s = (100 if strong(w["text"]) else 0) + len(b)
        if s > score and (strong(w["text"]) or len(b) >= 4):
            best, score = i, s
    return best


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


# ---------- measuring text (so lines fit the screen and underlines match their word) ----------

FONTS = {  # ASS font name, its file
    "black": ("Montserrat Black", "Montserrat-Black.ttf"),
    "black_i": ("Montserrat Black", "Montserrat-BlackItalic.ttf"),
    "xbold": ("Montserrat ExtraBold", "Montserrat-ExtraBold.ttf"),
    "medium": ("Montserrat Medium", "Montserrat-Medium.ttf"),
    "medium_i": ("Montserrat Medium", "Montserrat-MediumItalic.ttf"),
    "xbold_i": ("Montserrat ExtraBold", "Montserrat-ExtraBoldItalic.ttf"),
    "comic": ("Bangers", "Bangers-Regular.ttf"),
    "anton": ("Anton", "Anton-Regular.ttf"),
}
_font_cache: dict = {}


def _font(key: str):
    """(PIL font at size 100, em per unit of ASS font size, baseline as a share of the line) or None."""
    if key not in _font_cache:
        import struct
        from PIL import ImageFont
        _font_cache[key] = None
        p = FONTS_DIR / FONTS[key][1]
        try:
            f = ImageFont.truetype(str(p), 100)
            d = p.read_bytes()
            tables = {d[12 + 16 * i: 16 + 16 * i]: struct.unpack(">I", d[20 + 16 * i: 24 + 16 * i])[0]
                      for i in range(struct.unpack(">H", d[4:6])[0])}
            upem = struct.unpack(">H", d[tables[b"head"] + 18: tables[b"head"] + 20])[0]
            win_a, win_d = struct.unpack(">HH", d[tables[b"OS/2"] + 74: tables[b"OS/2"] + 78])
            # libass makes the ASS font size = the font's Windows line height (winAscent + winDescent)
            _font_cache[key] = (f, upem / (win_a + win_d), win_a / (win_a + win_d))
        except (OSError, KeyError, ValueError, struct.error):
            pass
    return _font_cache[key]


def em(key: str, px: float) -> int:
    """The ASS font size that makes letters `px` pixels per em (how designers size fonts)."""
    f = _font(key)
    return round(px / (f[1] if f else 0.8))


def ascent(key: str, fs: float) -> float:
    f = _font(key)
    return fs * (f[2] if f else 0.8)


def text_width(text: str, key: str, fs: float) -> float:
    """Width in screen pixels of text at ASS font size fs."""
    f = _font(key)
    if f is None:
        return len(text) * fs * 0.5
    return f[0].getlength(text) / 100 * fs * f[1]


def _t(seconds: float) -> str:
    cs = int(round(max(0.0, seconds) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _chunks(words: list[dict], key: str, fs: int, max_words: int, caps: bool, max_w: float = MAX_W) -> list[list[dict]]:
    """Words in chunks that fit on one line at this size, never across the end of a sentence or a pause."""
    out, cur = [], []
    for w in words:
        test = " ".join(clean(x["text"]) for x in cur + [w])
        if cur and (len(cur) >= max_words or text_width(test.upper() if caps else test, key, fs) > max_w
                    or w["start"] - cur[-1]["end"] > 0.6):
            carry = []
            if len(cur) > 1 and _bare(cur[-1]["text"]) in SMALL and w["start"] - cur[-1]["end"] <= 0.6:
                carry = [cur.pop()]  # "ANYONE PAY / A MILLION", not "ANYONE PAY A / MILLION"
            out.append(cur)
            cur = carry
        cur.append(w)
        if re.search(r"[.!?]['\")]*$", w["text"].strip()):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _ends(chunks: list[list[dict]], duration: float) -> list[tuple[float, float]]:
    """(start, end) per chunk: it stays up through short pauses, never over the next one."""
    out = []
    for g, ch in enumerate(chunks):
        a = ch[0]["start"]
        b = min(chunks[g + 1][0]["start"] if g + 1 < len(chunks) else duration, ch[-1]["end"] + 0.5, duration)
        out.append((a, max(b, a + 0.25)))
    return out


def _fit(text: str, key: str, fs: int, max_w: float = MAX_W) -> int:
    w = text_width(text, key, fs)
    return fs if w <= max_w else max(30, int(fs * max_w / w))


def _ev(layer: int, a: float, b: float, style: str, text: str) -> str:
    return f"Dialogue: {layer},{_t(a)},{_t(b)},{style},,0,0,0,,{text}\n"


def styles_block() -> str:
    """The ASS styles (font sizes here are overridden per line)."""
    b, x, m, c = FONTS["black"][0], FONTS["xbold"][0], FONTS["medium"][0], FONTS["comic"][0]
    return (
        f"Style: Hormozi,{b},100,{WHITE},&H000000FF&,{BLACK},&H99000000&,0,0,0,0,100,100,0,0,1,9,4,5,40,40,0,1\n"
        f"Style: Beast,{c},150,{WHITE},&H000000FF&,{BLACK},{BLACK},0,0,0,0,100,100,2,0,1,12,8,5,40,40,0,1\n"
        f"Style: Karaoke,{b},100,{WHITE},&H000000FF&,{BLACK},&H99000000&,0,0,0,0,100,100,0,0,1,8,4,5,40,40,0,1\n"
        f"Style: BoxBg,{b},100,&HFF000000&,&H000000FF&,{VIOLET},{VIOLET},0,0,0,0,100,100,0,0,3,18,0,5,40,40,0,1\n"
        f"Style: BoxText,{b},100,{WHITE},&H000000FF&,{BLACK},&H99000000&,0,0,0,0,100,100,0,0,1,6,3,5,40,40,0,1\n"
        f"Style: Iman,{x},80,{WHITE},&H000000FF&,&H50000000&,&H90000000&,0,0,0,0,100,100,0,0,1,3,3,5,40,40,0,1\n"
        f"Style: Post,{m},60,{WHITE},&H000000FF&,{BLACK},{BLACK},0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n"
        f"Style: Story,{m},80,{WHITE},&H000000FF&,{BLACK},&H90000000&,0,0,0,0,100,100,0,0,1,6,4,8,0,0,0,1\n"
    )


def _pos(x: int, y: int, an: int) -> str:
    return f"\\an{an}\\pos({x},{y})"


# ---------- the styles ----------

def hormozi_events(words, duration, x, y, an, scale=1.0) -> list[str]:
    fs = em("black", 92 * scale)
    chunks = _chunks(words, "black", fs, 3, True)
    out = []
    for ch, (a, b) in zip(chunks, _ends(chunks, duration)):
        k = key_index(ch)
        parts = []
        for j, w in enumerate(ch):
            colour = (GREEN if MONEY.search(w["text"]) else YELLOW) if j == k else WHITE
            parts.append(f"{{\\c{colour}}}{caps(w['text'])}")
        snap = "\\fscx82\\fscy82\\t(0,80,\\fscx107\\fscy107)\\t(80,150,\\fscx100\\fscy100)"
        out.append(_ev(2, a, b, "Hormozi", f"{{{_pos(x, y, an)}\\fs{fs}{snap}}}{' '.join(parts)}"))
    return out


def beast_events(words, duration, x, y, an, scale=1.0) -> list[str]:
    fs = em("comic", 150 * scale)
    chunks = _chunks(words, "comic", fs, 2, True)
    accents = [YELLOW, GREEN, RED, YELLOW]
    out = []
    for g, (ch, (a, b)) in enumerate(zip(chunks, _ends(chunks, duration))):
        text = " ".join(caps(w["text"]) for w in ch)
        size = _fit(text, "comic", fs)
        k = key_index(ch)
        parts = [f"{{\\c{accents[g % len(accents)]}}}{caps(w['text'])}{{\\c{WHITE}}}" if j == k
                 else caps(w["text"]) for j, w in enumerate(ch)]
        tilt = (-4, 3, -2, 4)[g % 4]
        pop = "\\fscx150\\fscy150\\t(0,110,\\fscx92\\fscy92)\\t(110,170,\\fscx100\\fscy100)"
        out.append(_ev(2, a, b, "Beast", f"{{{_pos(x, y, an)}\\fs{size}\\frz{tilt}{pop}}}{' '.join(parts)}"))
    return out


def karaoke_events(words, duration, x, y, an, scale=1.0) -> list[str]:
    fs = em("black", 84 * scale)
    chunks = _chunks(words, "black", fs, 3, True)
    out = []
    for ch, (a, b) in zip(chunks, _ends(chunks, duration)):
        texts = [caps(w["text"]) for w in ch]
        for k, w in enumerate(ch):
            w_a = a if k == 0 else w["start"]
            w_b = ch[k + 1]["start"] if k + 1 < len(ch) else b
            if w_b - w_a <= 0.01:
                continue
            shown = " ".join(f"{{\\c{GREEN}}}{t}{{\\c{WHITE}}}" if j == k else t for j, t in enumerate(texts))
            snap = "\\fscx90\\fscy90\\t(0,90,\\fscx100\\fscy100)" if k == 0 else ""
            out.append(_ev(2, w_a, w_b, "Karaoke", f"{{{_pos(x, y, an)}\\fs{fs}{snap}}}{shown}"))
    return out


def box_events(words, duration, x, y, an, scale=1.0) -> list[str]:
    fs = em("black", 84 * scale)
    chunks = _chunks(words, "black", fs, 3, True, MAX_W - 60)
    out = []
    for ch, (a, b) in zip(chunks, _ends(chunks, duration)):
        texts = [caps(w["text"]) for w in ch]
        pos = f"{{{_pos(x, y, an)}\\fs{fs}}}"
        for k, w in enumerate(ch):
            w_a = a if k == 0 else w["start"]
            w_b = ch[k + 1]["start"] if k + 1 < len(ch) else b
            if w_b - w_a <= 0.01:
                continue
            # the box layer draws a box only behind the spoken word (the other words are invisible there)
            box = " ".join(f"{{\\3a&H00&}}{t}" if j == k else f"{{\\3a&HFF&}}{t}" for j, t in enumerate(texts))
            out.append(_ev(1, w_a, w_b, "BoxBg", pos + box))
            out.append(_ev(2, w_a, w_b, "BoxText", pos + " ".join(texts)))
    return out


def iman_events(words, duration, x, y, an, scale=1.0) -> list[str]:
    fs = em("xbold", 66 * scale)
    chunks = _chunks(words, "xbold", fs, 5, False)
    xb, md = FONTS["xbold"][0], FONTS["medium"][0]
    out = []
    for ch, (a, b) in zip(chunks, _ends(chunks, duration)):
        texts = [clean(w["text"]).lower() for w in ch]
        for k, w in enumerate(ch):
            w_a = a if k == 0 else w["start"]
            w_b = ch[k + 1]["start"] if k + 1 < len(ch) else b
            if w_b - w_a <= 0.01:
                continue
            # said words bold and white, the rest light and a little see-through
            shown = " ".join(f"{{\\fn{xb}\\alpha&H00&}}{t}" if j <= k else f"{{\\fn{md}\\alpha&H55&}}{t}"
                             for j, t in enumerate(texts))
            fade = "\\fad(120,0)" if k == 0 else ""
            out.append(_ev(2, w_a, w_b, "Iman", f"{{{_pos(x, y, an)}\\fs{fs}\\blur1{fade}}}{shown}"))
    return out


def _phrases(words: list[dict], max_words: int = 7) -> list[list[dict]]:
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if not nxt or re.search(r"[.!?,;:]$", w["text"].strip()) or (nxt["start"] - w["end"]) > 0.5 or len(cur) >= max_words:
            out.append(cur)
            cur = []
    return out


def story_events(words: list[dict], duration: float, top: int, bottom: int, center_x: int = 540, scale: float = 1.0) -> list[str]:
    """Kinetic typography, centred: each phrase builds up word by word, e.g.
         PROCRASTINATING      <- key word: huge, heavy, slanted
            is choosing       <- normal words together, small words smaller and lighter
           to DELAY           <- the punchline big too, a thick yellow underline grows in under it
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
        # other words go two by two ("is choosing"), and a small word starts a line, never ends one
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
                    lines.append(cur)
                    cur = []
                cur.append(i)
                if k == "word" and (sum(kinds[j] == "word" for j in cur) >= 3 or len(cur) >= 4):
                    lines.append(cur)
                    cur = []
        if cur:
            if lines and "key" not in [kinds[j] for j in lines[-1]] and len(lines[-1]) + len(cur) <= 4:
                lines[-1] += cur
            else:
                lines.append(cur)

        font = {"key": "black_i", "word": "xbold", "small": "medium"}

        def shown(i):
            return texts[i].upper() if kinds[i] == "key" else texts[i].lower()

        def word_w(i, fs):
            return text_width(shown(i), font[kinds[i]], fs)

        def line_width(ln, sz):
            return sum(word_w(i, sz[i]) for i in ln) + sum(text_width(" ", "medium", sz[i]) for i in ln[1:])

        def sizes(ln):
            sz = {}
            for i in ln:
                if kinds[i] == "key":
                    sz[i] = min(em("black_i", 150 * scale), int(100 * MAX_W / max(1.0, text_width(shown(i), "black_i", 100) * 1.04)))
                else:
                    sz[i] = em("xbold", 74 * scale) if kinds[i] == "word" else em("medium", 56 * scale)
            while line_width(ln, sz) > MAX_W and min(sz.values()) > 40:
                sz = {i: int(v * 0.92) for i, v in sz.items()}
            return sz, line_width(ln, sz)

        laid = [sizes(ln) for ln in lines]
        heights = [max(sz.values()) * (0.92 if any(kinds[i] == "key" for i in ln) else 1.0) + (26 if last_key in ln else 0)
                   for ln, (sz, _) in zip(lines, laid)]
        y = max(top, int((top + bottom) / 2 - sum(heights) / 2))
        for li, ln in enumerate(lines):
            sz, width = laid[li]
            line_start = phrase[ln[0]]["start"]
            parts = []
            for j, i in enumerate(ln):
                look = f"\\fn{FONTS[font[kinds[i]]][0]}\\fs{sz[i]}\\i{1 if kinds[i] == 'key' else 0}"
                delay = int((phrase[i]["start"] - line_start) * 1000)
                appear = f"\\alpha&HFF&\\t({delay},{delay + 90},\\alpha&H00&)" if j else ""
                parts.append(f"{{{look}{appear}}}{shown(i)}")
            pop = "\\fscx115\\fscy115\\t(0,140,\\fscx100\\fscy100)" if kinds[ln[0]] == "key" else ""
            out.append(_ev(2, line_start, end, "Story", f"{{\\an8\\pos({center_x},{int(y)})\\fad(90,120){pop}}}{' '.join(parts)}"))
            if last_key in ln:  # the underline grows in from the left under the last big word
                k_size = sz[last_key]
                x0 = center_x - width / 2 + sum(word_w(i, sz[i]) + text_width(" ", "medium", sz[i]) for i in ln[: ln.index(last_key)])
                bar_w = text_width(re.sub(r"[!?]+$", "", shown(last_key)) or shown(last_key), "black_i", k_size)
                bar_h = max(8, int(k_size * 0.07))
                by = int(y + ascent("black_i", k_size) + k_size * 0.05)
                t0 = int((phrase[last_key]["start"] - line_start) * 1000) + 120
                out.append(_ev(2, line_start, end, "Story", f"{{\\an7\\pos({int(x0)},{by})\\p1\\c{YELLOW}\\bord3\\shad3"
                               f"\\fad(0,120)\\fscx0\\t({t0},{t0 + 230},\\fscx100)}}m 0 0 l {int(bar_w)} 0 l {int(bar_w)} {bar_h} l 0 {bar_h}{{\\p0}}"))
            y += heights[li]
    return out


POST_BLUE = "&H00FF9F4D&"  # #4D9FFF, the blue of the key phrases


def _post_words(text: str) -> list[tuple[str, bool]]:
    """("word", bold?) - **phrases** are bold."""
    out, bold = [], False
    for part in re.split(r"(\*\*)", clean(text)):
        if part == "**":
            bold = not bold
            continue
        for w in part.split():
            if out and not re.search(r"\w", w) and not w.startswith(("\u201c", '"', "(")):
                out[-1] = (out[-1][0] + w, out[-1][1])  # "neurons," not "neurons ,"
            else:
                out.append((w, bold))
    return out


def post_events(paragraphs: list[str], ending: str, duration: float, top: int, bottom: int,
                left: int = 84, right: int = 110, scale: float = 1.0) -> list[str]:
    """The story text under the video: paragraphs with bold blue key phrases, a blue bar beside the first one,
    and the call to action in italics. The font shrinks until it all fits between top and bottom."""
    width = 1080 - left - right
    blocks = [(p, False) for p in paragraphs if p.strip()] + ([(ending, True)] if ending.strip() else [])
    px = round(50 * scale)
    while True:
        fs = em("medium", px)
        line_h = round(fs * 0.98)
        laid, y = [], 0
        for text, italic in blocks:
            lines, cur, cur_w = [], [], 0.0
            for w, bold in _post_words(text):
                key = ("xbold" if bold else "medium") + ("_i" if italic else "")
                ww = text_width(w, key, fs)
                space = text_width(" ", key, fs) if cur else 0
                if cur and cur_w + space + ww > width:
                    lines.append(cur)
                    cur, cur_w, space = [], 0.0, 0
                cur.append((w, bold))
                cur_w += space + ww
            if cur:
                lines.append(cur)
            laid.append((lines, italic, y))
            y += len(lines) * line_h + round(line_h * 0.62)
        total = y - round(line_h * 0.62)
        if top + total <= bottom or px <= 30:
            break
        px -= 2
    out = []
    for b, (lines, italic, y0) in enumerate(laid):
        for li, line in enumerate(lines):
            parts, prev = [], None
            for w, bold in line:
                if bold != prev:
                    look = (f"\\fn{FONTS['xbold'][0]}\\c{POST_BLUE if not italic else WHITE}" if bold
                            else f"\\fn{FONTS['medium'][0]}\\c{WHITE}")
                    parts.append(f"{{{look}\\i{1 if italic else 0}}}")
                    prev = bold
                parts.append(w + " ")
            text = "".join(parts).rstrip()
            out.append(_ev(2, 0, duration, "Post", f"{{\\an7\\pos({left},{top + y0 + li * line_h})\\fs{fs}\\fad(250,0)}}{text}"))
        if b == 0:  # the blue bar beside the first paragraph
            bar_h = len(lines) * line_h - round(line_h * 0.2)
            out.append(_ev(2, 0, duration, "Post", f"{{\\an7\\pos({left - 40},{top + y0 + round(line_h * 0.12)})\\p1\\c{POST_BLUE}\\fad(250,0)}}"
                           f"m 0 0 l 9 0 l 9 {bar_h} l 0 {bar_h}{{\\p0}}"))
    return out


SIZES = {"s": 0.8, "m": 1.0, "l": 1.2, "xl": 1.4}  # caption size setting: small, normal, big, huge


def events(style: str, words: list[dict], duration: float, x: int, y: int, an: int, story_area: tuple[int, int],
           scale: float = 1.0) -> list[str]:
    style = ALIASES.get(style, style)
    if style == "story":
        return story_events(words, duration, *story_area, center_x=x, scale=scale)
    return {"hormozi": hormozi_events, "beast": beast_events, "highlight": karaoke_events, "box": box_events,
            "iman": iman_events}[style](words, duration, x, y, an, scale)
