"""Command-line entry point: `python -m shotsource.cli run shots.json [...]`"""
from __future__ import annotations

import argparse
import logging
import sys

from .pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shotsource", description="Find openly-licensed media for a shot list.")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Fetch and quality-filter media for every shot in a shot list.")
    run_p.add_argument("shots", help="Path to a shot list: .json (list of strings or {description}) or .md/.txt.")
    run_p.add_argument("--config", default=None, help="YAML config overriding shotsource/config.default.yaml.")
    run_p.add_argument("--output", default=None, help="Output directory (overrides the config's output_dir).")
    run_p.add_argument("-v", "--verbose", action="store_true", help="Debug-level logging.")

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.command == "run":
        try:
            manifest_path = run_pipeline(args.shots, args.config, args.output)
        except Exception as exc:
            logging.getLogger("shotsource").error("%s", exc)
            return 1
        print(f"Manifest written to {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
