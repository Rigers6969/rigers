#!/usr/bin/env python3
"""Orchestrator. One command per video.

  python build.py videos/cults                 run every unfinished stage
  python build.py videos/cults --only media    run one stage
  python build.py videos/cults --from cut      run from a stage onward
  python build.py videos/cults --only media --force   redo it
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

from pipeline import state as st
from pipeline.stages import cut, media, meta, script, transcribe

STAGES = [
    ("script", script.run),
    ("media", media.run),
    ("transcribe", transcribe.run),
    ("cut", cut.run),
    ("meta", meta.run),
]
NAMES = [n for n, _ in STAGES]


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the video pipeline.")
    ap.add_argument("video_dir", type=Path)
    ap.add_argument("--only", choices=NAMES)
    ap.add_argument("--from", dest="from_stage", choices=NAMES)
    ap.add_argument("--force", action="store_true", help="clear the stage and redo it")
    ap.add_argument("--config", type=Path, default=Path("config.yaml"))
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))

    if not (args.video_dir / "project.json").exists():
        print(f"No project.json in {args.video_dir}. Run init.py first.", file=sys.stderr)
        return 2

    start = NAMES.index(args.from_stage) if args.from_stage else 0

    for i, (name, fn) in enumerate(STAGES):
        if args.only and name != args.only:
            continue
        if i < start:
            continue
        if args.force:
            st.clear(args.video_dir, st.load(args.video_dir), name)
        try:
            fn(args.video_dir, config)
        except Exception as exc:
            logging.error("%s failed: %s", name, exc)
            st.mark_error(args.video_dir, st.load(args.video_dir), name, exc)
            return 1

    print(f"\nDone. State: {args.video_dir / 'project.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
