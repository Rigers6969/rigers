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

**Get the newest version:** double-click **`update.bat`**. It downloads the
new files and keeps your keys, logins and videos.

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
clippers.

### Can I clip them? (the AI checks for you)

Click **Can I clip them?** next to **Scan** to check every show or
streamer on your list. You can also click **Can I clip this?** on any
single video. For each channel, the AI reads its channel description and
its 3 latest video descriptions, which is where shows post their
clipping rules, and gives a verdict:

| Verdict | Meaning |
|---|---|
| **Clipping allowed** | The show invites clippers or links a clipping program. You get a **Join their clipping program** link, plus any rules they set (e.g. "tag us"). |
| **Says no reuploads** | The show warns against reuploads or copyright use. Clipping it risks copyright strikes, and the app asks you to confirm before clipping one of its videos. |
| **Clipping: unclear** | The show doesn't say either way. Ask it before clipping. |

**It never invents permission.**
- Every quote shown is copied word for word from the channel. Quotes and
  links the AI can't back up with the real text are thrown away.
- An "allowed" with no real quote is downgraded to "unclear".
- With no AI available, a built-in check still finds clipping programs
  and "no reupload" warnings.
- Results are saved for 7 days.

This is a helper, not legal advice. Only a show's written rules or its
clipping program give you real permission.

**"HTTP Error 403: Forbidden"** means the site refused the download. Clip
Factory then tries again by itself: disguised as a normal browser (Kick and
Twitch always need this), then at 720p. If it still fails, set **If a site
blocks the download, use my browser login** to Firefox (works best) or Edge,
log in to YouTube/Kick in that browser, and try again. The login is read on
this PC only.

## Make clips (second tab)

1. **Pick the video.** Choose it from the list (anything you put in the
   `input` folder shows up there), upload it, or paste its path
   (right-click the file, then **Copy as path**).
2. **Video type:** **Streamer** (Twitch, Kick, YouTube live) makes 15-45 s
   clips of big reactions, rage, fails and chat moments, for Chat Lost It.
   **Podcast** makes 30-90 s split-screen clips of hot takes and stories.
3. **How many clips:** 1-100. **Clip length:** 20-60 s works well for
   Shorts, Reels and TikTok.
4. **Layout:**
   - **Fill screen** for one person talking to the camera.
   - **Whole picture + blurred background** for gameplay or screen
     recordings.
   - **Podcast - split screen** for two people side by side.
   - **Clip on top + gameplay below** puts your clip in the top half and
     a gameplay video (Minecraft parkour, GTA driving...) in the bottom
     half, with no sound, to keep people watching. Add gameplay videos
     with **Add a gameplay video**, or put them in the `gameplay` folder.
     Each clip gets a random part of one. **Record the gameplay
     yourself** (e.g. with OBS); gameplay downloaded from other YouTubers
     can get your clips claimed.
5. Click **Make clips**.

**Viral captions** (setting **Captions**):
- **Pop:** 1-2 huge words at a time. The word being said pops in big and
  yellow, strong words (money, never, insane...) are green.
- **Box:** the word being said sits in a coloured box (the TikTok look).
- **Story:** big, bold, slanted key words and small filler words that
  build up word by word, with the last key word underlined (the podcast
  clip look: *PROCRASTINATING / is choosing / to delay*).
- **Word-by-word** and **Simple** are the classic captions.

**Captions on the screen:** **In the middle** (the default, best for
Shorts) or **Lower third**. **Emoji pops** puts an emoji above the
captions when a matching word is said (laugh 😂, money 💰, insane 🔥...),
at most 4 per clip.

**Background music (no copyright):** add a track with **Add a track** (or
put MP3s in the `music` folder), then choose it, or **Mix all my tracks**
for a different one per clip. The music gets quieter by itself whenever
someone talks. Get the music from **YouTube Studio → Audio Library** and
filter **Attribution not required**. Never use songs from Spotify or
TikTok: they get your clips claimed.

**Captions in another language** (e.g. English clips for an Albanian
channel): set **Captions and titles in** to **Albanian (Shqip)**. The AI
translates what's said into natural, spoken Albanian, and the captions still
light up word by word with the voice. Titles, descriptions, hashtags and
thumbnails come out in Albanian too, and the voices stay original. It
needs an AI engine; a free Gemini key translates best. Spanish,
Portuguese, French, German, Italian and Turkish work the same way.

**Every clip comes with everything for posting:**
- a **title**, **description**, **tags** and **hashtags**, each with a copy
  button on the clip
- a **cover** (1080x1920) for YouTube Shorts, Instagram Reels and Facebook
  Reels, and a **thumbnail** (1280x720) for anything wide. Both use the
  clip's best frame with the hook in big letters.

Clips made before thumbnails existed: open the run and click **Make
thumbnails**.

**Clipping campaigns (Whop):** open **Clipping campaign** under the
settings and tick **Use these campaign rules**:
- **Every title must mention** (e.g. `Preme`): added to titles,
  descriptions, tags and hashtags when missing.
- **Never mention** (e.g. `Drake`): removed from all text, and moments that
  talk about it are skipped.
- **Clips must be about** (e.g. `Preme`): the AI only picks moments with
  them.
- **Campaign logo:** add the PNG the campaign gives you. It goes on every
  clip, centered and clearly visible, never at an edge (campaigns reject
  hidden logos). Choose the position, size and opacity.

Untick the box for your normal clips.

Clips are numbered 1, 2, 3... from most to least viral. Every run is
saved in `output/<date>-<video name>/`. **Open folder** shows it in File
Explorer, and **Download all (zip)** gets every finished clip plus a
`titles.txt`. Click any run under **Past runs** to open it again.

## My channels (fourth tab): all your channels in one place

Shows every channel's views together, measured against your goal, e.g.
**10M views across 4 channels by December 1**.

**Setup (once):** click **Channels & goal**, type each channel's
@handle, set the goal and the dates, and click **Save and check now**.

**What it shows:**
- **Views this week**, with the change from last week, and your
  progress toward the goal.
- **Needed per day:** how many views a day you need from now on to hit
  the goal, next to your actual pace and where that pace ends up by the
  deadline.
- **Views per day:** a 14-day chart, stacked by channel. Hover a bar for
  the numbers, or click **Show as table**.
- **This week, channel by channel:**
  - subscribers, and how far each channel is toward 1,000
  - views this week and last week
  - views split between Shorts and long videos
  - each channel's best video
- **Top videos this week** across all channels.
- **What to do next week:** 3 concrete actions from the built-in coach.
  Click **Ask the AI coach** for a deeper read from the AI engines.

**How it works:**
- The app checks your channels when it starts and then every 3 hours
  while it's open, or when you click **Refresh now**.
- "Views this week" is the difference between those checks, so the
  numbers fill in over the first days after setup.
- **The numbers come from the YouTube Data API** (exact numbers) when an
  API key is available. It finds Wayne Factory's key in `config.json`
  automatically, or you can paste one.
- **With no key,** it reads the public channel pages. YouTube rounds
  those numbers (e.g. 1.2K), so small changes can look bumpy.
- Watch hours aren't public. YouTube Studio's **Earn** tab has those.

## Phone alerts (in the My channels tab)

Messages on your phone through **ntfy**, a free app for Android and
iPhone, with no account:
- **Clips are ready** when a clip run finishes.
- **One of my videos is going viral:** a video gains 10K+ views in about
  3 hours, or passes 10K, 50K, 100K, 500K, 1M... views.
- **A streamer is blowing up:** a new video from your streamer list gets
  20K+ views an hour, so you can clip it first. Checked every 2 hours.
- **30 minutes before a post** you haven't scheduled in YouTube Studio
  yet.
- **An automatic upload failed.**
- **Weekly report** on Monday morning: views this week and your goal.

**Setup:** install ntfy on your phone, tap **+**, type the name the panel
shows, then tick **On** and click **Send a test**. You can change the
numbers and turn each alert on or off.

Alerts come from Clip Factory, so it has to be running on the PC.

## Campaigns ($): get paid per view (Whop)

Whop's **Content Rewards** campaigns pay you per 1,000 views for clips of
a creator. This tab reads a campaign and tells you if it's worth it.

1. On whop.com open **Content Rewards** and click a campaign.
2. Press **Ctrl+A**, then **Ctrl+C**.
3. Paste it into the box and click **Read it**.

For each campaign it shows:
- the pay per 1,000 views on each platform, after Whop's 10%
- the budget left, and how many views a clip needs before it pays
- a verdict, **Good**, **OK** or **Skip**, with an example of what 10 clips
  could earn
- who to mention, who never to mention, required hashtags, the video to
  clip and the logo to download
- **every rule**, as a checklist to read before posting

**Use for my next clips** fills in Make clips for you: video type, the
campaign rules, the hashtags and the video link. Add the campaign's logo
there, then make the clips.

Numbers and links come straight from the page. The AI only adds the
plain-language checklist, and a name it suggests is kept only if it is
really on the page.

## Calendar: posting goals

Set a goal like **10 videos per channel every day** (or every week, or 10
in total as a one-time goal). The tab shows:
- **Today** (or this week): each channel's progress, e.g. "7 of 10 - 3 to
  go". A channel that reaches the goal is **closed ✓**. When every
  channel is done, the day is closed.
- **Calendar:** every day with each channel's count. Green means the goal
  was met, red means it was missed, and grey shows what's still scheduled.
  Your **streak** counts days in a row with every goal met.
- **One-time goals** close by themselves and move to **Finished goals**.

**How it counts:**
- Channels with an @handle in My channels are counted from YouTube by
  themselves, checked every 3 hours or when you click **Refresh counts**.
- Other channels count the posts you mark **Done - I scheduled them** in
  Publish.
- **+1 / -1** for anything else (e.g. TikTok), or to fix a day. Click a day
  to change it.

## My videos (sixth tab): everything in one place

Every video, without searching through folders:
- **Clips I made:** every clip, with its picture. **Play**, **Download**,
  **Download all (zip)**, or **Open** the run.
- **Downloaded videos:** what you downloaded. **Play**, **Make clips**
  (opens it in Make clips), or **Show file**.
- **Wayne Factory videos:** finished videos and Shorts from Wayne Factory.

Use the search box to find one by title.

**Everything is saved, once:** your channels, settings, AI keys, schedule,
logins and videos are all kept in this folder (`clip-factory`). They're
there every time you open Clip Factory, even in another browser, and
updates never delete them.

## Publish (fifth tab): the auto publisher

Puts every video for all 4 channels on one weekly schedule, then uploads
them to YouTube at the right times.

**The weekly plan (60-day challenge):**
- **Paper Trail:** full video Mon and Thu 17:00, a Short every day at 12:00
- **Science:** full video Tue and Fri 17:00, a Short every day at 12:00
- **History:** full video Wed and Sat 17:00, a Short every day at 12:00
- **Hot Mic Moments:** a Short every hour, 09:00-23:00
- **At least 1 hour between any two posts,** all channels together. If two
  channels want the same time, one moves to the next free hour.

**Change it:** open **Posting times** in the Schedule. Set the time
between posts (30 minutes to 3 hours), and each channel's Shorts: 1 a day,
3 a day, every 2 hours, or every hour. Then click **Re-plan all to-do
posts**.

**Time tracker:** the top of the Schedule counts down to the next post,
shows today's posts in order, and warns when a post missed its time. In
automatic mode, missed posts get new times one by one. They never all go
out at once.

**Setup (once):**
1. **client_secret.json:** a free Google Cloud file. The tab shows the
   steps (about 10 minutes). Put the file in the `clip-factory` folder.
2. **Connect** each channel. Google's login opens; pick that channel.
   If you pick the wrong one, the tab tells you.
3. **Prepare the approval request:** click it, copy the answers into
   Google's form, and send it. Approval is free and usually takes 1-4
   weeks.

**Every week:**
1. **Add videos:** clips from Clip Factory (with their descriptions and
   tags) and finished Wayne Factory videos and their Shorts.
2. Click **Fill the schedule**. Each video gets the next free time of its
   channel. Change any time or channel in the list.

**Posting with YouTube Studio (free, no Google setup needed):** click
**Get this week ready for YouTube Studio**. Each channel's next 7 days of
videos go into `to-upload\<channel>`, named by their titles, with a file
`00 - titles, descriptions, tags.txt`. Then, for each channel:
1. Click **Open folder**, and open YouTube Studio for that channel.
2. **Create** -> **Upload videos** -> select all the videos (up to 15 at a time).
3. Paste each video's description and tags from the text file, and set
   **Visibility** -> **Schedule** to its time.
4. Click **Done - I scheduled them**.

**Until Google approves:** YouTube locks everything an unapproved app
uploads as private. So the schedule is a checklist. For each item:
1. **Show file**, then **Open YouTube Studio** and upload it there.
2. Paste the **Copy title**, **Copy description** and **Copy tags** text.
3. Set **Schedule** to the time shown, then click **Scheduled** in the app.

**After Google approves:** tick **Google approved my app**. The app then
uploads each video up to 3 days before its time, as private with
YouTube's own publish time. YouTube makes it public at that time, even if
the PC is off. Keep the app open at least every couple of days.

**Limits:**
- YouTube allows about 6 uploads a day per Google project (10,000 quota
  units). The approval form asks for more.
- Custom thumbnails need a phone-verified channel.

The login files (`tokens/`) and `client_secret.json` stay on this PC.

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

### OmniRoute (your own free AI router)

[OmniRoute](https://omniroute.online/) runs on your PC and gives one
address in front of many AIs, including lots of free ones. When one is busy
or used up, it switches by itself. Clip Factory can use it **first** for
picking moments, titles, translations, campaigns and the coach:

**start.bat sets it up by itself:** it installs Node.js and OmniRoute the
first time, then starts OmniRoute in a small window ("OmniRoute - free AI
router"). Leave that window open. Clip Factory uses OmniRoute whenever it's
running; **AI engines** shows "OmniRoute is running".

- Add more free AIs in its dashboard: http://localhost:20128
- If **Test the keys** says OmniRoute didn't accept the key, create an API key
  in the dashboard and paste it under OmniRoute in AI engines.
- Don't want it? Create an empty file called `no-omniroute.txt` in the
  clip-factory folder, or untick it in AI engines.

If OmniRoute isn't running, Clip Factory skips it at once and uses the next
AI.

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
