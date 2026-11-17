from __future__ import annotations

# Safe, read-only OAuth validation trigger after PR #57 production deployment.

import os
import sys
import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
YOUTUBE_URL = "https://www.googleapis.com/youtube/v3"


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required GitHub Actions secret: {name}")
    return value


def refresh(label: str, client_id: str, client_secret: str, refresh_token: str, required_scope: str) -> str:
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if not response.ok:
        # Do not print response bodies: authentication endpoints may include sensitive diagnostics.
        raise RuntimeError(f"{label}: OAuth refresh failed (HTTP {response.status_code}). Check client/token pairing, revocation, and consent.")
    payload = response.json()
    access_token = str(payload.get("access_token", "")).strip()
    if not access_token:
        raise RuntimeError(f"{label}: OAuth refresh returned no access token.")
    info = requests.get(TOKENINFO_URL, params={"access_token": access_token}, timeout=20)
    if not info.ok:
        raise RuntimeError(f"{label}: Google tokeninfo validation failed (HTTP {info.status_code}).")
    scopes = set(str(info.json().get("scope", "")).split())
    if required_scope not in scopes:
        raise RuntimeError(f"{label}: required OAuth scope is not granted: {required_scope}")
    print(f"{label}: refresh OK; required scope confirmed; token value withheld.")
    return access_token


def main() -> int:
    upload_token = refresh(
        "YouTube upload OAuth",
        required("YOUTUBE_CLIENT_ID"),
        required("YOUTUBE_CLIENT_SECRET"),
        required("YOUTUBE_REFRESH_TOKEN"),
        "https://www.googleapis.com/auth/youtube.upload",
    )
    comment_client_id = os.getenv("YOUTUBE_COMMENT_CLIENT_ID", "").strip() or required("YOUTUBE_CLIENT_ID")
    comment_client_secret = os.getenv("YOUTUBE_COMMENT_CLIENT_SECRET", "").strip() or required("YOUTUBE_CLIENT_SECRET")
    comment_token = refresh(
        "YouTube comment OAuth",
        comment_client_id,
        comment_client_secret,
        required("YOUTUBE_COMMENT_REFRESH_TOKEN"),
        "https://www.googleapis.com/auth/youtube.force-ssl",
    )
    # Read-only channel ownership/access check. No video upload, comment, or metadata mutation.
    channel = requests.get(
        f"{YOUTUBE_URL}/channels",
        params={"part": "id,snippet", "mine": "true"},
        headers={"Authorization": f"Bearer {comment_token}"},
        timeout=30,
    )
    if not channel.ok:
        raise RuntimeError(f"YouTube read-only channel check failed (HTTP {channel.status_code}).")
    items = channel.json().get("items") or []
    if not items:
        raise RuntimeError("OAuth succeeded, but Google returned no YouTube channel for the authorized account.")
    for item in items:
        snippet = item.get("snippet") or {}
        print("YouTube channel access OK: " + str(snippet.get("title") or "channel title unavailable"))
    print("SAFE_CHECK_COMPLETE: no upload, comment, description update, or sheet write was performed. # rerun after comment token rotation")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"YOUTUBE_OAUTH_SAFE_CHECK_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
