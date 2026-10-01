# Clip Factory

Finds what's going viral right now, downloads it, and turns one long
video (stream, podcast, interview...) into up to **100 vertical Shorts**
in one go: 1080x1920, word-by-word captions,
an optional hook title, and Ollama choosing the most viral moments.

Clips are made **best first** and each one shows up on the page with its
own **Download** button the moment it's finished. You can grab clip 1
while clips 2, 3, 4... are still being cut.

Everything runs on your own PC, for free. No accounts and no uploads to
anywhere.

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

**Ask Ollama what's hot** gives you a short summary of what's trending
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

## Make clips (second tab)

1. **Pick the video.** Choose it from the list (anything you put in the
   `input` folder shows up there), upload it, or paste its path
   (right-click the file, then **Copy as path**).
2. **How many clips:** 1-100. **Clip length:** 20-60 s works well for
   Shorts, Reels and TikTok.
3. **Layout:**
   - **Fill screen** for one person talking to the camera.
   - **Whole picture + blurred background** for gameplay, screen
     recordings, or two people side by side.
4. Click **Make clips**.

Clips are numbered 1, 2, 3... from most to least viral. Every run is
saved in `output/<date>-<video name>/`. **Open folder** shows it in File
Explorer, and **Download all (zip)** gets every finished clip plus a
`titles.txt`. Click any run under **Past runs** to open it again.

## How it avoids mistakes

- **Cuts.** Clips always start and end on a full sentence, never in the
  middle of a word. Picked clips never overlap each other.
- **Ollama's answers are checked.**
  - Ollama is put in strict JSON mode, and every answer is checked:
    every clip needs a score from 1 to 10 and a title.
  - Anything missing or invalid is asked for again, up to 3 times, and
    only for the clips that were wrong.
  - If Ollama still fails, or isn't running, or the model isn't
    installed, the built-in scorer rates those clips. The run finishes
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

| Step | Time |
|---|---|
| Transcribing, "Normal" accuracy | about 5-10 min ("Better" is 2-3x slower) |
| Ollama rating every moment | about 10-25 min, depending on the model |
| Each clip | about 20-40 s; clip 1 is ready right after the rating step |

The GTX 1630 isn't used for cutting: it has no video encoder, so the CPU
does it.

Stop any time with **Stop**. The clips already finished are kept.
