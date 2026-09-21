"""Loads a local .env file (if present) into os.environ, once, so API keys
set there don't need re-entering every session.

Every entry-point app (empire.py, channel_agent.py, dashboard.py,
voice_generator.py, studio.py) and shotsource itself imports this before
reading any os.environ key, so a single .env file at the repo root covers
all of them. Copy .env.example to .env and fill in whichever keys you
have - anything left blank just means that app's sidebar field starts
empty, exactly like today.

python-dotenv's load_dotenv() never overwrites a variable that's already
set in the real environment - a .env value is only a fallback default.
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
