#!/usr/bin/env python3
"""Read-only check for Blogger OAuth credentials. Never publishes or edits posts."""
from __future__ import annotations

import os
import requests
from blogger_publisher import _credentials, BloggerPublishError

def main() -> int:
    try:
        credentials = _credentials()
        response = requests.get(
            "https://www.googleapis.com/blogger/v3/users/self/blogs",
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=30,
        )
        if response.status_code == 401 and credentials.refresh_token:
            # _credentials already refreshes expired tokens. This handles a token
            # rejected early by Google without exposing credential material.
            from google.auth.transport.requests import Request
            credentials.refresh(Request())
            response = requests.get(
                "https://www.googleapis.com/blogger/v3/users/self/blogs",
                headers={"Authorization": f"Bearer {credentials.token}"},
                timeout=30,
            )
        if response.status_code in (401, 403):
            raise BloggerPublishError(
                f"Blogger API rejected the authorization (HTTP {response.status_code}). "
                "Check the granted Blogger scope, account access, and Google OAuth status."
            )
        response.raise_for_status()
        blogs = response.json().get("items", [])
        print("BLOGGER_OAUTH_CHECK=PASS")
        print(f"Accessible Blogger blogs: {len(blogs)}")
        for blog in blogs:
            print(f"- {str(blog.get('name') or 'Untitled blog')} (ID ending: {str(blog.get('id', ''))[-6:]})")
        if not blogs:
            print("Warning: authorization succeeded, but Google returned no accessible blogs.")
        return 0
    except Exception as exc:
        # Do not dump credential JSON, request headers, or tokens.
        print(f"BLOGGER_OAUTH_CHECK=FAIL: {type(exc).__name__}: {exc}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
