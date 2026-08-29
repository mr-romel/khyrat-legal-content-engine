from __future__ import annotations

from datetime import datetime, timedelta

import gemini
import main as production_main
from content_similarity import highest_similarity
from content_style_v3 import build_style_context
from gemini_runtime import generate_post as resilient_generate_post
from post_bank import build_previous_context, get_bank_rows
from sheets import create_service
from telegram_publication import send_single_publication_message, send_single_status_message
from utils import now_cairo, parse_date, parse_time


def _diverse_generate_post(*, api_key, model, topic, legal_sources, previous_context="", **kwargs):
    style_context = build_style_context(topic, salt=now_cairo().strftime("%Y-%m-%d-%H"))
    combined_context = f"{previous_context}\n\n{style_context}".strip()
    return resilient_generate_post(
        api_key=api_key,
        model=model,
        topic=topic,
        legal_sources=legal_sources,
        previous_context=combined_context,
        **kwargs,
    )


gemini.generate_post = _diverse_generate_post
_original_prepare_editorial_assets = production_main._prepare_editorial_assets
_original_log_publication = production_main.log_publication
_latest_editorial: dict = {}


def _capture_editorial_assets(*args, **kwargs):
    global _latest_editorial
    result = _original_prepare_editorial_assets(*args, **kwargs)
    topic = str(kwargs.get("topic", "") or "").strip()
    legal_sources = str(kwargs.get("legal_sources", "") or "").strip()
    _latest_editorial = dict(result)
    _latest_editorial["legal_sources"] = legal_sources
    _latest_editorial.setdefault("similarity_score", "")
    _latest_editorial.setdefault("rewrite_applied", "NO")

    try:
        config = kwargs.get("config") or {}
        service = create_service(config["service_account_info"])
        bank_rows = get_bank_rows(service, config["sheet_id"])
        previous_posts = [str(row.get("المحتوى", "") or "").strip() for row in bank_rows if str(row.get("المحتوى", "") or "").strip()]
        candidate = str(result.get("facebook_post", "") or "").strip()
        if not candidate or not previous_posts:
            return result

        threshold = 0.72
        score, match = highest_similarity(candidate, previous_posts, threshold)
        _latest_editorial["similarity_score"] = f"{score:.4f}"
        if score < threshold:
            print(f"Similarity gate: PASS ({score:.2f} < {threshold:.2f}).")
            return result

        print(f"Similarity gate: REWRITE requested ({score:.2f} >= {threshold:.2f}).")
        context = build_previous_context(bank_rows, limit=8)
        context += (
            "\n\nPRE-PUBLICATION SIMILARITY WARNING. Rewrite the post from scratch while preserving the legal meaning. "
            "Use a materially different hook, sentence rhythm, ordering of ideas, examples, and CTA. "
            "Do not reuse distinctive phrases from previous posts. "
            f"The closest previous post begins: {match[:350]}"
        )

        try:
            rewritten = _diverse_generate_post(api_key=config["gemini_api_key"], model=config["gemini_model"], topic=topic, legal_sources=legal_sources, previous_context=context)
            rewritten_post = str(rewritten.get("post", "") or "").strip()
            if not rewritten_post:
                print("Similarity gate: rewrite returned empty content; publishing original.")
                return result

            score_after, _ = highest_similarity(rewritten_post, previous_posts, threshold)
            if score_after < threshold:
                print(f"Similarity gate: REWRITE PASS ({score_after:.2f} < {threshold:.2f}).")
                refreshed = _original_prepare_editorial_assets(config=config, topic=topic, facebook_post=rewritten_post, legal_sources=legal_sources)
                refreshed["similarity_score"] = f"{score_after:.4f}"
                refreshed["rewrite_applied"] = "YES"
                _latest_editorial = dict(refreshed)
                _latest_editorial["legal_sources"] = legal_sources
                return refreshed

            print(f"Similarity gate: rewrite still similar ({score_after:.2f} >= {threshold:.2f}); publishing original as required by continuous-publishing policy.")
            return result
        except Exception as rewrite_exc:
            print(f"Similarity gate rewrite unavailable; publishing original as required by continuous-publishing policy: {rewrite_exc}")
            return result
    except Exception as exc:
        print(f"Similarity gate unavailable; preserving publication flow: {exc}")
        return result


def _capture_publication_analytics(service, spreadsheet_id: str, **data: str) -> None:
    enriched = dict(data)
    enriched.setdefault("similarity_score", str(_latest_editorial.get("similarity_score", "")))
    enriched.setdefault("rewrite_applied", str(_latest_editorial.get("rewrite_applied", "NO")))
    try:
        _original_log_publication(service, spreadsheet_id, **enriched)
    except Exception as exc:
        # Analytics must never block successful publication.
        print(f"Analytics logging failed (non-blocking): {exc}")


def _single_telegram_notify(text: str) -> None:
    compact = str(text or "").strip()
    try:
        if compact.startswith(("🚨", "❌", "🟡")):
            return
        if compact.startswith("🟠"):
            send_single_status_message(text=compact)
            return
        if compact.startswith("✅"):
            marker = "تم نشر:"
            topic = compact.split(marker, 1)[1].split("\n", 1)[0].strip() if marker in compact else "غير متاح"
            post = str(_latest_editorial.get("facebook_post", "")).strip()
            if post:
                send_single_publication_message(topic=topic, post=post, legal_sources=str(_latest_editorial.get("legal_sources", "")), status_text="Facebook + LinkedIn: تم النشر بنجاح")
            else:
                send_single_status_message(text=compact)
            return
        send_single_status_message(text=compact)
    except Exception as exc:
        print(f"Telegram notification failed (non-blocking): {exc}")


def _suppress_linkedin_diagnostic(**kwargs) -> None:
    return None


def _smart_target_datetime(row: dict[str, str]):
    target_date = parse_date(row.get("تاريخ النشر", ""))
    target_time = parse_time(row.get("ساعة النشر", ""))
    if target_date is None or target_time is None:
        return None
    cairo_now = now_cairo()
    return datetime(target_date.year, target_date.month, target_date.day, target_time.hour, target_time.minute, 0, tzinfo=cairo_now.tzinfo)


def _smart_is_due(row: dict[str, str], current) -> bool:
    status = str(row.get("الحالة", "READY")).strip().upper()
    if status not in {"READY", "READY_FOR_SOCIAL_PUBLISH", "FAILED", "PARTIAL_FAILED"}:
        return False
    target = _smart_target_datetime(row)
    if target is None or current < target:
        return False
    return current - target <= timedelta(hours=16)


def _smart_failed_retry(row: dict[str, str], current) -> bool:
    return str(row.get("الحالة", "")).strip().upper() in {"FAILED", "PARTIAL_FAILED"} and _smart_is_due(row, current)


production_main._prepare_editorial_assets = _capture_editorial_assets
production_main.log_publication = _capture_publication_analytics
production_main.notify = _single_telegram_notify
production_main.notify_linkedin_interaction = _suppress_linkedin_diagnostic
production_main._is_due = _smart_is_due
production_main._failed_retry = _smart_failed_retry
production_main.main()
