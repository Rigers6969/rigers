"""Phone mode: open Wayne Factory from your phone.

Off by default - the app then only answers on this PC (127.0.0.1). When it's
on, the app also answers on your home Wi-Fi (and on Tailscale, if you use it
to reach the PC from anywhere), but every device other than this PC must type
the PIN first. The PIN is made at random and shown on the Phone page and in
the black start-up window. 5 wrong PINs lock that device out for 10 minutes.

Switching it on or off takes effect the next time Wayne Factory starts.
"""
from __future__ import annotations

import hmac
import json
import secrets
import socket
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = APP_DIR / "phone.json"
PORT = 5001
COOKIE = "wf_phone"
COOKIE_DAYS = 30
LOCAL = {"127.0.0.1", "::1", "localhost"}
_fails: dict[str, list[float]] = {}


def load() -> dict:
    data = {}
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    changed = False
    if not str(data.get("pin", "")).isdigit() or len(str(data.get("pin"))) != 6:
        data["pin"] = f"{secrets.randbelow(10**6):06d}"
        changed = True
    if not data.get("secret"):
        data["secret"] = secrets.token_hex(24)
        changed = True
    data.setdefault("enabled", False)
    if changed:
        _save(data)
    return data


def _save(data: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def set_enabled(on: bool) -> dict:
    data = load()
    data["enabled"] = bool(on)
    _save(data)
    return data


def new_pin() -> dict:
    data = load()
    data["pin"] = f"{secrets.randbelow(10**6):06d}"
    data["secret"] = secrets.token_hex(24)  # also logs every phone out
    _save(data)
    return data


def host() -> str:
    return "0.0.0.0" if load()["enabled"] else "127.0.0.1"


def lan_ip() -> str:
    """This PC's address on the Wi-Fi (no data is sent anywhere)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def all_ips() -> list[str]:
    """Every IPv4 address of this PC, home-Wi-Fi-looking ones first (192.168 / 10.x), Tailscale (100.x) last."""
    found = {lan_ip()}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    found = {ip for ip in found if not ip.startswith(("127.", "169.254."))}

    def rank(ip: str) -> int:
        if ip.startswith("192.168."):
            return 0
        if ip.startswith("10."):
            return 1
        if ip.startswith("172."):
            return 2
        if ip.startswith("100."):
            return 4
        return 3
    return sorted(found, key=lambda ip: (rank(ip), ip)) or ["127.0.0.1"]


def phone_url() -> str:
    return f"http://{all_ips()[0]}:{PORT}"


# ---------- who may come in ----------

def token() -> str:
    data = load()
    return hmac.new(data["secret"].encode(), b"phone-ok", "sha256").hexdigest()


def is_local(addr: str) -> bool:
    return (addr or "") in LOCAL


def allowed(addr: str, cookie: str) -> bool:
    return is_local(addr) or (bool(cookie) and hmac.compare_digest(cookie, token()))


def locked(addr: str) -> bool:
    now = time.time()
    _fails[addr] = [t for t in _fails.get(addr, []) if now - t < 600]
    return len(_fails[addr]) >= 5


def check_pin(addr: str, pin: str) -> bool:
    if locked(addr):
        return False
    if hmac.compare_digest(str(pin).strip(), load()["pin"]):
        _fails.pop(addr, None)
        return True
    _fails.setdefault(addr, []).append(time.time())
    return False


LOGIN_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Wayne Factory</title>
<style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:radial-gradient(circle at 50% 30%,#2a2210,#05070b 60%);
font-family:system-ui,sans-serif;color:#eee}
form{width:min(340px,88vw);text-align:center}
.sig{width:110px;height:110px;margin:0 auto 22px;border-radius:50%;background:radial-gradient(circle,#ffe9a6,#e2b552 55%,transparent 72%);
display:flex;align-items:center;justify-content:center;box-shadow:0 0 70px rgba(255,214,120,.25)}
.sig svg{width:72%;fill:#07090d}
h1{font:600 22px Georgia,serif;margin:0 0 6px}
p{color:#9aa0ab;font-size:14px;margin:0 0 22px}
input{width:100%;box-sizing:border-box;font-size:30px;letter-spacing:12px;text-align:center;padding:14px;border-radius:14px;
border:1px solid rgba(255,255,255,.15);background:rgba(255,255,255,.06);color:#fff;outline:none}
input:focus{border-color:#f3d488}
button{margin-top:16px;width:100%;padding:15px;border:0;border-radius:999px;font-size:16px;font-weight:700;color:#120e05;
background:linear-gradient(135deg,#f3d488,#c4943c);box-shadow:0 8px 28px rgba(214,169,74,.35)}
.err{color:#f0a39a;min-height:20px;margin-top:12px;font-size:14px}
</style></head><body><form method="post" action="/phone-login">
<div class="sig"><svg viewBox="0 0 100 46"><path d="M50 8c-1.6 3.2-3.4 3.6-5.2 1.2L43 4.5 41.2 13C35 8.6 24.8 6.8 12 9.5c8.4 3.4 10.6 9 8.6 16 7-4.2 14.6-2.6 18.8 4 1.4-3.6 3.6-5.6 5.6-6.2 1.6 3.8 3.2 7.6 5 12.2 1.8-4.6 3.4-8.4 5-12.2 2 .6 4.2 2.6 5.6 6.2 4.2-6.6 11.8-8.2 18.8-4-2-7 .2-12.6 8.6-16C75.2 6.8 65 8.6 58.8 13L57 4.5l-1.8 4.7C53.4 11.6 51.6 11.2 50 8z"/></svg></div>
<h1>The Wayne Factory</h1><p>Type the 6-digit PIN shown on your PC.</p>
<input name="pin" inputmode="numeric" autocomplete="one-time-code" maxlength="6" autofocus>
<button type="submit">Enter</button><div class="err">%ERROR%</div></form></body></html>"""
