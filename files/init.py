#!/usr/bin/env python3
"""Create a new video folder.

  python init.py cults --channel "Because We're Human" --title "Why Smart People Join Cults"
"""
from __future__ import annotations

import argparse
from pathlib import Path

from pipeline import state as st

SUBDIRS = ["sources", "media", "audio", "cut", "meta"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--channel", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--root", type=Path, default=Path("videos"))
    args = ap.parse_args()

    video_dir = args.root / args.slug
    if video_dir.exists():
        print(f"{video_dir} already exists.")
        return 1

    for sub in SUBDIRS:
        (video_dir / sub).mkdir(parents=True, exist_ok=True)
    st.save(video_dir, st.new_state(args.slug, args.channel, args.title))
    (video_dir / "script.md").write_text(f"# {args.title}\n\n", encoding="utf-8")

    print(f"Created {video_dir}")
    print(f"Next: write {video_dir / 'script.md'}, then: python build.py {video_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
