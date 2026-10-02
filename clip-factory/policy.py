"""YouTube Rules Guard - checks videos against YouTube's monetization and
community rules before you upload (rules in youtube_rules.json).

  scan()          instant, no AI: swearing (with exact times, for bleeping),
                  slurs, sexual / violent / drug / dangerous wording,
                  misleading-title patterns
  ai_review()     an AI (Gemini/Groq/.../Ollama via ai.Brain) reads the title,
                  description and script against the rule book
  ai_fix()        an AI rewrites the title/description/script to be safe
  ypp_status()    which monetization tier a channel qualifies for, what's missing
  channel_risks() the channel-level risks (reused / inauthentic content...)
  check_updates() downloads YouTube's official policy pages and reports what changed

Green = looks ad-friendly, yellow = risk of limited ads, red = risk of no ads,
removal or a strike. The scan is a careful first pass, not a guarantee - YouTube
decides, and context matters (news and education get more leeway).
"""
from __future__ import annotations

import datetime as dt
import difflib
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Optional

import requests

APP_DIR = Path(__file__).resolve().parent
RULES_FILE = APP_DIR / "youtube_rules.json"
WATCH_FILE = APP_DIR / "rules_watch.json"
LEVELS = {"green": 0, "yellow": 1, "red": 2}

STRONG_SWEARS = re.compile(r"^(?:mother)?f+u+c+k+\w*$|^c+u+n+t+s?$|^f+u+k+$|^wtf$|^stfu$", re.I)
MODERATE_SWEARS = re.compile(
    r"^(?:bull)?sh+i+t+\w*$|^bitch\w*$|^ass(?:hole|holes|hat)?$|^bastards?$|^dick(?:head)?s?$|^piss(?:ed)?$|^cock(?:sucker)?s?$|^prick$|^twats?$|^wank\w*$|^douche\w*$",
    re.I)
SLURS = re.compile(r"^n+[i1]+g+(?:a|er|ah|uh)s?$|^f+[a@]+g+(?:g?[o0]ts?)?$|^retard(?:ed|s)?$|^tr[a@]nn(?:y|ies)$", re.I)

TOPICS = {
    # rule id: (words/phrases, what to say)
    "violence": (r"\b(?:kill(?:ed|ing|s)?|murder(?:ed|s)?|blood(?:y)?|gore|stabb?(?:ed|ing)?|beheaded|massacre|tortur(?:e|ed)|dead bod(?:y|ies)|shot dead)\b",
                 "violent wording - fine as news/education/story, limited ads if graphic or for shock"),
    "adult": (r"\b(?:sex(?:y|ual)?|porn\w*|nudes?|naked|onlyfans|horny|hook ?up|stripper)\b",
              "sexual wording - no ads if sexual, keep it PG-13"),
    "drugs": (r"\b(?:cocaine|meth|heroin|fentanyl|weed|marijuana|lsd|shrooms|overdos(?:e|ed)|get(?:ting)? high|smok(?:e|ing) a joint)\b",
              "drug wording - limited ads if it shows or promotes use"),
    "harmful_acts": (r"\b(?:try this at home|dangerous challenge|blackout challenge|choking challenge|almost died doing)\b",
                     "dangerous-act wording - dangerous challenges get removed"),
    "sensitive": (r"\b(?:suicide|kill (?:my|your|him|her|them)sel(?:f|ves)|self[- ]harm|terroris[mt]|terror attack|school shooting|rape[ds]?|abuse[ds]?)\b",
                  "sensitive topic - keep it respectful and non-graphic"),
    "firearms": (r"\b(?:guns?|rifles?|ammo|ar-?15|glock|pistols?)\b",
                 "firearms - fine for sport/history; no sales, building or modifying"),
}
MISLEADING_TITLE = re.compile(r"\b(?:free (?:robux|v-?bucks|money|iphone)|giveaway|not clickbait|100% real|gone sexual|(?:link|code) in bio)\b", re.I)
HARASS = re.compile(r"\b(?:kys|kill yourself|go die)\b", re.I)


def load_rules() -> dict:
    return json.loads(RULES_FILE.read_text(encoding="utf-8"))


def _clean_token(text: str) -> str:
    return re.sub(r"[^\w@'-]", "", text).strip("'-")


def _fmt(t: float) -> str:
    t = int(max(0, t))
    return f"{t // 60}:{t % 60:02d}"


def swear_strength(token: str) -> Optional[str]:
    w = _clean_token(token)
    if not w:
        return None
    if SLURS.match(w):
        return "slur"
    if STRONG_SWEARS.match(w):
        return "strong"
    if MODERATE_SWEARS.match(w):
        return "moderate"
    return None


def censor(token: str) -> str:
    """'fucking,' -> 'F******,' (keeps punctuation around it)."""
    m = re.match(r"^(\W*)(\w[\w@'-]*)(\W*)$", token)
    if not m:
        return token
    lead, word, trail = m.groups()
    return f"{lead}{word[0]}{'*' * (len(word) - 1)}{trail}"


def clean_title(title: str) -> str:
    """A title with no swear words or slurs (they limit ads even when bleeped in the video)."""
    kept = [t for t in title.split() if not swear_strength(t)]
    return re.sub(r"\s+", " ", " ".join(kept)).strip(" -:,") or "Watch this"


def _add(findings, rule, severity, where, quote, why, fix):
    findings.append({"rule": rule, "severity": severity, "where": where, "quote": quote[:120], "why": why, "fix": fix})


def scan(title: str = "", description: str = "", text: str = "", words: Optional[list[dict]] = None,
         duration: Optional[float] = None) -> dict:
    """Instant check. words (with start/end seconds) give exact times and let
    swearing be bleeped; otherwise plain text is scanned."""
    findings: list[dict] = []
    swears: list[dict] = []

    # --- title (and thumbnail text, if you put it in the title box) ---
    for token in title.split():
        s = swear_strength(token)
        if s == "slur":
            _add(findings, "hate", "red", "title", token, "A slur in the title - no ads and likely removal.", "Remove it.")
        elif s:
            _add(findings, "profanity", "yellow", "title", token,
                 "Swear words in the title limit ads, even if the video itself is fine.", "Take the swear word out of the title.")
    m = MISLEADING_TITLE.search(title)
    if m:
        _add(findings, "misleading", "yellow", "title", m.group(0),
             "Looks like clickbait/scam wording - misleading titles break the spam rules.", "Describe what really happens in the video.")
    for rule, (pattern, why) in TOPICS.items():
        m = re.search(pattern, title, re.I)
        if m:
            sev = ("red" if rule == "adult" and re.search(r"porn|nudes?|naked|onlyfans", m.group(0), re.I)
                   else "info" if rule in ("violence", "firearms") else "yellow")  # "killed him in one shot" is normal for games
            _add(findings, rule, sev, "title", m.group(0), f"In the title: {why}.", "Use calmer wording in the title.")

    # --- spoken words / script ---
    if words:
        tokens = [(w["text"], w["start"], w["end"]) for w in words]
    else:
        tokens = [(t, None, None) for t in f"{description} {text}".split()]
    body = " ".join(t for t, _, _ in tokens)
    for tok, start, end in tokens:
        s = swear_strength(tok)
        if s:
            swears.append({"word": _clean_token(tok), "strength": s, "start": start, "end": end})
    slurs = [s for s in swears if s["strength"] == "slur"]
    if slurs:
        where = ", ".join(_fmt(s["start"]) for s in slurs[:5] if s["start"] is not None) or "text"
        _add(findings, "hate", "red", where, slurs[0]["word"],
             "Slurs get no ads and can be removed with a strike - even when quoting someone.", "Cut that part out (bleeping isn't enough).")
    m = HARASS.search(body)
    if m:
        _add(findings, "hate", "red", "text", m.group(0), "Telling someone to kill themselves is harassment - removal and a strike.", "Cut that part out.")
    normal = [s for s in swears if s["strength"] != "slur"]
    if normal:
        minutes = max((duration or (tokens[-1][2] or 0) or 60) / 60, 0.5)
        rate = len(normal) / minutes
        frequent = len(normal) >= 3 and rate >= 1.5 if (duration or 0) <= 180 else rate >= 2
        sev = "yellow" if frequent else "info"
        times = ", ".join(_fmt(s["start"]) for s in normal[:6] if s["start"] is not None)
        _add(findings, "profanity", sev, times or "text", ", ".join(sorted({s['word'].lower() for s in normal}))[:80],
             f"{len(normal)} swear word{'s' if len(normal) != 1 else ''}" + (" - frequent swearing limits ads." if frequent else
             " - occasional swearing is OK (even in the first 7 seconds since July 2025)."),
             "Bleep them (Clip Factory can do it automatically)." if frequent else "Fine as is; bleeping is optional.")
    for rule, (pattern, why) in TOPICS.items():
        hits = re.findall(pattern, body, re.I)
        if hits:
            # games are full of "kill"/"shot" - only many mentions are worth a warning
            many = len(hits) >= {"adult": 1, "harmful_acts": 1, "violence": 6, "firearms": 6}.get(rule, 3)
            _add(findings, rule, "yellow" if many else "info", "text", ", ".join(sorted({h.lower() for h in hits}))[:80],
                 f"{len(hits)} mention{'s' if len(hits) != 1 else ''}: {why}.", "Check the context is calm and non-graphic.")

    verdict = "green"
    for f in findings:
        if f["severity"] in LEVELS and LEVELS[f["severity"]] > LEVELS[verdict]:
            verdict = f["severity"]
    return {"verdict": verdict, "findings": findings, "swears": swears}


# ---------- AI review / fix ----------

def _rules_brief(rules: dict) -> str:
    return "\n".join(f"- {r['id']}: {r['title']}. {r['summary']}" for r in rules["rules"])


REVIEW_PROMPT = """You are a strict YouTube policy reviewer. Check this {kind} against YouTube's monetization, advertiser-friendly and community rules (summary below, as of {as_of}).

RULES:
{rules}

TITLE: {title}
DESCRIPTION: {description}
SCRIPT / TRANSCRIPT:
{text}

Judge it like YouTube's reviewers would. Context matters: news, education and calm discussion get more leeway than content made for shock.
verdict: "green" = fully ad-friendly, "yellow" = limited ads likely, "red" = no ads, removal or a strike likely.
Answer ONLY with JSON in exactly this shape:
{{"verdict": "green", "summary": "one sentence", "issues": [{{"rule": "rule id from the list", "severity": "yellow", "quote": "exact words from the content", "why": "short reason", "fix": "concrete change"}}]}}
Use an empty issues list if there is nothing to fix."""

FIX_PROMPT = """Rewrite this YouTube {kind} so it fully follows YouTube's advertiser-friendly and community rules, keeping the meaning, the facts, the hook and the energy. Change only what's needed.

Problems found:
{issues}

RULES (summary):
{rules}

TITLE: {title}
DESCRIPTION: {description}
SCRIPT:
{text}

Answer ONLY with JSON in exactly this shape:
{{"title": "...", "description": "...", "script": "...", "changes": ["short list of what you changed"]}}
Keep a field empty if the original was empty."""


def _ask_json(brain, prompt: str, ok) -> tuple[Optional[dict], str, Optional[str]]:
    last_error = None
    for _ in range(3):
        try:
            raw, who = brain.ask(prompt)
        except Exception as exc:
            return None, "", "; ".join(getattr(brain, "problems", [])) or str(exc)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            m = re.search(r"\{.*\}", raw or "", re.S)
            try:
                data = json.loads(m.group(0)) if m else None
            except json.JSONDecodeError:
                data = None
        if isinstance(data, dict) and ok(data):
            return data, who, None
        last_error = "the AI's answer didn't make sense"
    return None, "", last_error


def ai_review(brain, title: str, description: str, text: str, kind: str = "video") -> dict:
    rules = load_rules()
    ids = {r["id"] for r in rules["rules"]} | {"other"}
    prompt = REVIEW_PROMPT.format(kind=kind, as_of=rules["as_of"], rules=_rules_brief(rules), title=title or "(none)",
                                  description=description or "(none)", text=(text or "(none)")[:24000])
    data, who, error = _ask_json(brain, prompt, lambda d: d.get("verdict") in LEVELS and isinstance(d.get("issues", []), list))
    if not data:
        return {"ok": False, "error": error}
    issues = []
    for i in data.get("issues") or []:
        if not isinstance(i, dict):
            continue
        sev = i.get("severity") if i.get("severity") in ("yellow", "red", "info") else "yellow"
        rule = i.get("rule") if i.get("rule") in ids else "other"
        issues.append({k: str(i.get(k) or "")[:300] for k in ("quote", "why", "fix")} | {"rule": rule, "severity": sev})
    return {"ok": True, "verdict": data["verdict"], "summary": str(data.get("summary") or "")[:300], "issues": issues, "by": who}


def ai_fix(brain, title: str, description: str, text: str, issues: list[dict], kind: str = "video") -> dict:
    rules = load_rules()
    issue_text = "\n".join(f"- [{i.get('rule')}] {i.get('quote', '')}: {i.get('why', '')}" for i in issues) or "- (run a general safety pass)"
    prompt = FIX_PROMPT.format(kind=kind, issues=issue_text, rules=_rules_brief(rules), title=title or "", description=description or "",
                               text=(text or "")[:24000])

    def ok(d):
        return all(isinstance(d.get(k, ""), str) for k in ("title", "description", "script")) and \
            (not title or d.get("title")) and (not text or len(d.get("script", "")) > len(text) * 0.4)
    data, who, error = _ask_json(brain, prompt, ok)
    if not data:
        return {"ok": False, "error": error}
    out = {"ok": True, "title": data.get("title", ""), "description": data.get("description", ""),
           "script": data.get("script", ""), "changes": [str(c)[:200] for c in data.get("changes") or []][:12], "by": who}
    out["check"] = scan(out["title"], out["description"], out["script"])
    return out


# ---------- channel level ----------

def ypp_status(subscribers: int, watch_hours: float, shorts_views: int, uploads_90d: int, today: Optional[dt.date] = None) -> dict:
    rules = load_rules()["ypp"]
    today = today or dt.date.today()
    change = dt.date(2027, 2, 1)
    tiers = []
    for t in rules["tiers"]:
        hours_need, shorts_need = t["watch_hours_12m"], t["shorts_views_90d"]
        future = t.get("from_2027_02_01")
        if future and today >= change:
            hours_need, shorts_need = future["watch_hours_12m"], future["shorts_views_90d"]
        missing = []
        if subscribers < t["subscribers"]:
            missing.append(f"{t['subscribers'] - subscribers:,} more subscribers")
        if uploads_90d < t["uploads_90d"]:
            missing.append(f"{t['uploads_90d'] - uploads_90d} more public uploads in the last 90 days")
        if watch_hours < hours_need and shorts_views < shorts_need:
            missing.append(f"{hours_need - watch_hours:,.0f} more watch hours (12 months) OR "
                           f"{shorts_need - shorts_views:,} more Shorts views (90 days)")
        tiers.append({"name": t["name"], "unlocks": t["unlocks"], "met": not missing, "missing": missing,
                      "needs": f"{t['subscribers']:,} subscribers"
                               + (f" + {t['uploads_90d']} uploads in 90 days" if t["uploads_90d"] else "")
                               + f" + {hours_need:,} watch hours (12 months) or {shorts_need:,} Shorts views (90 days)"})
    days_left = (change - today).days
    note = rules["change_2027"]
    if days_left > 0:
        note = f"{days_left} days until the bar doubles. " + note
    return {"tiers": tiers, "general": rules["general"], "note_2027": note}


QUESTIONS = [
    ("clips_others", "Do you upload clips of other creators' videos or streams?"),
    ("permission", "Do you have written permission from those creators (e.g. their clipping program)?"),
    ("commentary", "Do you add your own commentary, context or storyline to their clips?"),
    ("ai_voice", "Is the narration an AI / text-to-speech voice?"),
    ("template", "Do most of your videos follow the same template with only small changes?"),
    ("many_per_day", "Do you upload more than 3 videos a day?"),
    ("realistic_ai", "Do your videos show realistic AI people, voices or events?"),
    ("music", "Do you use music you didn't make or license?"),
]


def channel_risks(answers: dict) -> list[dict]:
    a = {k: bool(answers.get(k)) for k, _ in QUESTIONS}
    out = []
    if a["clips_others"]:
        if not a["permission"]:
            out.append({"rule": "copyright", "level": "red", "text": "Clipping without permission risks copyright strikes (3 = channel deleted) and claims that take your money. Only clip creators who allow it."})
        if not a["commentary"]:
            out.append({"rule": "reused", "level": "red", "text": "Plain clips of someone else's content count as reused content - the channel won't be accepted for money. Add your own commentary, context or a storyline."})
        else:
            out.append({"rule": "reused", "level": "yellow", "text": "Good - keep the commentary substantial; a title card alone isn't enough."})
    if a["template"] and (a["ai_voice"] or a["many_per_day"]):
        out.append({"rule": "inauthentic", "level": "red", "text": "Template videos with an AI voice / many uploads a day is exactly what the 'inauthentic content' rule targets. Make each video genuinely different and fewer, better uploads."})
    elif a["template"] or a["many_per_day"]:
        out.append({"rule": "inauthentic", "level": "yellow", "text": "Watch for repetition - vary formats, scripts and visuals between videos."})
    if a["ai_voice"] and not a["template"]:
        out.append({"rule": "inauthentic", "level": "yellow", "text": "AI voices are allowed, but the script must carry real, original substance - not text-to-speech over stock footage."})
    if a["realistic_ai"]:
        out.append({"rule": "ai_disclosure", "level": "yellow", "text": "Tick 'altered or synthetic content' when you upload those videos."})
    if a["music"]:
        out.append({"rule": "copyright", "level": "red", "text": "Unlicensed music gets claimed (money goes to the owner) or struck. Use YouTube Audio Library or royalty-free music."})
    if not out:
        out.append({"rule": "ok", "level": "green", "text": "No channel-level red flags from these answers."})
    return out


# ---------- official page watcher ----------

def _page_text(html_text: str) -> str:
    body = re.sub(r"(?is)<(script|style|noscript|svg|head|nav|footer)[^>]*>.*?</\1>", " ", html_text)
    m = re.search(r"(?is)<h1.*?(?:Was this helpful\?|Need more help\?)", body)
    body = m.group(0) if m else body
    body = re.sub(r"(?i)<br\s*/?>|</(p|li|h\d|div|tr)>", "\n", body)
    text = html.unescape(re.sub(r"<[^>]+>", " ", body))
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if len(ln) > 2)


def check_updates(brain=None) -> dict:
    """Fetch YouTube's official policy pages, compare with the last check."""
    rules = load_rules()
    try:
        saved = json.loads(WATCH_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        saved = {}
    results, changed_text = [], []
    for page in rules["official_pages"]:
        url = page["url"]
        try:
            resp = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"})
            resp.raise_for_status()
            text = _page_text(resp.text)
        except Exception as exc:
            results.append({"name": page["name"], "url": url, "status": "error", "detail": f"couldn't load: {exc}"[:200]})
            continue
        digest = hashlib.sha1(text.encode()).hexdigest()
        before = saved.get(url)
        now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        if not before:
            status, detail = "saved", "First check - saved today's version. Next time you'll see what changed."
        elif before["hash"] == digest:
            status, detail = "same", f"No change since {before['checked']}."
        else:
            old, new = before["text"].splitlines(), text.splitlines()
            diff = [ln for ln in difflib.unified_diff(old, new, lineterm="", n=0) if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
            status, detail = "changed", "\n".join(diff[:80])
            changed_text.append(f"== {page['name']} ==\n" + "\n".join(diff[:120]))
        saved[url] = {"hash": digest, "text": text, "checked": now}
        results.append({"name": page["name"], "url": url, "status": status, "detail": detail})
    WATCH_FILE.write_text(json.dumps(saved), encoding="utf-8")
    summary = None
    if changed_text and brain is not None:
        prompt = ("These are the changed lines (- removed, + added) on YouTube's official policy pages since the last check. "
                  "Explain in plain simple English what changed for a small YouTube creator and what they must do differently. "
                  'Answer ONLY with JSON: {"summary": ["short bullet points"]}\n\n' + "\n\n".join(changed_text)[:20000])
        data, who, _err = _ask_json(brain, prompt, lambda d: isinstance(d.get("summary"), list) and d["summary"])
        if data:
            summary = {"points": [str(s)[:300] for s in data["summary"]][:8], "by": who}
    return {"pages": results, "summary": summary}
