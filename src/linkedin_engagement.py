from __future__ import annotations

import os
import time
from dataclasses import dataclass
from urllib.parse import quote

import requests

from linkedin_publisher import (
    LINKEDIN_REST_BASE,
    REST_PROTOCOL,
    TRANSIENT_STATUS_CODES,
    _error_summary,
    _headers,
)

FAKE_POST_URN = "urn:li:share:0000000000000000000"


@dataclass
class CapabilityResult:
    status: str
    http_status: int
    error: str = ""

    @property
    def available(self) -> bool:
        return self.status in {"AVAILABLE", "PROBABLE_AVAILABLE"}


def check_comment_capability(*, token: str, version: str | None = None) -> CapabilityResult:
    """Probe comment authorization without creating a real LinkedIn comment.

    A 403 is treated as a permission block. A 400/404 means the request reached
    the comments endpoint but the synthetic post is invalid, so authorization
    is considered probably available. No real post/comment is created.
    """
    token = (token or "").strip()
    if not token:
        return CapabilityResult("TOKEN_MISSING", 0, "LINKEDIN_ACCESS_TOKEN is empty.")

    endpoint = f"{LINKEDIN_REST_BASE}/socialActions/{quote(FAKE_POST_URN, safe='')}/comments"
    body = {"actor": "urn:li:person:capability-probe", "object": FAKE_POST_URN, "message": {"text": "capability-test"}}
    headers = _headers(token, json_content=True)
    if version:
        headers["Linkedin-Version"] = version

    try:
        response = requests.post(endpoint, headers=headers, json=body, timeout=30)
    except requests.RequestException as exc:
        return CapabilityResult("NETWORK_FAILED", 0, str(exc))

    if response.status_code == 403:
        return CapabilityResult("BLOCKED_PERMISSION", 403, _error_summary(response))
    if response.status_code == 401:
        return CapabilityResult("UNAUTHORIZED_TOKEN", 401, _error_summary(response))
    if response.status_code in TRANSIENT_STATUS_CODES:
        return CapabilityResult("TRANSIENT_FAILURE", response.status_code, _error_summary(response))
    if 200 <= response.status_code < 300:
        return CapabilityResult("AVAILABLE", response.status_code, "")
    return CapabilityResult("PROBABLE_AVAILABLE", response.status_code, _error_summary(response))


def comment_fingerprint(post_urn: str, message: str) -> str:
    import hashlib

    raw = f"{post_urn}|{message.strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def add_linkedin_comment(
    *,
    token: str,
    actor_urn: str,
    post_urn: str,
    message: str,
    dry_run: bool = False,
):
    if dry_run:
        from linkedin_publisher import LinkedInActionResult

        return LinkedInActionResult(
            status="DRY_RUN",
            item_id="",
            error="Comment was not sent because KHYRAT_LINKEDIN_ENGAGEMENT_DRY_RUN is enabled.",
            http_status=None,
        )

    from linkedin_publisher import add_comment

    return add_comment(token=token, actor_urn=actor_urn, post_urn=post_urn, message=message)
