"""Entry point for the shot-list media finder.

Usage:
    python shot_media_cli.py run shots.json --config shotsource/config.default.yaml --output ./out
    python shot_media_cli.py run shots.md -v

See shotsource/config.default.yaml for every tunable threshold (quality
scoring weights, hard-reject cutoffs, per-source rate limits) and
shotsource/pipeline.py for how a run is put together.
"""
from shotsource.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
