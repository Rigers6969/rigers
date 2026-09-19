"""Auto-publishing helpers for The Wayne Factory's finished clips.

Neither function here can do anything until you've completed a one-time
manual setup on each platform - this is a deliberate security boundary both
platforms enforce, not something any code can shortcut:

YouTube (Data API v3):
    1. Create a project in Google Cloud Console, enable the YouTube Data API v3.
    2. Create an OAuth 2.0 Desktop app client, download it as client_secret.json.
    3. First call opens a browser once for you to grant access; after that a
       token is cached to token.json and reused automatically.

Instagram (Graph API - requires a Business/Creator account linked to a
Facebook Page):
    1. Create a Meta for Developers app, add the Instagram Graph API product.
    2. Generate a long-lived Page access token with instagram_content_publish
       permission, and find your Instagram Business Account ID.
    3. The video must already be reachable at a public URL - the Graph API
       fetches it from there, it does not accept a direct file upload.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import requests

GRAPH_API_VERSION = "v21.0"


def upload_to_youtube(
    video_path: Path,
    title: str,
    description: str,
    tags: Optional[list[str]] = None,
    client_secret_path: str = "client_secret.json",
    token_path: str = "token.json",
    privacy_status: str = "private",
) -> str:
    """Uploads a video to YouTube via the Data API v3. Returns the new video ID.

    Requires: pip install google-api-python-client google-auth-oauthlib
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    if not Path(video_path).exists():
        raise FileNotFoundError(f"video not found: {video_path}")

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    creds = None
    token_file = Path(token_path)
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(client_secret_path).exists():
                raise FileNotFoundError(
                    f"YouTube OAuth client secret not found at {client_secret_path}. "
                    "Download it from Google Cloud Console (APIs & Services > Credentials)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, scopes)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json())

    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {"title": title[:100], "description": description[:5000], "tags": tags or []},
        "status": {"privacyStatus": privacy_status},
    }
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _status, response = request.next_chunk()
    return response["id"]


def post_to_instagram(
    caption: str,
    access_token: str,
    ig_user_id: str,
    video_public_url: str,
    poll_interval_seconds: float = 5.0,
    max_poll_attempts: int = 60,
) -> str:
    """Publishes a Reel to Instagram via the Graph API. Returns the published media ID.

    `video_public_url` must already be a URL the Graph API can fetch the
    video from - Instagram does not accept a direct file upload here.
    """
    base = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{ig_user_id}"

    create_resp = requests.post(
        f"{base}/media",
        data={
            "media_type": "REELS",
            "video_url": video_public_url,
            "caption": caption[:2200],
            "access_token": access_token,
        },
        timeout=30,
    )
    create_resp.raise_for_status()
    creation_id = create_resp.json()["id"]

    for _ in range(max_poll_attempts):
        status_resp = requests.get(
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/{creation_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=30,
        )
        status_resp.raise_for_status()
        status_code = status_resp.json().get("status_code")
        if status_code == "FINISHED":
            break
        if status_code == "ERROR":
            raise RuntimeError(f"Instagram failed to process the video (creation_id={creation_id})")
        time.sleep(poll_interval_seconds)
    else:
        raise TimeoutError(f"Instagram video processing did not finish in time (creation_id={creation_id})")

    publish_resp = requests.post(
        f"{base}/media_publish",
        data={"creation_id": creation_id, "access_token": access_token},
        timeout=30,
    )
    publish_resp.raise_for_status()
    return publish_resp.json()["id"]
