from __future__ import annotations

import json
import os

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_FACEBOOK_PAGE_ID = "464216073916915"
DEFAULT_FACEBOOK_GRAPH_VERSION = "26.0"

class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""

def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value: raise ConfigError(f"Missing required environment variable: {name}")
    return value

def _optional(name: str, default: str = "") -> str:
    value = os.getenv(name, "").strip()
    return value or default

def _normalize_model_name(value: str) -> str:
    model = (value or "").strip()
    if model.startswith("models/"): model = model[len("models/"):]
    return model or DEFAULT_GEMINI_MODEL

def _service_account_info() -> dict:
    raw = _required("GOOGLE_SERVICE_ACCOUNT_JSON")
    try: info = json.loads(raw)
    except json.JSONDecodeError as exc: raise ConfigError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON.") from exc
    if not isinstance(info, dict): raise ConfigError("GOOGLE_SERVICE_ACCOUNT_JSON must be a JSON object.")
    return info

def load_video_config() -> dict:
    return {"service_account_info": _service_account_info(),"sheet_id": _required("GOOGLE_SHEET_ID"),"sheet_range": _optional("GOOGLE_SHEET_RANGE","Content!A:AF")}

def load_facebook_engagement_config() -> dict:
    return {"service_account_info": _service_account_info(),"sheet_id": _required("GOOGLE_SHEET_ID"),"sheet_range": _optional("GOOGLE_SHEET_RANGE","Content!A:U"),"gemini_api_key": _optional("GEMINI_API_KEY",""),"gemini_model": _normalize_model_name(_optional("GEMINI_MODEL",DEFAULT_GEMINI_MODEL)),"facebook_page_id": _optional("FACEBOOK_PAGE_ID",DEFAULT_FACEBOOK_PAGE_ID),"facebook_page_access_token": _required("FACEBOOK_PAGE_ACCESS_TOKEN"),"facebook_graph_version": _optional("FACEBOOK_GRAPH_VERSION",DEFAULT_FACEBOOK_GRAPH_VERSION)}

def load_engagement_config() -> dict:
    return {"service_account_info": _service_account_info(),"sheet_id": _required("GOOGLE_SHEET_ID"),"sheet_range": _optional("GOOGLE_SHEET_RANGE","Content!A:U"),"gemini_api_key": _optional("GEMINI_API_KEY",""),"gemini_model": _normalize_model_name(_optional("GEMINI_MODEL",DEFAULT_GEMINI_MODEL)),"linkedin_access_token": _required("LINKEDIN_ACCESS_TOKEN"),"linkedin_author_urn": _optional("LINKEDIN_AUTHOR_URN","")}

def load_blogger_config() -> dict:
    enabled = _optional("BLOGGER_ENABLED","true").lower() in {"1","true","yes","on"}
    return {
        "enabled": enabled,
        "service_account_info": _service_account_info(),
        "sheet_id": _required("GOOGLE_SHEET_ID"),
        "sheet_range": _optional("GOOGLE_SHEET_RANGE","Content!A:AF"),
        "blogger_oauth_json": _optional("BLOGGER_OAUTH_JSON",""),
        "blogger_blog_id": _optional("BLOGGER_BLOG_ID",""),
        "blogger_url": _optional("BLOGGER_URL","https://askmahmoudkhyrat.blogspot.com/"),
    }

def load_config() -> dict:
    service_account_info = _service_account_info()
    dry_run = os.getenv("KHYRAT_DRY_RUN","false").strip().lower() in {"1","true","yes","on"}
    facebook_page_access_token = _optional("FACEBOOK_PAGE_ACCESS_TOKEN") if dry_run else _required("FACEBOOK_PAGE_ACCESS_TOKEN")
    linkedin_access_token = _optional("LINKEDIN_ACCESS_TOKEN") if dry_run else _required("LINKEDIN_ACCESS_TOKEN")
    cloudflare_account_id = _optional("CLOUDFLARE_ACCOUNT_ID") if dry_run else _required("CLOUDFLARE_ACCOUNT_ID")
    cloudflare_api_token = _optional("CLOUDFLARE_API_TOKEN") if dry_run else _required("CLOUDFLARE_API_TOKEN")
    return {
        "service_account_info": service_account_info,
        "sheet_id": _required("GOOGLE_SHEET_ID"),
        "sheet_range": _optional("GOOGLE_SHEET_RANGE","Content!A:U"),
        "gemini_api_key": _required("GEMINI_API_KEY"),
        "gemini_model": _normalize_model_name(_optional("GEMINI_MODEL",DEFAULT_GEMINI_MODEL)),
        "cloudflare_account_id": cloudflare_account_id,
        "cloudflare_api_token": cloudflare_api_token,
        "facebook_page_id": _optional("FACEBOOK_PAGE_ID",DEFAULT_FACEBOOK_PAGE_ID),
        "facebook_page_access_token": facebook_page_access_token,
        "facebook_graph_version": _optional("FACEBOOK_GRAPH_VERSION",DEFAULT_FACEBOOK_GRAPH_VERSION),
        "linkedin_access_token": linkedin_access_token,
        "linkedin_author_urn": _optional("LINKEDIN_AUTHOR_URN",""),
    }
