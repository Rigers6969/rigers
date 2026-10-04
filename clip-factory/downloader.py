"""Downloads a video (YouTube, Twitch VODs, Kick, and most other sites
yt-dlp supports) into the input/ folder, one at a time, with progress.

YouTube downloads need a JavaScript runtime (Deno - start.bat installs it)
because of how YouTube protects its video links; this finds it even when
it was installed a moment ago and the PATH hasn't caught up yet.
"""
from __future__ import annotations

import os
import queue
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

import upload_text
from trends import _QuietLogger, clean_error

APP_DIR = Path(__file__).resolve().parent
INPUT_DIR = APP_DIR / "input"
QUALITIES = {"2160": 2160, "1440": 1440, "1080": 1080, "720": 720}

downloads: dict[str, dict] = {}
_queue: "queue.Queue[str]" = queue.Queue()
_worker_started = threading.Lock()
_worker: dict = {"thread": None}
on_finished: list[Callable[[dict], None]] = []  # called with the download after it's done


class Cancelled(Exception):
    pass


def js_runtimes() -> dict:
    found = {}
    for name in ("deno", "node", "bun"):
        path = shutil.which(name)
        if not path and os.name == "nt" and name == "deno":
            for cand in (Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "deno.exe",
                         Path(os.environ.get("USERPROFILE", "")) / ".deno" / "bin" / "deno.exe"):
                if cand.is_file():
                    path = str(cand)
                    break
        if path:
            found[name] = {"path": path}
    return found


def is_url(text: str) -> bool:
    return bool(re.match(r"^https?://\S+$", text.strip()))


def add(url: str, quality: str = "1080", title: str = "", then_clip: Optional[dict] = None, cookies: str = "") -> dict:
    url = url.strip()
    for d in downloads.values():  # the same link already waiting or downloading
        if d["url"] == url and d["status"] in ("queued", "downloading"):
            if then_clip and not d.get("then_clip"):
                d["then_clip"] = then_clip
            return d
    did = uuid.uuid4().hex[:10]
    downloads[did] = {
        "id": did, "url": url, "title": title or url, "quality": quality if quality in QUALITIES else "1080",
        "status": "queued", "percent": 0, "message": "Waiting...", "file": None, "error": None,
        "then_clip": then_clip, "clip_run": None, "created": time.time(), "cancel": False,
        "cookies": cookies if cookies in COOKIE_BROWSERS else "",
    }
    _queue.put(did)
    with _worker_started:
        if not _worker["thread"] or not _worker["thread"].is_alive():
            _worker["thread"] = threading.Thread(target=_work, daemon=True)
            _worker["thread"].start()
    return downloads[did]


def cancel(did: str) -> bool:
    d = downloads.get(did)
    if not d or d["status"] not in ("queued", "downloading"):
        return False
    d["cancel"] = True
    if d["status"] == "queued":
        d.update(status="cancelled", message="Cancelled.")
    return True


def _work() -> None:
    while True:
        did = _queue.get()
        d = downloads.get(did)
        if not d or d["status"] != "queued":
            continue
        try:
            _download(d)
        except Exception as exc:  # never let one bad download stop the queue
            d.update(status="error", error=f"Unexpected problem: {exc}")
        for cb in on_finished:
            try:
                cb(d)
            except Exception:
                pass


COOKIE_BROWSERS = ("firefox", "edge", "chrome", "brave", "opera", "vivaldi")


def _impersonate_target():
    """'Look like Chrome' for sites behind Cloudflare (Kick) - needs the curl_cffi package."""
    import importlib.util
    if importlib.util.find_spec("curl_cffi") is None:
        return None
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget
        return ImpersonateTarget.from_str("chrome")
    except Exception:
        return None


def _blocked(exc: Exception) -> bool:
    """The site refused us (not a broken link): worth trying again another way."""
    return bool(re.search(r"\b403\b|forbidden|confirm you.?re not a bot|sign in to confirm|429|too many requests", str(exc), re.I))


def _remove_partial(paths: set[str]) -> None:
    """A cancelled download leaves half-written files behind - remove them."""
    for name in paths:
        for f in (Path(name), Path(name + ".part"), Path(name + ".ytdl")):
            try:
                if f.is_file() and f.resolve().parent == INPUT_DIR.resolve():
                    f.unlink()
            except OSError:
                pass


def _fmt_size(n) -> str:
    if not n:
        return "?"
    return f"{n / 1e9:.2f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB"


def _download(d: dict) -> None:
    try:
        import yt_dlp
    except ImportError:
        d.update(status="error", error="yt-dlp isn't installed - close the app and double-click start.bat again.")
        return
    INPUT_DIR.mkdir(exist_ok=True)
    d.update(status="downloading", message="Starting the download...")
    parts = {"n": 0}
    temp_files: set[str] = set()

    def hook(p):
        for key in ("tmpfilename", "filename"):
            if p.get(key) and p.get("status") == "downloading":
                temp_files.add(p[key])
        if d["cancel"]:
            raise Cancelled()
        if p.get("status") == "downloading":
            total = p.get("total_bytes") or p.get("total_bytes_estimate")
            done = p.get("downloaded_bytes") or 0
            pct = done / total * 100 if total else 0
            # video and audio come down separately, then get joined: show it as one bar
            overall = pct / 2 + (50 if parts["n"] >= 1 else 0)
            speed = p.get("speed")
            eta = p.get("eta")
            d.update(percent=round(min(99.0, overall), 1),
                     message=f"Downloading {'audio' if parts['n'] >= 1 else 'video'}: {_fmt_size(done)} of {_fmt_size(total)}"
                             + (f" at {speed / 1e6:.1f} MB/s" if speed else "")
                             + (f", about {int(eta // 60)}:{int(eta % 60):02d} left" if eta else ""))
        elif p.get("status") == "finished":
            parts["n"] += 1
            d.update(message="Joining video and audio...")

    height = QUALITIES[d["quality"]]
    opts = {
        "format": "bv*+ba/b",
        # the best picture up to the chosen height, preferring H.264 (fastest for ffmpeg to cut later);
        # above 1080p YouTube only has VP9/AV1, which is picked automatically
        "format_sort": [f"res:{height}", "vcodec:h264", "acodec:m4a"],
        "merge_output_format": "mp4",
        "outtmpl": str(INPUT_DIR / "%(title).80B [%(id)s].%(ext)s"),
        "windowsfilenames": True, "noplaylist": True, "continuedl": True,
        "quiet": True, "no_warnings": True, "noprogress": True, "logger": _QuietLogger(),
        "progress_hooks": [hook], "socket_timeout": 30, "retries": 5, "fragment_retries": 10,
    }
    runtimes = js_runtimes()
    if runtimes:
        opts["js_runtimes"] = runtimes
    target = _impersonate_target()
    base = dict(opts)
    if target and re.search(r"kick\.com|twitch\.tv", d["url"], re.I):
        base["impersonate"] = target  # these sites only answer requests that look like a real browser
    low = {"format": "bv*[height<=720]+ba/b[height<=720]/b", "format_sort": ["res:720", "vcodec:h264", "acodec:m4a"]}
    # when the site refuses (403 / bot check): try again disguised as a browser, then at 720p, then with your login
    attempts = [("", base)]
    if target and "impersonate" not in base:
        attempts.append(("disguised as a normal browser", dict(base, impersonate=target)))
    attempts.append(("at 720p", dict(attempts[-1][1], **low)))
    if d.get("cookies"):
        attempts.append((f"with your {d['cookies'].capitalize()} login", dict(attempts[-1][1], cookiesfrombrowser=(d["cookies"],))))
    info, path, last, tried = None, None, None, []
    for label, o in attempts:
        if label:
            d.update(message=f"The site refused the download - trying again {label}...", percent=0)
            parts["n"] = 0
        try:
            with yt_dlp.YoutubeDL(o) as ydl:
                info = ydl.extract_info(d["url"], download=True)
                if info and info.get("_type") == "playlist":
                    info = next((e for e in info.get("entries") or [] if e), None)
                if not info:
                    raise RuntimeError("nothing to download at that link")
                path = next((r.get("filepath") for r in info.get("requested_downloads") or [] if r.get("filepath")), None)
                path = Path(path or ydl.prepare_filename(info))
                if not path.exists():
                    path = path.with_suffix(".mp4")
            last = None
            break
        except Cancelled:
            _remove_partial(temp_files)
            d.update(status="cancelled", message="Cancelled.")
            return
        except Exception as exc:
            if d["cancel"]:
                _remove_partial(temp_files)
                d.update(status="cancelled", message="Cancelled.")
                return
            last = exc
            tried.append(label or "normally")
            if not _blocked(exc):
                break  # a different problem (bad link, private video...) - trying again won't help
            _remove_partial(temp_files)  # a refused download leaves broken pieces - start the next try clean
            temp_files.clear()
    if last is not None:
        msg = clean_error(last)
        if "youtube" in d["url"] and not runtimes:
            msg += " - YouTube downloads need Deno: close the app and double-click start.bat again (it installs it)."
        elif _blocked(last):
            hints = [f"Clip Factory tried {', '.join(tried)}."]
            if re.search(r"kick\.com|twitch\.tv", d["url"], re.I) and not target:
                hints.append("Kick and Twitch need an extra part: close Clip Factory and start it again with start.bat (it installs it).")
            if not d.get("cookies"):
                hints.append("Turn on 'If a site blocks the download, use my browser login' (Firefox works best), log in to the site in that browser, and try again.")
            else:
                hints.append("Make sure you're logged in to the site in that browser, close the browser, and try again - or try again in an hour.")
            msg += " - " + " ".join(hints)
        elif re.search(r"sign in|confirm you.?re not a bot|login", msg, re.I):
            msg += " - YouTube is asking for a login for this video; try another one or try again later."
        d.update(status="error", error=msg, message="Download failed.")
        return
    if not path.exists():
        d.update(status="error", error="The download finished but the file can't be found in the input folder.")
        return
    try:  # remember where it came from - clip descriptions credit the show and link the full video
        upload_text.save_source(path, info)
    except Exception:
        pass
    title = d["title"] if d["title"] != d["url"] else (info.get("title") or d["title"])
    d.update(status="done", percent=100, file=path.name, title=title,
             message=f"Downloaded - saved in the input folder as {path.name}")
