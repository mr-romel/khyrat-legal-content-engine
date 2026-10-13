#!/usr/bin/env python3
"""Read-only Blogger OAuth check; forces refresh and never publishes or edits posts."""
from __future__ import annotations

import requests
from google.auth.transport.requests import Request
from blogger_publisher import (
    _credentials,
    _persist_refreshed_blogger_credentials,
    BloggerPublishError,
)


def main() -> int:
    try:
        credentials = _credentials()
        if not credentials.refresh_token:
            raise BloggerPublishError(
                "OAuth credentials do not contain a refresh token. "
                "Run scripts/blogger_oauth.py locally and replace BLOGGER_OAUTH_JSON."
            )

        # Force a real refresh so this workflow validates the refresh token itself,
        # not merely an unexpired access token stored in the secret.
        try:
            credentials.refresh(Request())
        except Exception as exc:
            raise BloggerPublishError(
                f"OAuth refresh failed ({type(exc).__name__}). "
                "Re-authorize locally and update the BLOGGER_OAUTH_JSON secret."
            ) from exc

        _persist_refreshed_blogger_credentials(credentials)

        response = requests.get(
            "https://www.googleapis.com/blogger/v3/users/self/blogs",
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=30,
        )
        if response.status_code in (401, 403):
            raise BloggerPublishError(
                f"Blogger API rejected authorization (HTTP {response.status_code}). "
                "Check the Blogger scope and account access."
            )
        response.raise_for_status()
        blogs = response.json().get("items", [])
        print("BLOGGER_OAUTH_REFRESH=PASS")
        print("BLOGGER_API_ACCESS=PASS")
        print(f"Accessible Blogger blogs: {len(blogs)}")
        for blog in blogs:
            blog_id = str(blog.get("id", ""))
            print(f"- {str(blog.get('name') or 'Untitled blog')} (ID ending: {blog_id[-6:]})")
        if not blogs:
            print("Warning: authorization succeeded, but Google returned no accessible blogs.")
        return 0
    except Exception as exc:
        # Never print credential JSON, authorization headers, or token values.
        print(f"BLOGGER_OAUTH_CHECK=FAIL: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
