from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import quote

import requests

from linkedin_publisher import LINKEDIN_REST_BASE, TRANSIENT_STATUS_CODES, _error_summary


@dataclass
class CapabilityResult:
    status: str
    http_status: int
    error: str = ""

    @property
    def available(self) -> bool:
        return self.status == "READABLE"


def check_comment_capability(*, token: str, post_urn: str) -> CapabilityResult:
    """Diagnostic read against a real owned post; never uses a fake URN."""
    token = (token or "").strip()
    post_urn = (post_urn or "").strip()
    if not token:
        return CapabilityResult("TOKEN_MISSING", 0, "LINKEDIN_ACCESS_TOKEN is empty.")
    if not post_urn:
        return CapabilityResult("POST_URN_MISSING", 0, "post_urn is empty.")
    endpoint = f"{LINKEDIN_REST_BASE}/socialActions/{quote(post_urn, safe='')}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Linkedin-Version": "202607",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    try:
        response = requests.get(endpoint, headers=headers, timeout=30)
    except requests.RequestException as exc:
        return CapabilityResult("NETWORK_FAILED", 0, str(exc))
    if response.status_code in {401, 403}:
        return CapabilityResult("BLOCKED_PERMISSION", response.status_code, _error_summary(response))
    if response.status_code in TRANSIENT_STATUS_CODES:
        return CapabilityResult("TRANSIENT_FAILURE", response.status_code, _error_summary(response))
    if 200 <= response.status_code < 300:
        return CapabilityResult("READABLE", response.status_code, "")
    if response.status_code == 404:
        return CapabilityResult("POST_NOT_FOUND", 404, _error_summary(response))
    return CapabilityResult("UNKNOWN", response.status_code, _error_summary(response))


def comment_fingerprint(post_urn: str, message: str) -> str:
    raw = f"{post_urn}|{message.strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def add_linkedin_comment(*, token: str, actor_urn: str, post_urn: str, message: str, dry_run: bool = False):
    if dry_run:
        from linkedin_publisher import LinkedInActionResult
        return LinkedInActionResult(status="DRY_RUN", item_id="", error="Dry run: comment not sent.", http_status=None)
    from linkedin_publisher import add_comment
    return add_comment(token=token, actor_urn=actor_urn, post_urn=post_urn, message=message)
