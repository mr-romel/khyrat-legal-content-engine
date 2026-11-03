from __future__ import annotations

import json
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build

BLOG_URL = os.getenv("BLOGGER_URL", "https://askmahmoudkhyrat.blogspot.com/").strip()
SITEMAP_URL = os.getenv("BLOGGER_SITEMAP_URL", BLOG_URL.rstrip("/") + "/sitemap.xml")
SCOPE = "https://www.googleapis.com/auth/webmasters"


def main() -> int:
    raw = (os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_CREDENTIALS") or "").strip()
    if not raw:
        raise RuntimeError("Google service-account credentials are missing.")
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Google service-account credentials are not valid JSON.") from exc

    credentials = service_account.Credentials.from_service_account_info(info, scopes=[SCOPE])
    client = build("searchconsole", "v1", credentials=credentials, cache_discovery=False)
    site = client.sites().get(siteUrl=BLOG_URL).execute()
    permission = str(site.get("permissionLevel", ""))
    if permission not in {"siteOwner", "siteFullUser", "siteRestrictedUser"}:
        raise RuntimeError(f"Unexpected Search Console permission for {BLOG_URL}: {permission!r}")

    sitemaps = client.sitemaps().list(siteUrl=BLOG_URL).execute().get("sitemap", []) or []
    match = next((item for item in sitemaps if str(item.get("path", "")).rstrip("/") == SITEMAP_URL.rstrip("/")), None)
    if match is None:
        print(f"Submitting sitemap: {SITEMAP_URL}")
        client.sitemaps().submit(siteUrl=BLOG_URL, feedpath=SITEMAP_URL).execute()
    else:
        print(f"Sitemap already registered: {SITEMAP_URL}")

    verified = client.sitemaps().list(siteUrl=BLOG_URL).execute().get("sitemap", []) or []
    result = next((item for item in verified if str(item.get("path", "")).rstrip("/") == SITEMAP_URL.rstrip("/")), None)
    if result is None:
        raise RuntimeError("Search Console did not return the sitemap after submission.")
    print(json.dumps({
        "site": BLOG_URL,
        "permission": permission,
        "sitemap": result.get("path"),
        "lastSubmitted": result.get("lastSubmitted"),
        "isPending": result.get("isPending"),
        "warnings": result.get("warnings"),
        "errors": result.get("errors"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
