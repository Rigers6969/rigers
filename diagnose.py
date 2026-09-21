"""One-shot diagnostic for the "API key not valid" YouTube stats problem.

Run this instead of the web app - it reads config.json exactly the way
web_server.py does, prints exactly what it found, and makes the exact same
API call analytics.py makes, all in one place, so there's no ambiguity
about which terminal/browser tab to look at.

Usage:
    python diagnose.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"

print("=" * 60)
print(f"Looking for config.json at: {CONFIG_PATH}")
print(f"File exists: {CONFIG_PATH.exists()}")
print("=" * 60)

if not CONFIG_PATH.exists():
    print("ERROR: config.json not found at that exact path. That's the bug -")
    print("you're running this from a different folder than the one you edited.")
    sys.exit(1)

raw_bytes = CONFIG_PATH.read_bytes()
print(f"Raw file size: {len(raw_bytes)} bytes")
print(f"First 10 raw bytes: {raw_bytes[:10]!r}")

try:
    raw_text = raw_bytes.decode("utf-8-sig")
except UnicodeDecodeError as exc:
    print(f"ERROR: file is not valid UTF-8: {exc}")
    sys.exit(1)

try:
    data = json.loads(raw_text)
except json.JSONDecodeError as exc:
    print(f"ERROR: config.json is not valid JSON: {exc}")
    sys.exit(1)

channel_id = str(data.get("YOUTUBE_CHANNEL_ID", "")).strip()
api_key = str(data.get("YOUTUBE_API_KEY", "")).strip()

print("=" * 60)
print(f"YOUTUBE_CHANNEL_ID: {channel_id!r}  (length {len(channel_id)})")
print(f"YOUTUBE_API_KEY:    {api_key!r}  (length {len(api_key)})")
print("=" * 60)

if not api_key:
    print("ERROR: YOUTUBE_API_KEY is empty in config.json.")
    sys.exit(1)

sys.path.insert(0, str(APP_DIR))
from analytics import StatsFetchError, fetch_youtube_stats  # noqa: E402

print("Calling the real YouTube API with these exact values...")
print("=" * 60)
try:
    stats = fetch_youtube_stats(channel_id, api_key)
    print("SUCCESS:")
    print(json.dumps(stats, indent=2))
except StatsFetchError as exc:
    print(f"FAILED: {exc}")
    print()
    print("Since this used the literal bytes read from config.json on THIS")
    print("machine, whatever printed above as YOUTUBE_API_KEY repr is what's")
    print("actually being sent - compare it character by character against")
    print("the key shown in Google Cloud Console.")
