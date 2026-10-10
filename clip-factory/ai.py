"""Every AI in one place: free cloud AIs first, paid ones next, your PC last.

Writing down the speech:  Groq (free)  ->  OpenAI Whisper (paid)  ->  Whisper on this PC
Picking the moments:      Gemini -> Groq -> OpenRouter (free ones)
                          -> Claude -> ChatGPT -> Grok (paid, only if you add a key)
                          -> Ollama on this PC -> built-in scorer

A "Brain" asks the first AI that's available. If one is rate-limited it's
skipped for a bit; if its key is wrong or its free limit is used up it's
skipped for the rest of the run - the next one simply takes over, so a run
always finishes. Only AIs you've added a key for are used. Keys live in
ai_keys.json next to this file (this PC only).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

import requests

import moments
import transcriber

APP_DIR = Path(__file__).resolve().parent
KEYS_FILE = APP_DIR / "ai_keys.json"

# name: (label, API base address, default model, free?) - bases overridable for testing
CLOUD = {
    "gemini":     ("Gemini",     os.environ.get("CF_GEMINI_BASE", "https://generativelanguage.googleapis.com/v1beta"), "gemini-2.5-flash", True),
    "groq":       ("Groq",       os.environ.get("CF_GROQ_BASE", "https://api.groq.com/openai/v1"), "llama-3.3-70b-versatile", True),
    "openrouter": ("OpenRouter", os.environ.get("CF_OPENROUTER_BASE", "https://openrouter.ai/api/v1"), "meta-llama/llama-3.3-70b-instruct:free", True),
    "anthropic":  ("Claude",     os.environ.get("CF_ANTHROPIC_BASE", "https://api.anthropic.com/v1"), "claude-sonnet-5-5", False),
    "openai":     ("ChatGPT",    os.environ.get("CF_OPENAI_BASE", "https://api.openai.com/v1"), "gpt-5-mini", False),
    "xai":        ("Grok",       os.environ.get("CF_XAI_BASE", "https://api.x.ai/v1"), "grok-4-fast-non-reasoning", False),
    # OmniRoute: a free AI router you run on this PC - one address in front of many (free) AIs, with its own fallback
    "omniroute":  ("OmniRoute",  "http://localhost:20128/v1", "auto/best-free", True),
}
ORDER = ["gemini", "groq", "openrouter", "anthropic", "openai", "xai"]  # free first, then paid
TRANSCRIBERS = {"groq": "whisper-large-v3-turbo", "openai": "whisper-1"}  # both give word timings

DEFAULTS = {"cloud_on": False, **{f"{n}_key": "" for n in CLOUD},
            "omni_on": True, "omni_url": CLOUD["omniroute"][1], "omni_model": CLOUD["omniroute"][2]}  # used whenever it's running
CHUNK_S = 600       # audio is sent in 10-minute pieces (well under the 25 MB upload limits)
OVERLAP_S = 2.0     # each piece starts 2 s early so no word is cut in half at the seams
MAX_WAIT_S = 90     # a rate limit longer than this means "used up for now" -> next AI


class ProviderDown(Exception):
    """This AI can't be used for the rest of the run (bad key, free limit used up...)."""


class Cooldown(Exception):
    def __init__(self, seconds: float):
        super().__init__(f"rate limited for {seconds:.0f}s")
        self.seconds = seconds


class Temporary(Exception):
    """Timeout, server hiccup - worth another try."""


class AllDown(Exception):
    pass


# ---------- keys ----------

_keys_lock = threading.Lock()


def load_keys() -> dict:
    data = dict(DEFAULTS)
    try:
        saved = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            data.update({k: v for k, v in saved.items() if k in DEFAULTS})
    except (OSError, json.JSONDecodeError):
        pass
    return data


def save_keys(update: dict) -> dict:
    with _keys_lock:
        data = load_keys()
        for k in DEFAULTS:
            if k.endswith("_key") and update.get(k) is not None:
                data[k] = str(update[k]).strip()
        if "cloud_on" in update:
            data["cloud_on"] = bool(update["cloud_on"])
        if "omni_on" in update:
            data["omni_on"] = bool(update["omni_on"])
        for k in ("omni_url", "omni_model"):
            if update.get(k):
                data[k] = str(update[k]).strip()
        KEYS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data


def key_hint(key: str) -> str:
    return f"{key[:4]}...{key[-4:]}" if len(key) > 12 else ("set" if key else "")


# ---------- error handling shared by the cloud AIs ----------

def _retry_after(resp: requests.Response) -> float:
    try:
        return float(resp.headers.get("retry-after", ""))
    except ValueError:
        pass
    # "Please try again in 7m12.5s" / "retry in 34.2s"
    m = re.search(r"(?:in|after)\s+(?:(\d+)h)?(?:(\d+)m(?!s))?([\d.]+)s", resp.text)
    if m:
        return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3))
    m = re.search(r'"retryDelay":\s*"([\d.]+)s"', resp.text)
    return float(m.group(1)) if m else 30.0


def _check(resp: requests.Response, who: str) -> None:
    if resp.ok:
        return
    body = resp.text[:400]
    if resp.status_code in (401, 403):
        raise ProviderDown(f"{who} didn't accept the key - check it in AI engines")
    if resp.status_code == 402 or re.search(r"insufficient_quota|credit balance|billing|no credits", body, re.I):
        raise ProviderDown(f"{who} has no credit left on that account")
    if resp.status_code == 429:
        wait = _retry_after(resp)
        if wait > MAX_WAIT_S or (re.search(r"per day|daily|quota", body, re.I) and wait > 20):
            raise ProviderDown(f"{who}'s free limit is used up for now")
        raise Cooldown(wait)
    if resp.status_code == 413:
        raise Temporary(f"{who}: file too large")
    if resp.status_code in (503, 529):
        raise Temporary(f"{who} is overloaded right now")
    if resp.status_code >= 500:
        raise Temporary(f"{who} server error {resp.status_code}")
    raise Temporary(f"{who} error {resp.status_code}: {body}")


def _post(who: str, url: str, timeout: float, **kw) -> requests.Response:
    try:
        return requests.post(url, timeout=timeout, **kw)
    except requests.Timeout as exc:
        raise Temporary(f"{who} took too long") from exc
    except requests.ConnectionError as exc:
        raise Temporary(f"can't reach {who} - check the internet connection") from exc


def _model_gone(resp: requests.Response) -> bool:
    return resp.status_code == 404 or (resp.status_code == 400 and bool(re.search(
        r"model.{0,80}(not found|not exist|does not exist|decommission|deprecated|invalid)|model_decommissioned|model_not_found",
        resp.text, re.I)))


# ---------- the AIs that pick moments ----------

class Provider:
    name = "?"
    label = "?"
    cloud = True

    def __init__(self):
        self.down: Optional[str] = None
        self.cool_until = 0.0
        self.failures = 0
        self.used = 0

    def ask(self, prompt: str) -> str:
        raise NotImplementedError


# picks a current model when the default one has been retired (newest/best first)
def _pick(ids: list[str], name: str) -> Optional[str]:
    def newest(cands):
        return sorted(cands, reverse=True)[0] if cands else None
    skip = r"whisper|guard|tts|audio|realtime|image|vision|imagine|embed|transcribe|search|moderation|instruct|codex|compound|playai|orpheus|dall-e"
    ids = [i for i in ids if not re.search(skip, i, re.I)]
    if name == "groq":
        return next((i for i in ids if re.search(r"70b|120b|versatile", i)), ids[0] if ids else None)
    if name == "openrouter":
        free = [i for i in ids if i.endswith(":free")]
        return next((i for pref in ("llama-3.3-70b", "deepseek", "qwen", "gemma", "mistral") for i in free if pref in i),
                    free[0] if free else None)
    if name == "openai":
        gpt = [i for i in ids if i.startswith("gpt-")]
        return newest([i for i in gpt if "mini" in i and "nano" not in i]) or newest(gpt)
    if name == "xai":
        grok = [i for i in ids if "grok" in i and "code" not in i]
        return newest([i for i in grok if "fast" in i or "mini" in i]) or newest(grok)
    if name == "omniroute":  # its own routing aliases pick (and switch between) the best free models
        return next((i for pref in ("auto/best-free", "auto/best", "auto") for i in ids if i == pref), None) or \
            next((i for i in ids if i.startswith("auto")), ids[0] if ids else None)
    if name == "anthropic":
        claude = [i for i in ids if i.startswith("claude")]
        return newest([i for i in claude if "sonnet" in i]) or newest([i for i in claude if "haiku" in i]) or newest(claude)
    return None


class OpenAIStyle(Provider):
    """Groq, OpenRouter, ChatGPT and Grok all speak the same "chat completions" language."""

    def __init__(self, name: str, key: str):
        super().__init__()
        self.name = name
        self.label, self.base, self.model, _free = CLOUD[name]
        self.key = key
        self._picked = False
        self.json_mode = True
        self.temperature = name not in ("openai",)  # newer GPT models only accept their default

    def _pick_model(self) -> None:
        resp = requests.get(f"{self.base}/models", headers={"Authorization": f"Bearer {self.key}"}, timeout=20)
        _check(resp, self.label)
        model = _pick([m.get("id", "") for m in resp.json().get("data", [])], self.name)
        if not model:
            raise ProviderDown(f"{self.label} has no suitable model available")
        self.model = model

    def ask(self, prompt: str) -> str:
        for _ in range(4):
            body = {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
            if self.json_mode:
                body["response_format"] = {"type": "json_object"}
            if self.temperature:
                body["temperature"] = 0.2
            resp = _post(self.label, f"{self.base}/chat/completions", 180,
                         headers={"Authorization": f"Bearer {self.key}"}, json=body)
            if not resp.ok:
                if not self._picked and _model_gone(resp):
                    self._picked = True  # the default model was retired: pick a current one, once
                    self._pick_model()
                    continue
                if resp.status_code == 400 and self.temperature and "temperature" in resp.text:
                    self.temperature = False
                    continue
                if resp.status_code == 400 and self.json_mode and re.search(r"response_format|json", resp.text, re.I):
                    self.json_mode = False  # the prompt itself still asks for JSON only
                    continue
            _check(resp, self.label)
            try:
                return resp.json()["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                raise Temporary(f"{self.label} sent an unexpected answer") from exc
        raise Temporary(f"{self.label} model problem")


_omni_seen: dict[str, tuple[float, bool]] = {}


def omniroute_up(url: str) -> bool:
    """Is OmniRoute answering at that address? (Any answer counts, even "key needed".) Remembered for 30 s."""
    import time as _t
    url = (url or CLOUD["omniroute"][1]).rstrip("/")
    hit = _omni_seen.get(url)
    if hit and _t.time() - hit[0] < 30:
        return hit[1]
    try:
        requests.get(f"{url}/models", timeout=1.5)
        up = True
    except requests.RequestException:
        up = False
    _omni_seen[url] = (_t.time(), up)
    return up


class OmniRouteLLM(OpenAIStyle):
    """OmniRoute on this PC (or another address you set). The key is optional - only if you made one in its dashboard."""

    def __init__(self, base: str, key: str = "", model: str = ""):
        super().__init__("omniroute", key)
        self.base = (base or CLOUD["omniroute"][1]).rstrip("/")
        self.model = model or CLOUD["omniroute"][2]
        self.batch_size = 20

    def ask(self, prompt: str) -> str:
        try:
            return super().ask(prompt)
        except Temporary as exc:
            if "can't reach" in str(exc):  # not running: skip it for this run instead of waiting on it
                raise ProviderDown("OmniRoute isn't running on this PC - start it (omniroute) or untick it in AI engines") from exc
            raise


class GeminiLLM(Provider):
    name = "gemini"
    label = "Gemini"

    def __init__(self, key: str):
        super().__init__()
        self.key = key
        _l, self.base, self.model, _f = CLOUD["gemini"]
        self._picked = False

    def _pick_model(self) -> None:
        resp = requests.get(f"{self.base}/models", headers={"x-goog-api-key": self.key}, params={"pageSize": 200}, timeout=20)
        _check(resp, "Gemini")
        names = [m.get("name", "").split("/")[-1] for m in resp.json().get("models", [])
                 if "generateContent" in (m.get("supportedGenerationMethods") or [])]

        def version(n):
            m = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
            return float(m.group(1)) if m else 0.0
        plain_flash = [n for n in names if re.fullmatch(r"gemini-[\d.]+-flash", n)]
        flash = plain_flash or [n for n in names if "flash" in n and not re.search(r"image|tts|live|audio|exp|lite", n)]
        if not flash:
            raise ProviderDown("Gemini has no suitable model available")
        self.model = max(flash, key=version)

    def ask(self, prompt: str) -> str:
        for _ in range(2):
            resp = _post("Gemini", f"{self.base}/models/{self.model}:generateContent", 180,
                         headers={"x-goog-api-key": self.key},
                         json={"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                               "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}})
            if not self._picked and resp.status_code == 404:
                self._picked = True
                self._pick_model()
                continue
            _check(resp, "Gemini")
            try:
                parts = resp.json()["candidates"][0]["content"]["parts"]
                return "".join(p.get("text", "") for p in parts)
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                raise Temporary("Gemini sent an empty answer (it may have blocked the text)") from exc
        raise Temporary("Gemini model problem")


class ClaudeLLM(Provider):
    name = "anthropic"
    label = "Claude"

    def __init__(self, key: str):
        super().__init__()
        self.key = key
        _l, self.base, self.model, _f = CLOUD["anthropic"]
        self._picked = False

    def _headers(self) -> dict:
        return {"x-api-key": self.key, "anthropic-version": "2023-06-01"}

    def _pick_model(self) -> None:
        resp = requests.get(f"{self.base}/models", headers=self._headers(), params={"limit": 100}, timeout=20)
        _check(resp, "Claude")
        model = _pick([m.get("id", "") for m in resp.json().get("data", [])], "anthropic")
        if not model:
            raise ProviderDown("Claude has no suitable model available")
        self.model = model

    def ask(self, prompt: str) -> str:
        for _ in range(2):
            resp = _post("Claude", f"{self.base}/messages", 180, headers=self._headers(),
                         json={"model": self.model, "max_tokens": 4096,
                               "messages": [{"role": "user", "content": prompt}]})
            if not self._picked and _model_gone(resp):
                self._picked = True
                self._pick_model()
                continue
            _check(resp, "Claude")
            try:
                return "".join(b.get("text", "") for b in resp.json()["content"] if b.get("type") == "text")
            except (KeyError, ValueError, TypeError) as exc:
                raise Temporary("Claude sent an unexpected answer") from exc
        raise Temporary("Claude model problem")


class OllamaLLM(Provider):
    name = "ollama"
    label = "Ollama"
    cloud = False

    def __init__(self, host: str, model: str):
        super().__init__()
        self.host, self.model, self._checked = host, model, False

    def ask(self, prompt: str) -> str:
        try:
            if not self._checked:
                self.model = moments.check_ollama(self.host, self.model)
                self._checked = True
            return moments._ask_ollama(self.host, self.model, prompt, timeout=300)
        except moments.OllamaUnavailable as exc:
            raise ProviderDown(str(exc)) from exc
        except requests.Timeout as exc:
            raise Temporary("Ollama took too long") from exc
        except requests.RequestException as exc:
            raise Temporary(f"Ollama error: {exc}") from exc


def make_provider(name: str, key: str) -> Provider:
    if name == "gemini":
        return GeminiLLM(key)
    if name == "anthropic":
        return ClaudeLLM(key)
    return OpenAIStyle(name, key)


class Brain:
    """Asks the first AI that can answer right now."""

    def __init__(self, providers: list[Provider], report: Optional[Callable[[str], None]] = None):
        self.providers = providers
        self.report = report or (lambda m: None)
        self.problems: list[str] = []

    @property
    def names(self) -> list[str]:
        return [p.name for p in self.providers]

    @property
    def batch_size(self) -> int:
        # big cloud models handle more clips per question; small local ones do better with fewer
        return 12 if any(p.cloud for p in self.providers) else moments.BATCH_SIZE

    def _note(self, msg: str) -> None:
        if msg not in self.problems:
            self.problems.append(msg)
            self.report(msg)

    def ask(self, prompt: str) -> tuple[str, str]:
        for _ in range(20):
            now = time.time()
            alive = [p for p in self.providers if not p.down]
            if not alive:
                raise AllDown("no AI is available")
            ready = [p for p in alive if p.cool_until <= now]
            if not ready:
                wait = min(p.cool_until for p in alive) - now
                if wait > MAX_WAIT_S:
                    raise AllDown("every AI is rate-limited")
                time.sleep(max(0.5, wait))
                continue
            p = ready[0]
            try:
                raw = p.ask(prompt)
                p.failures = 0
                p.used += 1
                return raw, p.label
            except Cooldown as exc:
                p.cool_until = time.time() + exc.seconds
            except ProviderDown as exc:
                p.down = str(exc)
                self._note(f"{exc} - switched to the next AI")
            except Temporary as exc:
                p.failures += 1
                if p.failures >= 3:
                    p.down = str(exc)
                    self._note(f"{exc} (3 times) - switched to the next AI")
                else:
                    p.cool_until = time.time() + 3 * p.failures
        raise AllDown("no AI gave an answer")


def build_brain(settings: dict, keys: dict, report=None) -> Optional[Brain]:
    """None = don't use AI at all (the built-in scorer does everything)."""
    if not settings.get("use_ai", True):
        return None
    providers: list[Provider] = []
    if keys.get("omni_on") and omniroute_up(keys.get("omni_url")):  # your own router first, when it's running
        providers.append(OmniRouteLLM(keys.get("omni_url"), keys.get("omniroute_key", ""), keys.get("omni_model")))
    if keys.get("cloud_on"):
        providers += [make_provider(n, keys[f"{n}_key"]) for n in ORDER if keys.get(f"{n}_key")]
    providers.append(OllamaLLM(settings.get("host") or "http://localhost:11434", settings.get("model") or "llama3"))
    return Brain(providers, report)


def test_keys(keys: dict) -> dict:
    """{name: 'ok' | problem} with a tiny real request to each AI that has a key."""
    out = {}
    prompt = 'Answer ONLY with this JSON: {"ok": true}'
    if keys.get("omni_on") and not omniroute_up(keys.get("omni_url")):
        out["omniroute"] = "not running - start.bat starts it (or run: omniroute)"
    elif keys.get("omni_on"):
        try:
            raw = OmniRouteLLM(keys.get("omni_url"), keys.get("omniroute_key", ""), keys.get("omni_model")).ask(prompt)
            out["omniroute"] = "ok" if "ok" in raw.lower() else "answered, but strangely"
        except Cooldown:
            out["omniroute"] = "ok (busy right now)"
        except (ProviderDown, Temporary) as exc:
            out["omniroute"] = str(exc)
        except Exception as exc:
            out["omniroute"] = f"problem: {exc}"
    for name in ORDER:
        key = keys.get(f"{name}_key")
        if not key:
            continue
        try:
            raw = make_provider(name, key).ask(prompt)
            out[name] = "ok" if "ok" in raw.lower() else "answered, but strangely"
        except Cooldown:
            out[name] = "ok (busy right now - rate limited for a moment)"
        except (ProviderDown, Temporary) as exc:
            out[name] = str(exc)
        except Exception as exc:
            out[name] = f"problem: {exc}"
    return out


def cloud_transcribers(keys: dict) -> list[str]:
    if not keys.get("cloud_on"):
        return []
    return [n for n in TRANSCRIBERS if keys.get(f"{n}_key")]


# ---------- cloud transcription (Groq / OpenAI Whisper) ----------

def _norm(word: str) -> str:
    return re.sub(r"[^\w']", "", word.lower())


def punctuate(words: list[dict], text: str) -> list[dict]:
    """Cloud word timings come without punctuation; the full text has it.
    Line the two up so sentences can still be found."""
    tokens = text.split()
    j = 0
    out = []
    for w in words:
        target = _norm(w["text"])
        found = None
        for k in range(j, min(j + 4, len(tokens))):
            if _norm(tokens[k]) == target:
                found = k
                break
        if found is not None:
            out.append(dict(w, text=tokens[found]))
            j = found + 1
        else:
            out.append(w)
    return out


def _words_from_response(data: dict) -> list[dict]:
    words = [{"start": float(w["start"]), "end": float(w["end"]), "text": str(w.get("word", "")).strip()}
             for w in data.get("words") or [] if str(w.get("word", "")).strip()]
    if words:
        return punctuate(words, data.get("text") or "")
    # no word timings: spread each segment's words evenly over its time
    out = []
    for seg in data.get("segments") or []:
        toks = str(seg.get("text", "")).split()
        if not toks:
            continue
        start, end = float(seg["start"]), float(seg["end"])
        step = (end - start) / len(toks)
        out += [{"start": start + i * step, "end": start + (i + 1) * step, "text": t} for i, t in enumerate(toks)]
    return out


_local_lock = threading.Lock()


def _extract_chunk(video: Path, start: float, length: float, out: Path) -> None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    proc = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
         "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", "-f", "mp3", str(out)],
        capture_output=True, text=True, errors="replace", timeout=600, creationflags=flags,
    )
    if proc.returncode != 0 or not out.exists():
        raise Temporary(f"couldn't take the audio out of the video: {proc.stderr.strip()[-200:]}")


def _transcribe_file(name: str, path: Path, key: str) -> list[dict]:
    label, base = CLOUD[name][0], CLOUD[name][1]
    for attempt in range(4):
        with open(path, "rb") as f:
            resp = _post(label, f"{base}/audio/transcriptions", 300,
                         headers={"Authorization": f"Bearer {key}"},
                         files={"file": (path.name, f, "audio/mpeg")},
                         data={"model": TRANSCRIBERS[name], "response_format": "verbose_json", "temperature": "0",
                               "timestamp_granularities[]": ["word", "segment"]})
        try:
            _check(resp, label)
        except Cooldown as exc:
            time.sleep(exc.seconds + 0.5)
            continue
        except Temporary:
            if attempt >= 2:
                raise
            time.sleep(2 + attempt * 3)
            continue
        try:
            return _words_from_response(resp.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise Temporary(f"{label} sent an unexpected transcript") from exc
    raise Temporary(f"{label} stayed busy")


def cloud_transcribe(
    video: Path, duration: float, keys: dict, work_dir: Path,
    local_fallback: Callable[[Path], list[dict]],
    progress: Optional[Callable[[str, float], None]] = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[list[dict], dict]:
    """Whole-video word timings in the cloud, 3 pieces at a time. Each piece
    tries Groq, then OpenAI; any piece neither can do is done on this PC.
    Returns (words, stats)."""
    report = progress or (lambda m, p: None)
    order = cloud_transcribers(keys)
    work_dir.mkdir(parents=True, exist_ok=True)
    starts = [k * CHUNK_S for k in range(max(1, int((duration + CHUNK_S - 1) // CHUNK_S)))]
    results: dict[int, list[dict]] = {}
    stats = {"pieces": len(starts), "local": 0, "problem": None, "by": {}}
    down: dict[str, str] = {}

    def do_piece(k: int) -> tuple[int, list[dict], str]:
        if cancelled():
            raise transcriber.Cancelled()
        nominal = starts[k]
        audio_start = max(0.0, nominal - (OVERLAP_S if k else 0.0))
        length = min(CHUNK_S + OVERLAP_S, duration - audio_start + 1)
        piece = work_dir / f"piece_{k:03d}.mp3"
        _extract_chunk(video, audio_start, length, piece)
        words, how = None, "this PC"
        for name in order:
            if name in down:
                continue
            try:
                words, how = _transcribe_file(name, piece, keys[f"{name}_key"]), CLOUD[name][0]
                break
            except ProviderDown as exc:
                down[name] = str(exc)
                stats["problem"] = str(exc)
            except Temporary as exc:
                stats["problem"] = str(exc)
        if words is None:
            with _local_lock:  # one local Whisper at a time - the PC can't run three at once
                words = local_fallback(piece)
        piece.unlink(missing_ok=True)
        # back to whole-video time; each piece keeps only its own stretch (seams sit 1 s
        # inside the overlap, so every word comes from a piece that heard all of it)
        lo = nominal - OVERLAP_S / 2 if k else -1.0
        hi = starts[k + 1] - OVERLAP_S / 2 if k + 1 < len(starts) else float("inf")
        shifted = [dict(w, start=w["start"] + audio_start, end=w["end"] + audio_start) for w in words]
        return k, [w for w in shifted if lo <= w["start"] < hi], how

    done = 0
    report(f"Sending the audio to the cloud in {len(starts)} piece{'s' if len(starts) != 1 else ''}...", 0)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(do_piece, k) for k in range(len(starts))]
        try:
            for fut in as_completed(futures):
                k, words, how = fut.result()
                results[k] = words
                stats["by"][how] = stats["by"].get(how, 0) + 1
                if how == "this PC":
                    stats["local"] += 1
                done += 1
                report(f"Transcribing in the cloud: {done} of {len(starts)} pieces done", done / len(starts) * 100)
        except BaseException:
            for f in futures:
                f.cancel()
            raise
    words = [w for k in sorted(results) for w in results[k]]
    words.sort(key=lambda w: w["start"])
    return words, stats


# ---------- AIs that can look at pictures (to read the style of an example video) ----------

VISION_MODELS = {"groq": "meta-llama/llama-4-scout-17b-16e-instruct", "openai": "gpt-4o-mini",
                 "openrouter": "google/gemini-2.0-flash-exp:free"}


def look(keys: dict, prompt: str, jpegs: list[bytes]) -> Optional[tuple[str, str]]:
    """(answer, who) from the first AI that can see pictures, or None. Gemini first (free), then the others."""
    import base64
    pics = [base64.b64encode(j).decode() for j in jpegs]
    if not keys.get("cloud_on"):
        return None
    if keys.get("gemini_key"):
        try:
            g = GeminiLLM(keys["gemini_key"])
            for _ in range(2):
                resp = _post("Gemini", f"{g.base}/models/{g.model}:generateContent", 180, headers={"x-goog-api-key": g.key},
                             json={"contents": [{"role": "user", "parts": [{"text": prompt}] + [
                                 {"inline_data": {"mime_type": "image/jpeg", "data": p}} for p in pics]}],
                                   "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}})
                if resp.status_code == 404 and not g._picked:
                    g._picked = True
                    g._pick_model()
                    continue
                _check(resp, "Gemini")
                parts = resp.json()["candidates"][0]["content"]["parts"]
                return "".join(p.get("text", "") for p in parts), "Gemini"
        except Exception:
            pass
    for name in ("openai", "groq", "openrouter"):
        if not keys.get(f"{name}_key"):
            continue
        label, base, _m, _f = CLOUD[name]
        content = [{"type": "text", "text": prompt}] + [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{p}"}} for p in pics[:5]]
        try:
            resp = _post(label, f"{base}/chat/completions", 180, headers={"Authorization": f"Bearer {keys[f'{name}_key']}"},
                         json={"model": VISION_MODELS[name], "messages": [{"role": "user", "content": content}]})
            _check(resp, label)
            return resp.json()["choices"][0]["message"]["content"], label
        except Exception:
            continue
    if keys.get("anthropic_key"):
        label, base, _m, _f = CLOUD["anthropic"]
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": p}} for p in pics[:5]]
        try:
            prov = make_provider("anthropic", keys["anthropic_key"])
            resp = _post(label, f"{base}/messages", 180,
                         headers={"x-api-key": keys["anthropic_key"], "anthropic-version": "2023-06-01"},
                         json={"model": prov.model, "max_tokens": 600,
                               "messages": [{"role": "user", "content": content + [{"type": "text", "text": prompt}]}]})
            _check(resp, label)
            return "".join(b.get("text", "") for b in resp.json().get("content", [])), label
        except Exception:
            pass
    return None
