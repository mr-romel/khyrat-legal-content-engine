from __future__ import annotations

import gemini
import main as production_main
from gemini_runtime import generate_post as resilient_generate_post
from telegram_publication import send_single_publication_message, send_single_status_message


# main.py imports generate_post from the gemini module. Patch that symbol before
# running the production pipeline so the existing retries and fallback remain active.
gemini.generate_post = resilient_generate_post


# Capture the final post after the comprehensive legal/editorial gate. This is
# the exact version sent to the social publishers and to the Telegram video package.
_original_prepare_editorial_assets = production_main._prepare_editorial_assets
_latest_editorial: dict = {}


def _capture_editorial_assets(*args, **kwargs):
    global _latest_editorial
    result = _original_prepare_editorial_assets(*args, **kwargs)
    _latest_editorial = dict(result)
    return result


def _single_telegram_notify(text: str) -> None:
    """Send one final Telegram package instead of multiple publication diagnostics."""
    compact = str(text or "").strip()

    # Intermediate platform errors are intentionally suppressed. The final
    # PARTIAL_FAILED / FAILED notification is the single status message.
    if compact.startswith("🚨") or compact.startswith("❌"):
        return

    if compact.startswith("🟠"):
        send_single_status_message(text=compact)
        return

    if compact.startswith("✅"):
        marker = "تم نشر:"
        topic = compact.split(marker, 1)[1].split("\n", 1)[0].strip() if marker in compact else "غير متاح"
        post = str(_latest_editorial.get("facebook_post", "")).strip()
        if post:
            send_single_publication_message(
                topic=topic,
                post=post,
                status_text="Facebook + LinkedIn: تم النشر بنجاح",
            )
        else:
            send_single_status_message(text=compact)
        return

    send_single_status_message(text=compact)


def _suppress_linkedin_diagnostic(**kwargs) -> None:
    """Keep LinkedIn interaction diagnostics in GitHub logs, not extra Telegram messages."""
    return None


production_main._prepare_editorial_assets = _capture_editorial_assets
production_main.notify = _single_telegram_notify
production_main.notify_linkedin_interaction = _suppress_linkedin_diagnostic

production_main.main()
