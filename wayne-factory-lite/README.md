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

Open http://localhost:5000. The main Wayne Factory app runs on 5001, so
both can run at the same time without a port conflict.

On the Produce page, type the channel name (e.g. "History") each time -
there's no separate app per channel, just this one app used for
whichever channel you're currently producing for.

Videos land in this folder's own `content/` directory - entirely
separate from the main app's, including its own Obsidian vault.

## Trend Scout (optional)

On the Produce page, the **Trend Scout** panel lets the scheduler's
topic invention take a hint from what's actually getting views right
now in a channel's niche, fully automatically - you give it a few
search keywords, not specific channels to track, and it searches all
of YouTube itself.

To use it:
1. Make sure `YOUTUBE_API_KEY` is set in `config.json` (same key used
   for the Dashboard's stats - see `analytics.py`'s docstring for how
   to get one).
2. On the Produce page's Trend Scout panel, type your channel's exact
   name (matching what you use in the Schedule panel) and a few niche
   search keywords, one per line (e.g. "ancient history", "lost
   civilizations") -> Save.
3. Click "Preview Current Top Titles" any time to see exactly what
   it's currently pulling, with no production job involved.

**Quota cost:** each keyword costs 100 of your project's 10,000 daily
quota units (shared with YouTube uploads at 1,600 units each - see
"Auto-publishing to YouTube" above) - a handful of keywords per channel
is plenty; don't add dozens, and don't hit Preview repeatedly for no
reason. If you skip this entirely, topic invention works exactly as
before, just without the extra context.

## Auto-publishing to YouTube (optional)

Every produced video automatically generates a thumbnail and uploads
itself to YouTube as **public**, immediately, no review step - unless
that channel hasn't been connected yet, in which case it's just skipped
(the video still saves locally, nothing breaks).

To connect a channel:
1. You need the same `client_secret.json` used for `youtube_auth_setup.py`
   (revenue stats) - if you haven't set that up, see `analytics.py`'s
   docstring for how to get one from Google Cloud Console.
2. Run, once per channel:
   ```
   python youtube_publish_auth_setup.py "Deep Field"
   ```
   Your browser opens - **switch to that channel** using YouTube's own
   account switcher before approving. This matters: the YouTube API
   always uploads to whichever channel the login was approved under,
   with no way to pick a different destination per upload. If Deep
   Field and The Archive share one Google login, run this command again
   for the other channel, switching first.
3. That's it - future videos produced under that exact channel name
   auto-publish from then on.

**Real limits worth knowing before you turn this on:**
- Each upload costs 1,600 of your Google Cloud project's 10,000 daily
  quota units - about **6 uploads/day**, shared across every channel
  using the same project's credentials.
- Publishing is immediate and public - there's no built-in review step.
  If you want to check videos before they go live, don't run the auth
  setup for that channel (or delete its `token_upload_*.json`) and
  publish manually from YouTube Studio instead.

## Shorts (automatic)

After every **long** video, the app also cuts it into 3-4 vertical
Shorts (1080x1920, under a minute each) for YouTube Shorts, Reels and
TikTok: the writer model picks the most gripping self-contained moments
from the transcript (if it's unavailable, clips are spread evenly), each
clip keeps the full picture over a blurred background, with a title at
the top and word-by-word captions at the bottom. They land in the
video's `shorts/` folder.

On the Produce page, open a video to watch/download its Shorts, remake
them, or **Publish** one to YouTube. Shorts are made automatically but
published only when you click - every upload costs 1,600 of your
~10,000 daily YouTube API units (about 6 uploads a day), so 4 Shorts per
video would use most of it. To stop making them automatically, set
`AUTO_SHORTS = False` in `producer.py`.
