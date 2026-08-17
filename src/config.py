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

    old_names = {
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    }

    if not model or model in old_names:
        return "gemini-3.5-flash-lite"

    return model


def load_config() -> dict:
    service_account_raw = _required("GOOGLE_SERVICE_ACCOUNT_JSON")

    try:
        service_account_info = json.loads(service_account_raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            "GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON."
        ) from exc

    if not isinstance(service_account_info, dict):
        raise ConfigError(
            "GOOGLE_SERVICE_ACCOUNT_JSON must be a JSON object."
        )

    return {
        "service_account_info": service_account_info,
        "sheet_id": _required("GOOGLE_SHEET_ID"),
        "sheet_range": os.getenv(
            "GOOGLE_SHEET_RANGE",
            "Content!A:Q",
        ).strip(),
        "gemini_api_key": _required("GEMINI_API_KEY"),
        "gemini_model": _normalize_model_name(
            os.getenv(
                "GEMINI_MODEL",
                "gemini-3.5-flash-lite",
            )
        ),
    }
