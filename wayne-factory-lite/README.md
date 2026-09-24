# Wayne Factory Lite

A standalone sibling of the main Wayne Factory app, for a second YouTube
channel (History, Science, or whatever comes next). Same production
pipeline (script writing, shot planning, voiceover, stock media search,
automatic 9:16 vertical + captions for Shorts, automatic background
music, thumbnail generator) - just three pages instead of the full
app's: **Dashboard**, **Produce**, **Thumbnails**.

This folder is fully self-contained - it doesn't import any code from
the main app one level up. It's a separate app that happens to live in
the same repo.

## Setup

1. Copy `config.example.json` to `config.json` and fill in this
   channel's own `YOUTUBE_CHANNEL_ID` and `YOUTUBE_API_KEY` (Dashboard
   stats only - see `analytics.py`'s docstring for how to get them).
2. Copy `.env.example` to `.env` and fill in whichever keys you use
   (Ollama/Claude, stock media sources, Jamendo for music) - same keys
   as the main app's own `.env`, since it's the same set of external
   services.
3. Install dependencies if this is a fresh environment:
   ```
   pip install -r requirements.txt
   pip install -r shotsource/requirements.txt
   ```
   (Skip this if you're running it on the same PC as the main app -
   everything's already installed there.)

## Run

```
python web_server.py
```

Open http://localhost:5000. Note: this uses the *same* port (5000) as
the main Wayne Factory app, so don't run both at the same time unless
you change one of their ports.

On the Produce page, type the channel name (e.g. "History") each time -
there's no separate app per channel, just this one app used for
whichever channel you're currently producing for.

Videos land in this folder's own `content/` directory - entirely
separate from the main app's, including its own Obsidian vault.
