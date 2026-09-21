"""shotsource - turn a shot list into a folder of openly-licensed media.

Queries Openverse, Wikimedia Commons, the Library of Congress, archive.org,
and Pexels via their public APIs (no scraping), runs everything that comes
back through a quality filter (resolution, sharpness, caption match, hard
rejects for size/aspect-ratio/watermarks/duplicates), and writes the top N
survivors per shot to disk plus a CSV manifest with licensing info.

Entry point: shotsource.cli.main() (also runnable as
`python shot_media_cli.py run <shots file>` from the repo root).
"""
from pathlib import Path

from dotenv import load_dotenv

# Load the repo root's .env (API keys for Pexels/Pixabay/Unsplash) so the
# CLI picks them up the same way the Streamlit apps do via env_config.py -
# this runs whenever shotsource is imported, standalone or via studio.py.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
