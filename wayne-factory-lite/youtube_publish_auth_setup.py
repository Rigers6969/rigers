"""One-time login per YouTube channel so this app can upload videos to it
automatically. Separate from youtube_auth_setup.py (that one is for
reading revenue) - this needs the "upload" scope instead, which lets it
actually post videos, not just read numbers.

Why per-channel: the YouTube Data API always uploads to whichever
channel the OAuth login itself is tied to - there's no "choose the
destination channel per upload" option, even when one Google account
manages several channels (Brand Accounts) - see developers.google.com/
youtube/v3/docs/videos/insert (videos.insert "uploads a video to the
channel associated with the request"). So if Deep Field and The Archive
share one Google login, you run this script twice, once per channel,
switching which channel you're acting as in the browser each time -
each run saves its own token file.

Setup (once per channel):
    1. Google Cloud Console (console.cloud.google.com) -> APIs & Services
       -> Library -> enable "YouTube Data API v3" (same project as your
       existing API key is fine - same as youtube_auth_setup.py's setup).
    2. APIs & Services -> Credentials -> your existing OAuth client ID
       (the same client_secret.json from youtube_auth_setup.py works
       here too - no need for a second one).
    3. Run:
           python youtube_publish_auth_setup.py "Deep Field"
       Your browser opens - IMPORTANT: before approving, use YouTube's
       account/channel switcher (top-right avatar) to switch to the
       Deep Field channel specifically, THEN approve. If you approve
       while "acting as" the wrong channel, uploads will go to the
       wrong place.
    4. Run it again for your other channel:
           python youtube_publish_auth_setup.py "The Archive"
       switching to that channel in the browser before approving this
       time.

Each run saves token_upload_<channel-slug>.json, reused automatically
after that - you won't need to log in again unless you revoke access.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CLIENT_SECRET_PATH = "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _slugify(channel: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", channel.lower()).strip("-") or "channel"


def token_path_for(channel: str) -> Path:
    return Path(f"token_upload_{_slugify(channel)}.json")


def main() -> int:
    if len(sys.argv) != 2:
        print('Usage: python youtube_publish_auth_setup.py "Channel Name"')
        print('Example: python youtube_publish_auth_setup.py "Deep Field"')
        return 1
    channel = sys.argv[1]

    if not Path(CLIENT_SECRET_PATH).exists():
        print(f"Missing {CLIENT_SECRET_PATH} in this folder.")
        print("Download it from Google Cloud Console first - see this file's docstring for the exact steps.")
        return 1

    from google_auth_oauthlib.flow import InstalledAppFlow

    print(f'About to log in for "{channel}". When the browser opens, switch to that channel')
    print("using YouTube's account switcher BEFORE approving access.\n")

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
    creds = flow.run_local_server(port=0)
    token_path = token_path_for(channel)
    token_path.write_text(creds.to_json())

    print(f"\nSaved {token_path}. Videos produced under channel \"{channel}\" will now auto-upload there.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
