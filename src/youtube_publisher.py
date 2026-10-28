"""Upload a finished vertical reel to YouTube as a Short.

Required GitHub Actions secrets:
  YOUTUBE_CLIENT_ID
  YOUTUBE_CLIENT_SECRET
  YOUTUBE_REFRESH_TOKEN
Optional:
  YOUTUBE_PRIVACY_STATUS (default: public)
The refresh token must be granted the YouTube upload scope:
  https://www.googleapis.com/auth/youtube.upload
"""
from __future__ import annotations

import os
from pathlib import Path

import requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def publish_youtube_short(video_path: str, title: str, description: str = "") -> dict[str, str]:
    client_id = os.getenv("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip()
    if not all((client_id, client_secret, refresh_token)):
        raise RuntimeError(
            "YouTube secrets missing: set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, "
            "and YOUTUBE_REFRESH_TOKEN after OAuth consent."
        )

    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if not token_response.ok:
        raise RuntimeError(
            f"YouTube OAuth refresh failed: HTTP {token_response.status_code} "
            f"{token_response.text[:800]}"
        )
    access_token = token_response.json().get("access_token", "")
    if not access_token:
        raise RuntimeError("Google OAuth refresh returned no access token.")

    from google.oauth2.credentials import Credentials
    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError(f"YouTube upload video not found: {path}")
    safe_title = (title or "معلومة قانونية").strip()[:95]
    if "#Shorts" not in safe_title:
        safe_title = (safe_title + " #Shorts")[:100]
    body = {
        "snippet": {
            "title": safe_title,
            "description": (description or "").strip()[:5000],
            "categoryId": "25",
        },
        "status": {
            "privacyStatus": os.getenv("YOUTUBE_PRIVACY_STATUS", "public").strip(),
            "selfDeclaredMadeForKids": False,
        },
    }
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(path), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024),
    )
    response = None
    while response is None:
        _status, response = request.next_chunk()
    video_id = str(response.get("id", "")).strip()
    if not video_id:
        raise RuntimeError("YouTube API returned no video ID.")
    return {"video_id": video_id, "url": f"https://youtube.com/shorts/{video_id}"}


def publish_youtube_short_comment(video_id: str, message: str) -> dict[str, str]:
    """Publish one channel-owned comment on a Short using a separately authorized OAuth token.

    YOUTUBE_COMMENT_REFRESH_TOKEN must be authorized with the youtube.force-ssl scope.
    It is separate from the upload token because OAuth grants do not automatically gain scopes.
    """
    client_id = os.getenv("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("YOUTUBE_COMMENT_REFRESH_TOKEN", "").strip()
    if not all((client_id, client_secret, refresh_token)):
        raise RuntimeError(
            "YouTube comments need YOUTUBE_COMMENT_REFRESH_TOKEN authorized with "
            "https://www.googleapis.com/auth/youtube.force-ssl."
        )
    video_id = str(video_id or "").strip()
    message = str(message or "").strip()
    if not video_id or not message:
        raise ValueError("YouTube video ID and comment text are required.")
    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if not token_response.ok:
        raise RuntimeError(
            f"YouTube comment OAuth refresh failed: HTTP {token_response.status_code} "
            f"{token_response.text[:700]}"
        )
    access_token = token_response.json().get("access_token", "")
    if not access_token:
        raise RuntimeError("YouTube comment OAuth refresh returned no access token.")
    from google.oauth2.credentials import Credentials
    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
    )
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    response = youtube.commentThreads().insert(
        part="snippet",
        body={"snippet": {
            "videoId": video_id,
            "topLevelComment": {"snippet": {"textOriginal": message}},
        }},
    ).execute()
    comment_id = str(response.get("id", "")).strip()
    if not comment_id:
        raise RuntimeError("YouTube API returned no comment thread ID.")
    return {"comment_id": comment_id}
