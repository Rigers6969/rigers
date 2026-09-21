# shotsource

Turns a shot list into a folder of openly-licensed media, filtered for quality.

## Install

```bash
pip install -r shotsource/requirements.txt
```

`sentence-transformers` (used for caption-to-shot-description similarity)
pulls in `torch` and is the heaviest dependency - everything else is light.

Pexels, Pixabay, and Unsplash each need a free API key - set whichever you
have:

```bash
export PEXELS_API_KEY=your-key-here        # https://www.pexels.com/api/
export PIXABAY_API_KEY=your-key-here        # https://pixabay.com/api/docs/
export UNSPLASH_ACCESS_KEY=your-key-here    # https://unsplash.com/developers
```

Any of the three left unset is silently skipped - no error, it just
contributes no candidates. The other four sources (Openverse, Wikimedia
Commons, Library of Congress, archive.org) need no key at all.

## Run

There's no separate CLI - use the **Media Finder** tab in `studio.py`:

```bash
streamlit run studio.py --server.port 8505
```

Paste your shot list (one description per line) into the text box and
click "Find media". If you're scripting this instead, call the pipeline
directly:

```python
from shotsource.pipeline import run_pipeline
run_pipeline("shotsource/example_shots.json", output_dir_override="./shot_media_output")
```

Shot list input is either:
- JSON: a list of strings, or a list of `{"id": "...", "description": "..."}` objects
- Markdown/plain text: one shot per bullet, numbered item, or non-empty line

Output:
- `shot_media_output/<shot>/01_..jpg` ... `05_..jpg` - the top-scoring media per shot
- `shot_media_output/manifest.csv` - source URL, direct URL, license, license URL, attribution text, and every quality score, one row per kept file
- `shot_media_output/rejections.csv` - every candidate that didn't make it, with a reason (hard-reject cause, download/decode failure, missing license, or "below top-N cutoff") - tune `shotsource/config.default.yaml` against this

## Config

Copy `shotsource/config.default.yaml`, edit the copy, and pass its path in
the Media Finder tab's "Config YAML" field (or as `config_path` to
`run_pipeline`). Only the keys you include override the packaged
defaults; everything else keeps its default. See the comments in
`config.default.yaml` for what each threshold and weight does.

## How scoring works

Every candidate that survives the hard-reject checks (min width, aspect
ratio, watermark keyword/heuristic, perceptual-hash duplicate) gets a
weighted score:

```
final = w_resolution * resolution_score + w_sharpness * sharpness_score + w_caption * caption_similarity_score
```

- `resolution_score`: width / `resolution_reference_width_px`, capped at 1.0
- `sharpness_score`: variance of the Laplacian (OpenCV) / `sharpness_reference_variance`, capped at 1.0
- `caption_similarity_score`: cosine similarity between the shot description and the candidate's title/caption, via a sentence-transformers embedding

The top `top_n_per_shot` (default 5) by `final_score` are kept; the rest are
logged to `rejections.csv` with reason `below top-N cutoff after scoring`.

## Caching and rate limits

Every API response and downloaded image is cached under `cache_dir`
(default `./.shotsource_cache`) - API responses expire after
`cache_ttl_hours`, images never do (they're addressed by URL). Each source
has its own `requests_per_minute` in the config; re-running the tool while
tuning quality thresholds won't re-hit any API or re-download anything
already cached.
