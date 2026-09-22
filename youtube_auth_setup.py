"""One-time login so the dashboard can read your REAL YouTube ad revenue.

A plain API key (what config.json already uses for subscriber/view counts)
cannot read revenue - that's a restricted, account-owner-only number, so
Google requires an actual OAuth login, not just a key.

Setup (once):
    1. Google Cloud Console (console.cloud.google.com) -> APIs & Services
       -> Library -> enable "YouTube Analytics API" (same project you
       already used for the YouTube Data API v3 key is fine).
    2. APIs & Services -> Credentials -> Create Credentials -> OAuth
       client ID -> Application type "Desktop app" -> Create.
    3. Download it (the download icon next to the new client) and save it
       in this same folder as client_secret.json.
    4. If prompted to configure an OAuth consent screen first: choose
       "External", fill in an app name (anything) and your own email for
       support/developer contact, and under "Test users" add your own
       Google account. Since this is only ever you logging into your own
       app, it never needs Google's verification review.
    5. Run this script:
           python youtube_auth_setup.py
       Your browser opens once for you to log in and approve access.
       After that, token_analytics.json is saved and reused automatically
       - you won't need to log in again unless you revoke access.
"""
from __future__ import annotations

from pathlib import Path

CLIENT_SECRET_PATH = "client_secret.json"
TOKEN_PATH = "token_analytics.json"
SCOPES = ["https://www.googleapis.com/auth/yt-analytics-monetary.readonly"]


def main() -> int:
    if not Path(CLIENT_SECRET_PATH).exists():
        print(f"Missing {CLIENT_SECRET_PATH} in this folder.")
        print("Download it from Google Cloud Console first - see this file's docstring for the exact steps.")
        return 1

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
    creds = flow.run_local_server(port=0)
    Path(TOKEN_PATH).write_text(creds.to_json())

    print(f"\nSaved {TOKEN_PATH}. The dashboard's revenue goal bar will now show your real number.")
    print("(If your channel isn't in the YouTube Partner Program yet, that number is correctly $0.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
