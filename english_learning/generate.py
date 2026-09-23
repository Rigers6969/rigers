"""Builds English_Learning_Guide.pdf: real vocabulary (Free Dictionary
API), real grammar (Wikibooks' "English in Use"), and real idioms
(Wiktionary) - fetched live, then laid out into one PDF.

Usage:
    python generate.py
    python generate.py --words 200 --idioms 100 --grammar 25
    python generate.py --out ~/Desktop/English.pdf

Needs internet access (this fetches from three real, free, no-API-key
sources - see the fetch_*.py files for exactly which ones and why).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from build_pdf import build_pdf
from fetch_grammar import fetch_grammar
from fetch_idioms import fetch_idioms
from fetch_vocabulary import fetch_vocabulary

DEFAULT_OUT = Path(__file__).resolve().parent / "English_Learning_Guide.pdf"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--words", type=int, default=150, help="Number of vocabulary words (default 150)")
    parser.add_argument("--idioms", type=int, default=80, help="Number of idioms (default 80)")
    parser.add_argument("--grammar", type=int, default=20, help="Number of grammar chapters (default 20)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output PDF path")
    args = parser.parse_args()

    def progress(msg: str) -> None:
        print(msg, flush=True)

    print("Fetching vocabulary from the Free Dictionary API...")
    vocabulary = fetch_vocabulary(limit=args.words, progress=progress)
    print(f"  -> {len(vocabulary)} word(s) with real definitions found.\n")

    print("Fetching grammar chapters from Wikibooks...")
    grammar = fetch_grammar(limit=args.grammar, progress=progress)
    print(f"  -> {len(grammar)} chapter(s) found.\n")

    print("Fetching idioms from Wiktionary...")
    idioms = fetch_idioms(limit=args.idioms, progress=progress)
    print(f"  -> {len(idioms)} idiom(s) found.\n")

    print(f"Building PDF at {args.out}...")
    build_pdf(args.out, vocabulary, grammar, idioms)
    print(f"Done: {args.out}")


if __name__ == "__main__":
    main()
