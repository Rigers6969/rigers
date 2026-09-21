"""Loads a local .env file (if present) into os.environ, once, so API keys
set there don't need re-entering every session.

studio.py imports this before reading any os.environ key, and shotsource
loads the same .env itself too, so a single .env file at the repo root
covers everything. Copy .env.example to .env and fill in whichever keys
you have - anything left blank just means that field starts empty,
exactly like today.

python-dotenv's load_dotenv() never overwrites a variable that's already
set in the real environment - a .env value is only a fallback default.
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
