# Video pipeline

Stages share one contract: `project.json` in each video folder. Every stage
reads it, does its work, writes back. No stage imports another, so any of them
can be rerun, replaced, or done by hand.

## Setup

    pip install -r requirements.txt

## Making a video

    python init.py cults --channel "Because We're Human" --title "Why Smart People Join Cults"

Write the narration into `videos/cults/script.md`. Shot lines are numbered
italics (`1. *A university corridor*`) — the script stage pulls them out into
`project.json`, where you can add `query_terms` to steer the search.

    python build.py videos/cults

Record your own voiceover to `videos/cults/audio/vo.wav` before the transcribe
stage runs.

## Stages

| Stage | Reads | Writes |
|---|---|---|
| script | `script.md` | shot list into `project.json` |
| media | shot list | `media/shot-NN-*/`, `manifest.csv`, `rejected/` |
| transcribe | `audio/vo.wav` | `audio/timings.json` |
| cut | timings + shots | `cut/edit_plan.json` |
| meta | plan + manifest | `meta/metadata.json` |

## Running one stage

    python build.py videos/cults --only media
    python build.py videos/cults --only media --force    # redo it
    python build.py videos/cults --from cut

## Tuning the filter

`min_sharpness` in `config.yaml` is the one to adjust first. Every rejection is
logged with its reason and the file is kept in `media/rejected/` — if good shots
are landing there, lower it.

## What's real and what's a stub

Real: state handling, orchestrator, media fetch + quality filter, metadata.
Stub: `cut.py` spaces shots evenly and writes a plan; turning that into FCP7 XML
that Premiere imports is the next piece to build.
