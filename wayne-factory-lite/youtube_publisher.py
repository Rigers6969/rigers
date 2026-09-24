"""Uploads a produced video to YouTube automatically - the last
automatic step in produce_video(), same tier as auto-captions/music/
review. Uses the per-channel OAuth token from
youtube_publish_auth_setup.py (token_upload_<channel-slug>.json) - if
that channel hasn't been connected yet, publish_video() returns None
instead of raising, so an unconnected channel just quietly doesn't
publish rather than breaking production.

Real, documented behavior worth knowing (see this repo's chat history
for the verification): the YouTube Data API always uploads to whichever
channel the OAuth login is tied to - videos.insert has no "choose the
destination channel" parameter, even for an account managing several
Brand Account channels. That's why auth is per-channel, not per-app.

Also worth knowing: each upload costs 1,600 quota units against your
Google Cloud project's default 10,000-unit daily cap - about 6 uploads/
day, shared across every channel using the same project's API
credentials (Deep Field and The Archive both do, if you set them up
under the same Google Cloud project).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from youtube_publish_auth_setup import SCOPES as UPLOAD_SCOPES
from youtube_publish_auth_setup import token_path_for

ProgressCB = Callable[[str], None]

DEFAULT_CATEGORY_ID = "27"  # Education - fits general documentary content


class PublishError(RuntimeError):
    pass


def _load_credentials(channel: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_file = token_path_for(channel)
    if not token_file.exists():
        return None  # not connected yet - not an error, just "nothing to publish with"

    creds = Credentials.from_authorized_user_file(str(token_file), UPLOAD_SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_file.write_text(creds.to_json())
        else:
            raise PublishError(
                f'YouTube login for "{channel}" has expired or been revoked - '
                f'run `python youtube_publish_auth_setup.py "{channel}"` again.'
            )
    return creds


def publish_video(
    video_dir: Path, channel: str, privacy_status: str = "public",
    category_id: str = DEFAULT_CATEGORY_ID, progress: Optional[ProgressCB] = None,
) -> Optional[dict]:
    """Uploads video_dir's finished video (final_edited.mp4 if the
    auto-edit step made one, else plain final.mp4) to `channel`'s
    YouTube channel, using metadata.json's own youtube.title/
    description/tags, and sets thumbnail.jpg as the video's thumbnail
    if one exists. Returns {"video_id", "url"} on success, or None if
    this channel isn't connected yet."""
    def report(msg: str) -> None:
        if progress:
            progress(msg)

    creds = _load_credentials(channel)
    if creds is None:
        report(f'YouTube not connected for "{channel}" - skipping publish '
               f'(run youtube_publish_auth_setup.py to enable it).')
        return None

    video_path = video_dir / "final_edited.mp4"
    if not video_path.exists():
        video_path = video_dir / "final.mp4"
    if not video_path.exists():
        raise PublishError("No assembled video to publish.")

    metadata_path = video_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    yt = metadata.get("youtube", {})
    title = (yt.get("title") or video_dir.name)[:100]
    description = yt.get("description", "")
    tags = yt.get("tags", [])

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {"title": title, "description": description, "tags": tags, "categoryId": category_id},
        "status": {"privacyStatus": privacy_status},
    }
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

    report(f'Uploading "{title}" to YouTube ({channel})...')
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            report(f"Upload {int(status.progress() * 100)}%...")

    video_id = response["id"]

    thumbnail_path = video_dir / "thumbnail.jpg"
    if thumbnail_path.exists():
        report("Setting thumbnail...")
        try:
            youtube.thumbnails().set(videoId=video_id, media_body=str(thumbnail_path)).execute()
        except Exception as exc:
            report(f"Thumbnail upload failed ({exc}) - video is still published, just without a custom thumbnail.")

    url = f"https://www.youtube.com/watch?v={video_id}"
    report(f"Published: {url}")
    return {"video_id": video_id, "url": url}
