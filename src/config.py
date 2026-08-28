from __future__ import annotations

import json
import os


DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
DEFAULT_FACEBOOK_PAGE_ID = "464216073916915"
DEFAULT_FACEBOOK_GRAPH_VERSION = "26.0"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise ConfigError(
            f"Missing required environment variable: {name}"
        )

    return value


def _optional(name: str, default: str = "") -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _normalize_model_name(value: str) -> str:
    model = (value or "").strip()
    if model.startswith("models/"):
        model = model[len("models/"):]
    return model or DEFAULT_GEMINI_MODEL


def _service_account_info() -> dict:
    service_account_raw = _required("GOOGLE_SERVICE_ACCOUNT_JSON")

    try:
        service_account_info = json.loads(service_account_raw)
    except json.JSONDecodeError as exc:
        raise ConfigError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON.") from exc

    if not isinstance(service_account_info, dict):
        raise ConfigError("GOOGLE_SERVICE_ACCOUNT_JSON must be a JSON object.")

    return service_account_info


def load_video_config() -> dict:
    """Load only configuration required by the independent Video Layer.

    The Video Layer reads published content from Google Sheets and sends
    Gemini Notebook preparation messages through Telegram. It does not
    publish to Facebook/LinkedIn and therefore must not require their tokens.
    """
    return {
        "service_account_info": _service_account_info(),
        "sheet_id": _required("GOOGLE_SHEET_ID"),
        "sheet_range": _optional("GOOGLE_SHEET_RANGE", "Content!A:U"),
    }


def load_config() -> dict:
    service_account_info = _service_account_info()

    dry_run = os.getenv("KHYRAT_DRY_RUN", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }

    facebook_page_access_token = (
        _optional("FACEBOOK_PAGE_ACCESS_TOKEN")
        if dry_run
        else _required("FACEBOOK_PAGE_ACCESS_TOKEN")
    )
    linkedin_access_token = (
        _optional("LINKEDIN_ACCESS_TOKEN")
        if dry_run
        else _required("LINKEDIN_ACCESS_TOKEN")
    )

    # Safe comment dry-run does not create an image or publish anything, so
    # Cloudflare credentials are intentionally optional there. Production
    # publishing still requires both values.
    cloudflare_account_id = (
        _optional("CLOUDFLARE_ACCOUNT_ID")
        if dry_run
        else _required("CLOUDFLARE_ACCOUNT_ID")
    )
    cloudflare_api_token = (
        _optional("CLOUDFLARE_API_TOKEN")
        if dry_run
        else _required("CLOUDFLARE_API_TOKEN")
    )

    return {
        "service_account_info": service_account_info,
        "sheet_id": _required("GOOGLE_SHEET_ID"),
        "sheet_range": _optional("GOOGLE_SHEET_RANGE", "Content!A:U"),
        "gemini_api_key": _required("GEMINI_API_KEY"),
        "gemini_model": _normalize_model_name(_optional("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)),
        "cloudflare_account_id": cloudflare_account_id,
        "cloudflare_api_token": cloudflare_api_token,
        "facebook_page_id": _optional("FACEBOOK_PAGE_ID", DEFAULT_FACEBOOK_PAGE_ID),
        "facebook_page_access_token": facebook_page_access_token,
        "facebook_graph_version": _optional("FACEBOOK_GRAPH_VERSION", DEFAULT_FACEBOOK_GRAPH_VERSION),
        "linkedin_access_token": linkedin_access_token,
        "linkedin_author_urn": _optional("LINKEDIN_AUTHOR_URN", ""),
    }
