"""Clipping campaigns (Whop Content Rewards and similar), read from the campaign page you copy.

Whop has no public list for apps, so you open a campaign, press Ctrl+A then Ctrl+C, and paste it here.
Numbers and links are read straight from the text (never guessed); an AI, when available, adds the
plain-language rules checklist and who/what the clips must mention - and every word it suggests must
really be in the text.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
FILE = APP_DIR / "campaigns.json"
FEE = 0.10  # Whop keeps 10% of campaign payouts
PLATFORMS = {"instagram": "Instagram", "youtube": "YouTube", "tiktok": "TikTok", "x": "X"}
SOURCE_HOSTS = ("kick.com", "twitch.tv", "youtube.com", "youtu.be", "rumble.com", "x.com", "twitter.com", "instagram.com", "tiktok.com")


def load() -> list[dict]:
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save(items: list[dict]) -> None:
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=1), encoding="utf-8")
    tmp.replace(FILE)


def _money(s: str) -> float:
    return float(s.replace(",", ""))


def read_numbers(text: str) -> dict:
    """Pay, payouts, budget, platforms, links - only what is literally on the page."""
    t = text.replace(" ", " ")
    out: dict = {"cpm": {}, "min_payout": None, "max_payout": None, "budget_left": None, "budget_spent": None,
                 "sources": [], "files": [], "links": []}
    # per-platform blocks: "Instagram  Per 1K views $0.50  Min payout $2.00  Max payout $999.00"
    for key, label in PLATFORMS.items():
        pat = (r"(?is)(?:^|\n)\s*" + ("x" if key == "x" else label) + r"\s*\n?.{0,40}?per\s*1k\s*views\s*\$?\s*([\d.,]+)"
               r"(?:.{0,40}?min(?:imum)?\s*payout\s*\$?\s*([\d.,]+))?(?:.{0,40}?max(?:imum)?\s*payout\s*\$?\s*([\d.,]+))?")
        m = re.search(pat, t)
        if m:
            out["cpm"][label] = _money(m.group(1))
            if m.group(2) and out["min_payout"] is None:
                out["min_payout"] = _money(m.group(2))
            if m.group(3) and out["max_payout"] is None:
                out["max_payout"] = _money(m.group(3))
    if not out["cpm"]:
        m = re.search(r"(?i)\$\s*([\d.,]+)\s*(?:usd)?\s*(?:per|/)\s*(1k|1,000|thousand|million|1m)\b", t)
        if m:
            per_k = _money(m.group(1)) / (1000 if m.group(2).lower() in ("million", "1m") else 1)
            mentioned = [lbl for k, lbl in PLATFORMS.items() if k != "x" and re.search(r"(?i)\b" + lbl + r"\b", t)]
            for lbl in mentioned or ["All"]:
                out["cpm"][lbl] = round(per_k, 4)
    if out["min_payout"] is None:
        m = re.search(r"(?i)min(?:imum)?\s*payout\s*\$?\s*([\d.,]+)", t)
        out["min_payout"] = _money(m.group(1)) if m else None
    if out["max_payout"] is None:
        m = re.search(r"(?i)max(?:imum)?\s*payout\s*\$?\s*([\d.,]+)", t)
        out["max_payout"] = _money(m.group(1)) if m else None
    m = re.search(r"(?i)\$\s*([\d,]+(?:\.\d+)?)\s*\$\s*([\d,]+(?:\.\d+)?)\s*remaining", t) or \
        re.search(r"(?i)budget\s*\$\s*([\d,]+(?:\.\d+)?)\D{0,20}\$\s*([\d,]+(?:\.\d+)?)\s*remaining", t)
    if m:
        out["budget_spent"], out["budget_left"] = _money(m.group(1)), _money(m.group(2))
    else:
        m = re.search(r"(?i)\$\s*([\d,]+(?:\.\d+)?)\s*(?:remaining|left|still up for grabs)", t)
        out["budget_left"] = _money(m.group(1)) if m else None
    for url in dict.fromkeys(re.findall(r"https?://[^\s)\]>\"']+", t)):
        url = url.rstrip(".,;")
        host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0].lower()
        if any(host == h or host.endswith("." + h) for h in SOURCE_HOSTS):
            out["sources"].append(url)
        elif "drive.google" in host or "dropbox" in host or "docs.google" in host:
            out["files"].append(url)
        else:
            out["links"].append(url)
    return out


NOT_NAMES = {"requirements", "requirement", "rules", "guidelines", "content", "clips", "clip", "caption", "captions",
             "the", "your", "this", "violations", "brief", "campaign", "videos", "video"}


def _words_in(text: str, words) -> list[str]:
    """Only keep names that really appear in the campaign text (the AI must not invent rules)."""
    out = []
    for w in words or []:
        w = str(w or "").strip().strip("@#.,:;!")
        if w and w.lower() not in NOT_NAMES and re.search(r"(?i)\b" + re.escape(w) + r"\b", text) and w.lower() not in {x.lower() for x in out}:
            out.append(w[:40])
    return out[:5]


def read_rules(text: str) -> dict:
    """The rules without AI: must/never mention, watermark, hashtags, kind."""
    t = text
    must = re.findall(r"(?i)must\s+(?:mention|tag|include|name)\s+@?([A-Z][\w.]{1,30})", t)
    ban = []
    for m in re.finditer(r"(?i)(?:do\s*not|don'?t|never|no)\s+(?:mention|tag|include|show)\s+([^\n.]{1,60})", t):
        ban += [w.strip(" @#\"'") for w in re.split(r",|\bor\b|\band\b|/", m.group(1)) if w.strip()]
    focus = re.findall(r"(?i)(?:must\s+)?feature\s+@?([A-Z][\w.]{1,30})\s+in\s+a\s+relevant\s+way", t) + \
        re.findall(r"(?i)^\s*clip\s+@?([A-Z][\w.]{1,30})", t, re.M)
    hashtags = list(dict.fromkeys(h for h in re.findall(r"#(\w{2,30})", t) if not h.isdigit()))[:6]
    kind = "stream" if re.search(r"(?i)\b(livestream|live stream|stream|kick|twitch|vod)\b", t) else \
        "podcast" if re.search(r"(?i)\bpodcast\b", t) else ""
    name = ""
    m = re.search(r"(?im)^\s*(.{3,80}?)\s*\n\s*\$[\d,.]+\s*(?:usd)?\s*per\s*(?:million|1k)", t)
    if m:
        name = m.group(1).strip()
    lines = t.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip().lower() in ("brief", "rules", "requirements", "guidelines")), 0)
    rules, section = [], ""
    for ln in lines[start:]:
        ln = ln.strip(" •*-\t")
        if not ln or "http" in ln:
            continue
        if ln.endswith(":") and len(ln.split()) <= 4:  # a heading like "Caption Requirements:"
            section = ln.lower()
            continue
        ln = ln.rstrip(":")
        if len(ln.split()) >= 4:
            rules.append(("Not allowed: " if "violation" in section else "") + ln)
    return {"must": _words_in(t, must), "ban": _words_in(t, ban), "focus": _words_in(t, focus), "hashtags": hashtags,
            "watermark": bool(re.search(r"(?i)watermark|logo", t)), "kind": kind, "name": name,
            "rules": [r[:220] for r in dict.fromkeys(rules) if len(r) > 8][:20]}


AI_PROMPT = """This is the text of a clipping campaign page (people get paid per 1,000 views for posting clips of a creator).
Read it and answer ONLY with JSON:
{{"name": "campaign name", "creator": "who the clips are about",
  "must_mention": ["names every caption/title must mention"], "never_mention": ["names that must not be mentioned"],
  "focus": ["who must be in the clips"], "hashtags": ["required hashtags without #"], "tag_accounts": ["@accounts to tag"],
  "kind": "stream" or "podcast" or "other",
  "checklist": ["every rule a clipper must follow, one short plain sentence each"],
  "watch_out": ["the rules most likely to get a clip rejected"]}}
Use only what the text says. Leave a list empty if the text doesn't say it.

Campaign text:
{text}
"""


def read_with_ai(text: str, brain) -> dict:
    if brain is None:
        return {}
    for _ in range(2):
        try:
            raw, who = brain.ask(AI_PROMPT.format(text=text[:9000]))
            m = re.search(r"\{.*\}", raw or "", re.S)
            d = json.loads(m.group(0)) if m else {}
        except Exception:
            continue
        if isinstance(d, dict) and (d.get("checklist") or d.get("name")):
            d["by"] = who
            return d
    return {}


def score(c: dict) -> dict:
    """Is it worth it? A verdict with reasons, from the numbers only."""
    cpms = [v for v in c["cpm"].values() if v]
    best = max(cpms) if cpms else None
    reasons, points = [], 0
    if best is None:
        reasons.append("Couldn't find the pay per 1,000 views - check the page.")
    else:
        net = best * (1 - FEE)
        reasons.append(f"Pays ${best:.2f} per 1,000 views (${net:.2f} after Whop's 10%).")
        points += 2 if best >= 1.5 else 1 if best >= 0.75 else 0
    if c.get("min_payout") and best:
        need = int(c["min_payout"] / best * 1000)
        c["views_to_pay"] = need
        reasons.append(f"A clip needs about {need:,} views before it pays anything.")
        points += 1 if need <= 3000 else 0
    left = c.get("budget_left")
    if left is not None:
        spent = c.get("budget_spent") or 0
        burn = spent / (spent + left) if (spent + left) else 0
        c["burn"] = round(burn * 100)
        if left < 100:
            reasons.append(f"Only ${left:,.0f} left - it will end soon.")
            points -= 2
        else:
            reasons.append(f"${left:,.0f} still to pay out ({c['burn']}% used).")
            points += 2 if left >= 500 and burn < 0.5 else 1
    n_plat = len([k for k in c["cpm"] if k != "All"]) or (4 if "All" in c["cpm"] else 0)
    if n_plat:
        reasons.append(f"Pays on {n_plat} platform{'s' if n_plat != 1 else ''}: {', '.join(c['cpm'])} - post each clip on all of them.")
        points += 1 if n_plat >= 3 else 0
    if best:
        est = 10 * max(1, n_plat) * 10_000 / 1000 * best * (1 - FEE)
        c["example"] = f"Example: 10 clips with 10K views on each platform = about ${est:,.0f}."
    verdict = "Good" if points >= 5 else "OK" if points >= 3 else "Skip"
    return {"verdict": verdict, "points": points, "reasons": reasons}


def add(text: str, brain=None) -> dict:
    text = (text or "").strip()
    if len(text) < 40:
        raise ValueError("Paste the whole campaign page (Ctrl+A, then Ctrl+C on the campaign).")
    c = {"id": uuid.uuid4().hex[:8], "added": time.strftime("%Y-%m-%d %H:%M"), "text": text[:20000]}
    c.update(read_numbers(text))
    rules = read_rules(text)
    ai = read_with_ai(text, brain)
    c["name"] = str(ai.get("name") or rules["name"] or "Campaign").strip()[:80]
    c["creator"] = str(ai.get("creator") or "").strip()[:60] if _words_in(text, [ai.get("creator")]) else ""
    c["must"] = _words_in(text, list(ai.get("must_mention") or []) + rules["must"])
    c["ban"] = _words_in(text, list(ai.get("never_mention") or []) + rules["ban"])
    c["focus"] = _words_in(text, list(ai.get("focus") or []) + rules["focus"] + ([c["creator"]] if c["creator"] else []))
    c["hashtags"] = [h for h in dict.fromkeys(list(ai.get("hashtags") or []) + rules["hashtags"])
                     if re.search(r"(?i)#?" + re.escape(str(h).lstrip("#")), text)][:6]
    c["tag_accounts"] = _words_in(text, ai.get("tag_accounts") or [])
    c["kind"] = ai.get("kind") if ai.get("kind") in ("stream", "podcast") else rules["kind"]
    c["watermark"] = rules["watermark"]
    c["checklist"] = [str(x)[:220] for x in ai.get("checklist") or []][:15] or rules["rules"]
    c["watch_out"] = [str(x)[:220] for x in ai.get("watch_out") or []][:5]
    c["read_by"] = ai.get("by") or "built-in reader"
    c.update(score(c))
    items = [x for x in load() if x.get("text") != c["text"]] + [c]
    save(items)
    return c


def remove(cid: str) -> None:
    save([c for c in load() if c["id"] != cid])


def ranked() -> list[dict]:
    order = {"Good": 0, "OK": 1, "Skip": 2}
    return sorted((dict(c, text=None) for c in load()), key=lambda c: (order.get(c.get("verdict"), 3), -c.get("points", 0)))
