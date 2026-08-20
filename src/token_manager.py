from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from nacl.public import PublicKey, SealedBox

from telegram_bot import notify


RENEWAL_DAYS = 14
GITHUB_API = "https://api.github.com"
FACEBOOK_GRAPH_VERSION = "v26.0"


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _github_headers() -> dict[str, str]:
    token = _env("GH_SECRET_ROTATION_TOKEN")
    if not token:
        raise RuntimeError("GH_SECRET_ROTATION_TOKEN is missing.")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
    }


def _encrypt_secret(public_key_b64: str, value: str) -> str:
    public_key = PublicKey(base64.b64decode(public_key_b64))
    encrypted = SealedBox(public_key).encrypt(value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("ascii")


def update_github_secret(name: str, value: str) -> None:
    repo = _env("GITHUB_REPOSITORY")
    if not repo:
        raise RuntimeError("GITHUB_REPOSITORY is missing.")
    headers = _github_headers()
    key_response = requests.get(
        f"{GITHUB_API}/repos/{repo}/actions/secrets/public-key",
        headers=headers,
        timeout=30,
    )
    key_response.raise_for_status()
    key = key_response.json()
    body = {
        "encrypted_value": _encrypt_secret(key["key"], value),
        "key_id": key["key_id"],
    }
    response = requests.put(
        f"{GITHUB_API}/repos/{repo}/actions/secrets/{name}",
        headers=headers,
        json=body,
        timeout=30,
    )
    response.raise_for_status()


def _facebook_debug(token: str) -> dict[str, Any]:
    app_id = _env("FACEBOOK_APP_ID")
    app_secret = _env("FACEBOOK_APP_SECRET")
    if not app_id or not app_secret:
        raise RuntimeError("FACEBOOK_APP_ID / FACEBOOK_APP_SECRET are required for automatic Facebook renewal.")
    if not token:
        return {"is_valid": False, "expires_at": 0}
    app_access_token = f"{app_id}|{app_secret}"
    response = requests.get(
        f"https://graph.facebook.com/{FACEBOOK_GRAPH_VERSION}/debug_token",
        params={"input_token": token, "access_token": app_access_token},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json().get("data", {})
    return data


def _facebook_exchange_user_token(user_token: str) -> tuple[str, int]:
    app_id = _env("FACEBOOK_APP_ID")
    app_secret = _env("FACEBOOK_APP_SECRET")
    response = requests.get(
        f"https://graph.facebook.com/{FACEBOOK_GRAPH_VERSION}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": user_token,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    token = str(data.get("access_token", "")).strip()
    expires_in = int(data.get("expires_in", 0) or 0)
    if not token:
        raise RuntimeError(f"Facebook token exchange returned no access token: {data}")
    return token, expires_in


def _facebook_page_token(user_token: str) -> tuple[str, str]:
    page_id = _env("FACEBOOK_PAGE_ID", "464216073916915")
    response = requests.get(
        f"https://graph.facebook.com/{FACEBOOK_GRAPH_VERSION}/me/accounts",
        params={"fields": "id,name,access_token", "access_token": user_token},
        timeout=30,
    )
    response.raise_for_status()
    for item in response.json().get("data", []):
        if str(item.get("id", "")) == page_id:
            token = str(item.get("access_token", "")).strip()
            if token:
                return token, str(item.get("name", ""))
    raise RuntimeError(f"Facebook Page {page_id} was not returned by /me/accounts.")


def _days_remaining(data: dict[str, Any], now: datetime) -> float:
    expires_at = int(data.get("expires_at", 0) or 0)
    if not expires_at:
        return 9999.0
    return (datetime.fromtimestamp(expires_at, tz=timezone.utc) - now).total_seconds() / 86400


def renew_facebook() -> str:
    page_token = _env("FACEBOOK_PAGE_ACCESS_TOKEN")
    user_token = _env("FACEBOOK_USER_ACCESS_TOKEN")
    if not user_token:
        raise RuntimeError("FACEBOOK_USER_ACCESS_TOKEN is required.")

    now = datetime.now(timezone.utc)

    # A Page token may expire while the long-lived User token is still valid.
    # That must NOT block recovery: we can regenerate the Page token from /me/accounts.
    page_data = _facebook_debug(page_token)
    page_valid = bool(page_data.get("is_valid"))
    page_days = _days_remaining(page_data, now) if page_valid else 0.0

    user_data = _facebook_debug(user_token)
    if not user_data.get("is_valid"):
        raise RuntimeError(f"Facebook User token is invalid: {user_data}")
    user_days = _days_remaining(user_data, now)

    if page_valid and page_days > RENEWAL_DAYS and user_days > RENEWAL_DAYS:
        return f"Facebook tokens healthy: page≈{page_days:.0f}d, user≈{user_days:.0f}d."

    user_renewed = False
    if user_days <= RENEWAL_DAYS:
        user_token, _ = _facebook_exchange_user_token(user_token)
        update_github_secret("FACEBOOK_USER_ACCESS_TOKEN", user_token)
        user_data = _facebook_debug(user_token)
        if not user_data.get("is_valid"):
            raise RuntimeError("Facebook User token exchange returned an invalid token.")
        user_days = _days_remaining(user_data, now)
        user_renewed = True

    new_page_token, page_name = _facebook_page_token(user_token)
    new_page_data = _facebook_debug(new_page_token)
    if not new_page_data.get("is_valid"):
        raise RuntimeError("Facebook Page token generated by /me/accounts failed validation.")
    new_page_days = _days_remaining(new_page_data, now)
    update_github_secret("FACEBOOK_PAGE_ACCESS_TOKEN", new_page_token)

    message = (
        "✅ Facebook token maintenance completed.\n"
        f"الصفحة: {page_name or 'configured page'}\n"
        f"Page token: ≈{new_page_days:.0f} يوم\n"
        f"User token: ≈{user_days:.0f} يوم\n"
        f"User token renewed: {'نعم' if user_renewed else 'لا'}"
    )
    notify(message)
    return message


def renew_linkedin() -> str:
    refresh_token = _env("LINKEDIN_REFRESH_TOKEN")
    client_id = _env("LINKEDIN_CLIENT_ID")
    client_secret = _env("LINKEDIN_CLIENT_SECRET")
    expires_at_raw = _env("LINKEDIN_TOKEN_EXPIRES_AT")

    if not refresh_token or not client_id or not client_secret or not expires_at_raw:
        message = (
            "⚠️ LinkedIn automatic renewal is not fully configured.\n"
            "Need LINKEDIN_REFRESH_TOKEN, LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, "
            "and LINKEDIN_TOKEN_EXPIRES_AT."
        )
        notify(message)
        return message

    expires_at = datetime.fromisoformat(expires_at_raw.replace("Z", "+00:00"))
    remaining = expires_at - datetime.now(timezone.utc)
    if remaining > timedelta(days=RENEWAL_DAYS):
        return f"LinkedIn token healthy: ≈{remaining.days}d remaining."

    response = requests.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    new_access_token = str(data.get("access_token", "")).strip()
    new_refresh_token = str(data.get("refresh_token", refresh_token)).strip()
    expires_in = int(data.get("expires_in", 0) or 0)
    refresh_expires_in = int(data.get("refresh_token_expires_in", 0) or 0)
    if not new_access_token or not expires_in:
        raise RuntimeError(f"LinkedIn refresh response missing token or expiry: {data}")

    new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    update_github_secret("LINKEDIN_ACCESS_TOKEN", new_access_token)
    update_github_secret("LINKEDIN_REFRESH_TOKEN", new_refresh_token)
    update_github_secret("LINKEDIN_TOKEN_EXPIRES_AT", new_expires_at.isoformat())
    if refresh_expires_in:
        refresh_expires_at = datetime.now(timezone.utc) + timedelta(seconds=refresh_expires_in)
        update_github_secret("LINKEDIN_REFRESH_TOKEN_EXPIRES_AT", refresh_expires_at.isoformat())

    message = f"✅ LinkedIn access token renewed automatically. New expiry: {new_expires_at.isoformat()}"
    notify(message)
    return message


def main() -> None:
    results = []
    for name, fn in (("Facebook", renew_facebook), ("LinkedIn", renew_linkedin)):
        try:
            result = fn()
            results.append(f"{name}: {result}")
            print(result)
        except Exception as exc:
            message = f"🚨 {name} token manager failed: {exc}"
            print(message)
            notify(message)
            results.append(message)
    print("\n".join(results))


if __name__ == "__main__":
    main()
