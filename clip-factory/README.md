# Clip Factory

Finds what's going viral right now, downloads it, and turns one long
video (stream, podcast, interview...) into up to **100 vertical Shorts**
in one go: 1080x1920, word-by-word captions,
an optional hook title, and AI choosing the most viral moments.

Clips are made **best first** and each one shows up on the page with its
own **Download** button the moment it's finished. You can grab clip 1
while clips 2, 3, 4... are still being cut.

It runs on your own PC for free. Optionally, cloud AIs do the heavy AI work
much faster (see **AI engines** below).

## Start it

Double-click **`start.bat`**. The page opens at http://localhost:5003.

The very first time, it installs what it needs (about a minute). The
first transcription also downloads the Whisper speech model, about
150 MB.

You also need:
- **ffmpeg.** You already have it if Wayne Factory works on this PC. If
  not, open PowerShell and run `winget install Gyan.FFmpeg`, then close
  and reopen start.bat.
- **Ollama** running, with the model you want, e.g. `llama3`. Open the
  Ollama app; it sits in the tray. Without Ollama the app still works,
  and a built-in scorer picks the moments instead.

## Find viral videos (first tab)

- **Your streamers.**
  - Type their YouTube names, one per line (e.g. `@KaiCenat`, or paste
    their channel link), pick how many days back to look, and click
    **Scan my streamers**.
  - Any name that doesn't load is listed so you can fix it.
- **Or search all of YouTube**, e.g. "podcast" or "minecraft". It shows
  YouTube's most viewed results for today, this week or this month.

Results are ranked **hottest first**:

| Label | Meaning |
|---|---|
| **views/hour** | Views divided by the hours since upload, so it shows how fast the video is blowing up right now. |
| **3x their normal** | Three times the views that streamer usually gets. A big jump like that is a great sign. |

Shorts, still-live and upcoming streams, and anything under 4 minutes are
left out, so you only see videos worth cutting.

**Ask AI what's hot** gives you a short summary of what's trending
plus the 3 best videos to clip, and why.

On every video:
- **Download** saves it into the `input` folder.
- **Download + make clips** downloads it and then cuts clips straight
  away, using the settings on the **Make clips** tab.

You can also paste any YouTube, Twitch VOD or Kick link at the top.
Downloads go one at a time, and you can cancel them.

**Only clip videos you're allowed to.** Use your own videos, or videos
whose creator allows clipping (many streamers run clipping programs).
Reuploading other people's videos without permission can get you
copyright strikes.

Nothing to set up and no API key: it reads YouTube's pages with
**yt-dlp**.
- start.bat updates yt-dlp every time, because YouTube changes often.
- On the first run, start.bat also installs **Deno**, a small free
  program yt-dlp needs to download from YouTube.

## Podcasts

Podcast clips are one of the biggest Shorts formats, and Clip Factory
has a podcast mode for them.

1. On **Find viral videos**, pick **Podcasts** instead of **Streamers**.
   - A starting list of big shows is filled in. Edit it like the
     streamers list.
   - **Scan my podcasts** shows only full episodes (20+ minutes), hottest
     first.
   - The YouTube search box has **Full episodes only (20+ min)** ticked.
2. Picking Podcasts switches the **Make clips** settings to podcast mode:
   - **Split screen layout.** The left person goes on top and the right
     person below, with the captions on the line between them. This
     suits the usual two-people-at-a-desk podcast camera shot.
   - **Clip length.** Clips are 30-90 seconds.
   - **What the AI picks.** It looks for hot takes, surprising stories,
     funny exchanges and debates, and skips ad reads, sponsor segments
     and intros.
3. Click **Download + make clips** on an episode, or use any podcast
   video with **Make clips**.

**Permission matters even more for podcasts.** Many big shows claim
copyright on clips, but many also run clipping programs that welcome
clippers. Check each show's rules first, and add your own titles and
context (see **YouTube rules** below).

## Make clips (second tab)

1. **Pick the video.** Choose it from the list (anything you put in the
   `input` folder shows up there), upload it, or paste its path
   (right-click the file, then **Copy as path**).
2. **How many clips:** 1-100. **Clip length:** 20-60 s works well for
   Shorts, Reels and TikTok.
3. **Layout:**
   - **Fill screen** for one person talking to the camera.
   - **Whole picture + blurred background** for gameplay or screen
     recordings.
   - **Podcast - split screen** for two people side by side.
4. Click **Make clips**.

Clips are numbered 1, 2, 3... from most to least viral. Every run is
saved in `output/<date>-<video name>/`. **Open folder** shows it in File
Explorer, and **Download all (zip)** gets every finished clip plus a
`titles.txt`. Click any run under **Past runs** to open it again.

## YouTube rules (third tab)

A guard that knows what gets a channel monetized and what gets it
demonetized, so the clips (and any video you make) stay within
YouTube's rules. The rule book is `youtube_rules.json`: a plain-English
summary from October 2026, with sources.

**Every clip is checked automatically:**
- **Skipped moments.** Moments with slurs, harassment or sexual content
  are never picked (setting: *Skip moments that break YouTube's rules*).
- **Bleeping.** Swear words are bleeped (muted) and shown as `F***` in
  the captions (setting: *Bleep swear words*). Frequent swearing limits
  ads; occasional swearing is fine.
- **Clean titles.** Clip titles never contain swear words, because
  swearing in a title limits ads even when the video is clean.
- **A badge on every clip:**
  - green = looks ad-friendly
  - yellow = risk of limited ads
  - red = risk of no ads, removal or a strike

**On the YouTube rules tab:**
- **Check a video before you upload.** Paste the title, description and
  script.
  - **Instant check** runs on this PC.
  - **AI review** reads it against all the rules and quotes exactly
    what's wrong and how to fix it.
  - **Fix it for me** rewrites it safely, keeping the meaning, then
    re-checks it.
  - **Full rules check** on any clip opens it here, already filled in.
- **Can my channel get monetized?** Enter your numbers to see which tier
  you qualify for and exactly what's missing. The calculator includes
  the February 1, 2027 change: new channels will need 8,000 watch hours
  or 20 million Shorts views, double today.
- **Is my channel at risk?** These are the channel-level rules that
  remove whole channels from monetization:
  - reused content (clip channels)
  - inauthentic or mass-produced content (AI or template channels)
  - AI disclosure
  - copyright
- **Check for rule updates.** Reads YouTube's official policy pages,
  shows exactly what changed since your last check, and has an AI
  explain it in plain English.

This is a careful first pass, not a guarantee. YouTube's reviewers make
the final call, and context matters: news, education and calm
discussion get more leeway than content made to shock.

## AI engines: every AI in one (much faster)

Click **AI engines** at the top right, tick **Use cloud AI**, paste the
key of any AI you want, then click **Test the keys**. Only the AIs you
add a key for are used. Each one has a **get a key** link next to it.

| AI | Cost | What it does |
|---|---|---|
| **Groq** | free | writes down the speech (1 hour of video in about a minute) and picks moments |
| **Gemini** | free | picks moments |
| **OpenRouter** | free models | picks moments |
| **Claude** | paid, per use | picks moments |
| **ChatGPT** (OpenAI) | paid, per use | writes down the speech and picks moments |
| **Grok** (xAI) | paid, per use | picks moments |

The order they're tried in:

- **Writing down the speech:** Groq &rarr; ChatGPT &rarr; Whisper on
  this PC.
- **Picking the viral moments:** Gemini &rarr; Groq &rarr; OpenRouter
  &rarr; Claude &rarr; ChatGPT &rarr; Grok &rarr; Ollama on this PC
  &rarr; built-in scorer.

Free ones are always tried first, and paid ones only when the free ones
are busy or used up.
- When an AI is rate-limited, used up, out of credit, or its key is
  wrong, the next one takes over by itself. The page shows which AI did
  what, and why one was skipped.
- When a company retires a model, the app picks that company's current
  one automatically.
- With cloud AI on, your PC only cuts the clips.

**Good to know:**
- A ChatGPT Plus or Claude Pro subscription is **not** an API key. The
  paid keys are separate pay-per-use accounts, and Clip Factory only
  uses them when the free ones can't answer.
- Keys stay on this PC, in `ai_keys.json`. With cloud AI on, the
  video's audio and text are sent to those companies to be processed.
- Turn cloud AI off any time and everything runs on your PC again.

## How it avoids mistakes

- **Cuts.** Clips always start and end on a full sentence, never in the
  middle of a word. Picked clips never overlap each other.
- **Every AI's answers are checked.**
  - The AIs are put in strict JSON mode, and every answer is checked:
    every clip needs a score from 1 to 10 and a title.
  - Anything missing or invalid is asked for again, up to 3 times, and
    only for the clips that were wrong.
  - If one AI fails, the next takes over. If every AI fails, isn't
    running, or has no model installed, the built-in scorer rates those
    clips. The run finishes
    anyway and the page tells you what happened.
- **Asking for too many.** If you ask for more clips than the video has
  room for, you get as many as fit, and the page says so.
- **Unfinished files.** A clip only appears once it's completely
  written, so a download is never half a file.
- **Transcripts are saved.** Making a second batch from the same video
  (different length, layout or count) skips straight to picking
  moments.

## How long it takes (i7-8700, 16 GB)

These are rough numbers for a 1-hour video:

| Step | Only this PC | With cloud AI |
|---|---|---|
| Writing down the speech | about 5-10 min ("Better" accuracy is 2-3x slower) | about 1 min |
| Rating every moment | about 10-25 min with Ollama | about 1-2 min |
| Each clip | about 20-40 s | the same: your PC cuts the clips either way |

Clip 1 is ready right after the rating step.

The GTX 1630 isn't used for cutting: it has no video encoder, so the CPU
does it.

Stop any time with **Stop**. The clips already finished are kept.
