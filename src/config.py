import json
import os


class ConfigError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def load_config() -> dict:
    service_account_raw = _required("GOOGLE_SERVICE_ACCOUNT_JSON")
    try:
        service_account_info = json.loads(service_account_raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            "GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON. "
            "Paste the complete service-account JSON into the GitHub Secret."
        ) from exc

    if not isinstance(service_account_info, dict):
        raise ConfigError("GOOGLE_SERVICE_ACCOUNT_JSON must be a JSON object.")

    return {
        "service_account_info": service_account_info,
        "sheet_id": _required("GOOGLE_SHEET_ID"),
        "sheet_range": os.getenv(
            "GOOGLE_SHEET_RANGE",
            "Content!A:Q"
        ).strip(),
        "gemini_api_key": _required("GEMINI_API_KEY"),
        "gemini_model": os.getenv(
            "GEMINI_MODEL",
            "gemini-2.5-flash"
        ).strip(),
    }
