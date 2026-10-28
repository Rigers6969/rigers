"""Flask backend for the Wayne Factory web dashboard.

This serves a real HTML/CSS/JavaScript website (in web/) instead of a
Streamlit app - Streamlit's components render inside sandboxed iframes,
which blocks full-page canvas animation and other effects that need the
real page DOM. A plain backend + static frontend has none of those limits.

The backend's only job is to keep your API keys/tokens server-side. The
frontend calls GET /api/stats and never sees the credentials themselves.

Run with:
    python web_server.py
Then open http://localhost:5001

Configure credentials by copying config.example.json to config.json and
filling in your values (see analytics.py's docstring for exactly how to
obtain each one). Edit config.json in a plain text editor (Notepad is
fine) - this is deliberately simpler than environment variables, which
have to be retyped every terminal session and are easy to paste
incorrectly (a partial paste is silently accepted as a short, wrong
value - there's no error until the API rejects it). config.json is
gitignored, so your real credentials never get committed.

Environment variables (YOUTUBE_CHANNEL_ID, YOUTUBE_API_KEY, IG_USER_ID,
IG_ACCESS_TOKEN) still work too, as a fallback for anything not set in
config.json - useful for a real deployment, not needed for local use.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, jsonify, make_response, redirect, request, send_from_directory

import phone_access

from analytics import StatsFetchError, fetch_youtube_revenue, fetch_youtube_stats
from video_api import bp as video_bp
from studio_api import bp as studio_bp
from auto_api import bp as auto_bp
from jobs import bp as jobs_bp
from news_api import bp as news_bp
from editor_api import bp as editor_bp
from grammar_guide_api import bp as grammar_guide_bp
from thumbnail_api import bp as thumbnail_bp
from research_api import bp as research_bp
from books_api import bp as books_bp
from autopilot_api import bp as autopilot_bp

APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"
CONFIG_PATH = APP_DIR / "config.json"

app = Flask(__name__, static_folder=None)
app.register_blueprint(video_bp)
app.register_blueprint(studio_bp)
app.register_blueprint(auto_bp)
app.register_blueprint(jobs_bp)
app.register_blueprint(news_bp)
app.register_blueprint(grammar_guide_bp)
app.register_blueprint(editor_bp)
app.register_blueprint(thumbnail_bp)
app.register_blueprint(research_bp)
app.register_blueprint(books_bp)
app.register_blueprint(autopilot_bp)


def load_config() -> dict:
    """Reads credentials from config.json if present, falling back to
    environment variables for any key it doesn't set. Values are stripped
    of surrounding whitespace - a trailing newline from a copy-paste into
    a text file is a common, silent source of "invalid" credentials."""
    file_config: dict = {}
    if CONFIG_PATH.exists():
        try:
            # utf-8-sig (not plain utf-8) strips a byte-order-mark if
            # present without erroring - Windows tools like PowerShell's
            # Set-Content or Notepad can write one, and plain utf-8 decoding
            # would raise UnicodeDecodeError on it (an exception type the
            # caller wasn't catching, which surfaced as an opaque HTML 500
            # error page instead of a JSON response - exactly what a user
            # hit). It's a no-op for a file that has no BOM.
            raw_text = CONFIG_PATH.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError) as exc:
            raise RuntimeError(f"config.json could not be read: {exc}") from exc
        try:
            file_config = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"config.json is not valid JSON: {exc}") from exc
        if not isinstance(file_config, dict):
            raise RuntimeError(
                "config.json must contain a JSON object like "
                '{"YOUTUBE_CHANNEL_ID": "...", ...} - '
                f"got a {type(file_config).__name__} instead"
            )

    def get(key: str) -> str:
        value = file_config.get(key) or os.environ.get(key, "")
        return value.strip() if isinstance(value, str) else value

    return {
        "YOUTUBE_CHANNEL_ID": get("YOUTUBE_CHANNEL_ID"),
        "YOUTUBE_API_KEY": get("YOUTUBE_API_KEY"),
        "IG_USER_ID": get("IG_USER_ID"),
        "IG_ACCESS_TOKEN": get("IG_ACCESS_TOKEN"),
    }


@app.before_request
def phone_gate():
    """Other devices (your phone) must type the PIN once; this PC never has to."""
    if request.path in ("/phone-login",) or phone_access.allowed(request.remote_addr, request.cookies.get(phone_access.COOKIE, "")):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": "Type the PIN first."}), 401
    return redirect("/phone-login")


@app.after_request
def phone_keep_logged_in(resp):
    """A phone that keeps using the app stays logged in (the 30 days restart on every visit)."""
    cookie = request.cookies.get(phone_access.COOKIE, "")
    if cookie and not phone_access.is_local(request.remote_addr) and phone_access.allowed(request.remote_addr, cookie):
        resp.set_cookie(phone_access.COOKIE, cookie, max_age=phone_access.COOKIE_DAYS * 86400, httponly=True, samesite="Lax")
    return resp


@app.route("/phone-login", methods=["GET", "POST"])
def phone_login():
    error = ""
    if request.method == "POST":
        addr = request.remote_addr or ""
        if phone_access.locked(addr):
            error = "Too many wrong PINs. Wait 10 minutes."
        elif phone_access.check_pin(addr, request.form.get("pin", "")):
            resp = make_response(redirect("/"))
            resp.set_cookie(phone_access.COOKIE, phone_access.token(), max_age=phone_access.COOKIE_DAYS * 86400,
                            httponly=True, samesite="Lax")
            return resp
        else:
            error = "Wrong PIN."
    return phone_access.LOGIN_PAGE.replace("%ERROR%", error)


@app.route("/api/phone", methods=["GET", "POST"])
def api_phone():
    if not phone_access.is_local(request.remote_addr):
        return jsonify({"error": "Change phone settings on the PC itself."}), 403
    data = request.get_json(silent=True) or {}
    if "enabled" in data:
        phone_access.set_enabled(bool(data["enabled"]))
    if data.get("new_pin"):
        phone_access.new_pin()
    cfg = phone_access.load()
    return jsonify({"enabled": cfg["enabled"], "pin": cfg["pin"], "url": phone_access.phone_url(),
                    "urls": [f"http://{ip}:{phone_access.PORT}" for ip in phone_access.all_ips()],
                    "running_open": app.config.get("PHONE_HOST") == "0.0.0.0"})


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(WEB_DIR, filename)


@app.route("/api/stats")
def api_stats():
    result: dict = {"youtube": None, "errors": []}

    try:
        config = load_config()
    except Exception as exc:
        # Whatever goes wrong reading/parsing config.json, the frontend must
        # still get back valid JSON - an uncaught exception here previously
        # fell through to Flask's default HTML error page, which broke the
        # page's fetch() call with a confusing "Unexpected token '<'" parse
        # error instead of showing the actual problem.
        result["errors"].append(str(exc))
        return jsonify(result)

    if config["YOUTUBE_CHANNEL_ID"] and config["YOUTUBE_API_KEY"]:
        try:
            result["youtube"] = fetch_youtube_stats(config["YOUTUBE_CHANNEL_ID"], config["YOUTUBE_API_KEY"])
        except Exception as exc:
            result["errors"].append(f"YouTube: {exc}")
    else:
        result["errors"].append(
            "YouTube not configured: set YOUTUBE_CHANNEL_ID and YOUTUBE_API_KEY in config.json"
        )

    return jsonify(result)


REVENUE_GOAL = 10000.0


@app.route("/api/revenue")
def api_revenue():
    try:
        data = fetch_youtube_revenue()
        return jsonify({
            "goal": REVENUE_GOAL,
            "current": data["total_revenue"],
            "currency": data.get("currency", "USD"),
            "note": data.get("note"),
        })
    except StatsFetchError as exc:
        # Not connected yet (no token_analytics.json) - $0 is the honest
        # number until the one-time login in youtube_auth_setup.py is done.
        return jsonify({"goal": REVENUE_GOAL, "current": 0.0, "currency": "USD", "note": str(exc)})


if __name__ == "__main__":
    # threaded=True so a slow pipeline run (media search, whisper transcription)
    # doesn't block the stats dashboard from loading in another tab.
    host = phone_access.host()
    app.config["PHONE_HOST"] = host
    if host != "127.0.0.1":
        cfg = phone_access.load()
        print("\n  PHONE MODE IS ON")
        for ip in phone_access.all_ips():
            print(f"  On your phone (same Wi-Fi) open:  http://{ip}:{phone_access.PORT}")
        print(f"  PIN: {cfg['pin']}\n")
    app.run(host=host, port=phone_access.PORT, debug=False, threaded=True)
