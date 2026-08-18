import json
import os


class ConfigError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _normalize_model_name(value: str) -> str:
    model = (value or "").strip()
    if model.startswith("models/"):
        model = model[len("models/"):]
    if not model:
        return "gemini-3.5-flash"
    return model


def load_config() -> dict:
    raw = _required("GOOGLE_SERVICE_ACCOUNT_JSON")
    try:
        service_account_info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON.") from exc
    if not isinstance(service_account_info, dict):
        raise ConfigError("GOOGLE_SERVICE_ACCOUNT_JSON must be a JSON object.")

    return {
        "service_account_info": service_account_info,
        "sheet_id": _required("GOOGLE_SHEET_ID"),
        "sheet_range": os.getenv("GOOGLE_SHEET_RANGE", "Content!A:Q").strip(),
        "gemini_api_key": _required("GEMINI_API_KEY"),
        "gemini_model": _normalize_model_name(os.getenv("GEMINI_MODEL", "gemini-3.5-flash")),
        "facebook_page_id": os.getenv("FACEBOOK_PAGE_ID", "464216073916915").strip(),
        "facebook_page_access_token": _required("FACEBOOK_PAGE_ACCESS_TOKEN"),
        "facebook_graph_version": os.getenv("FACEBOOK_GRAPH_VERSION", "26.0").strip().lstrip("v"),
        "facebook_auto_like": os.getenv("FACEBOOK_AUTO_LIKE", "true").strip().lower() == "true",
        "facebook_first_comment": os.getenv(
            "FACEBOOK_FIRST_COMMENT",
            "لو الموضوع ده بيمس موقف حصل معاك، اكتب سؤالك في التعليقات، وهنوضح لك القاعدة القانونية ببساطة. ⚖️",
        ).strip(),
    }
