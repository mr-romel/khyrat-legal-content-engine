from __future__ import annotations

from datetime import datetime, timedelta
import re

import gemini
import main as production_main
from content_planner import classify
from content_similarity import highest_similarity
from content_style_v3 import build_style_context
from decision_engine import choose_due_row
from gemini_runtime import generate_post as resilient_generate_post
from monthly_recycler import recycle_month_if_needed
from post_bank import build_previous_context, get_bank_rows
from sheets import create_service, ensure_headers, get_values, row_to_dict, update_row
from telegram_publication import send_single_publication_message, send_single_status_message
from utils import now_cairo, parse_date, parse_time, sheet_name_from_range


def _diverse_generate_post(*, api_key, model, topic, legal_sources, previous_context="", **kwargs):
    style_context = build_style_context(topic, salt=now_cairo().strftime("%Y-%m-%d-%H"))
    linkedin_context = (
        "\n\nLINKEDIN B2B AUTHORING RULES:\n"
        "This content will be adapted for LinkedIn and must not read like a short Facebook legal tip. "
        "The LinkedIn version must be materially longer, substantive, and useful to companies and decision-makers. "
        "Target business owners, CEOs, HR leaders, legal departments, operations managers, and people responsible for contracts and compliance. "
        "Build around a real business problem, the legal risk or operational consequence, what management should check before acting, "
        "and a practical decision point. Explain the business impact, not just the legal rule. "
        "Use a professional Egyptian lawyer voice: natural, experienced, direct, and readable. "
        "Prefer roughly 350-600 Arabic words for the LinkedIn version when the subject supports it. "
        "Do not pad the post with generic advice, repeated conclusions, or a sales pitch. "
        "Use a soft, context-driven CTA only when it naturally leads to discussion or a professional inquiry. "
        "The final LinkedIn post should have enough substance that a company decision-maker can learn something and see why legal review matters."
    )
    combined_context = f"{previous_context}\n\n{style_context}{linkedin_context}".strip()
    return resilient_generate_post(api_key=api_key, model=model, topic=topic, legal_sources=legal_sources, previous_context=combined_context, **kwargs)


gemini.generate_post = _diverse_generate_post
_original_prepare_editorial_assets = production_main._prepare_editorial_assets
_original_log_publication = production_main.log_publication
_latest_editorial: dict = {}


def _linkedin_word_count(text: str) -> int:
    return len(str(text or "").strip().split())


def _linkedin_needs_completion(text: str) -> bool:
    compact = " ".join(str(text or "").strip().split())
    if not compact:
        return True
    if re.search(r"(?:\.\.\.|…)$", compact):
        return True
    if re.search(r"\s(?:و|أو|لكن|لأن|لذلك|ثم|كما|بحيث|التي|الذي)$", compact):
        return True
    return False


def _clean_linkedin_ellipsis(text: str) -> str:
    return re.sub(r"\.{3}|…", ".", str(text or "")).strip()


def _fit_linkedin_char_limit(text: str, *, api_key: str, model: str, topic: str, legal_sources: str, max_chars: int = 2900) -> str:
    text = _clean_linkedin_ellipsis(text)
    if len(text) <= max_chars:
        return text
    prompt = (
        "LINKEDIN CHARACTER-LIMIT REPAIR:\n"
        f"Rewrite this complete LinkedIn post to fit within {max_chars} characters. "
        "Preserve the core legal meaning, practical business analysis, qualifications, and conclusion. "
        "Remove repetition and low-value wording instead of cutting sentences. "
        "The result MUST end with a complete thought and natural punctuation. Never use '...' or '…'. "
        "Return only the finished LinkedIn post.\n\n"
        f"Topic: {topic}\nLegal sources: {legal_sources or 'none'}\n\nPost:\n{text}"
    )
    result = _diverse_generate_post(
        api_key=api_key,
        model=model,
        topic=topic,
        legal_sources=legal_sources,
        previous_context=prompt,
    )
    candidate = _clean_linkedin_ellipsis(str(result.get("post", "") or "").strip())
    if candidate and len(candidate) <= max_chars and not _linkedin_needs_completion(candidate):
        return candidate
    raise RuntimeError(
        f"LinkedIn post is {len(text)} characters and could not be safely reduced below {max_chars} without truncation."
    )


def _strengthen_linkedin_post(post: str, *, api_key: str = "", model: str = "", topic: str = "", legal_sources: str = "") -> str:
    """Prevent LinkedIn from becoming short, truncated, or AI-styled."""
    text = _clean_linkedin_ellipsis(str(post or "").strip())
    if not text:
        return text

    minimum_words = 350
    target_words = 450
    current_words = _linkedin_word_count(text)
    if current_words >= minimum_words and not _linkedin_needs_completion(text):
        return text

    expansion_context = (
        "CURRENT LINKEDIN DRAFT THAT IS TOO SHORT:\n"
        f"{text}\n\n"
        "EXPANSION/COMPLETION REQUIREMENT:\n"
        f"Write a complete, substantive Egyptian legal-business LinkedIn post of approximately {target_words} words and never fewer than {minimum_words} words. "
        "If the draft is already substantive, preserve its useful content and repair/complete its ending instead of shortening it. "
        "Preserve the legal meaning and any legally important qualifications already present. Do not merely repeat or pad the existing paragraphs. "
        "Add useful analysis: the practical business problem, who inside a company should care, the legal/operational risk, what documents or facts management should check, "
        "the decision points before acting, a realistic example or scenario where appropriate, and a concise conclusion. "
        "The post MUST end with a complete thought and a natural sentence ending. Never end with '...', '…', a comma, a colon, or a dangling conjunction such as 'و'. "
        "Do not use ellipses anywhere in the post. Keep a professional Egyptian lawyer voice. Do not turn it into a sales pitch, generic motivational post, or list of empty tips. "
        "Do not mention that you are expanding or repairing a draft. Return only the finished LinkedIn post."
    )
    try:
        expanded = _diverse_generate_post(
            api_key=api_key,
            model=model,
            topic=topic,
            legal_sources=legal_sources,
            previous_context=expansion_context,
        )
        candidate = str(expanded.get("post", "") or "").strip()
        candidate = _clean_linkedin_ellipsis(candidate)
        if _linkedin_word_count(candidate) >= minimum_words and not _linkedin_needs_completion(candidate):
            candidate = _fit_linkedin_char_limit(candidate, api_key=api_key, model=model, topic=topic, legal_sources=legal_sources)
            print(f"LinkedIn depth gate: completed {current_words} -> {_linkedin_word_count(candidate)} words / {len(candidate)} chars.")
            return candidate
        if candidate:
            text = candidate
    except Exception as exc:
        print(f"LinkedIn depth gate expansion unavailable; using structured fallback: {exc}")

    # Safety fallback: add substantive business analysis instead of allowing a short post through.
    fallback = (
        "\n\nمن زاوية الإدارة، المهم هنا مش بس معرفة القاعدة القانونية، لكن ترجمتها إلى قرار عملي. قبل توقيع العقد أو اتخاذ الإجراء، لازم المسؤول المختص يراجع الوقائع والمستندات المرتبطة بالموضوع، ويحدد بوضوح مين عليه الالتزام، وإيه المستند اللي يثبت تنفيذه، وإيه النتيجة لو حصل إخلال أو تأخير. النقطة دي بتفرق جدًا بين إدارة المخاطر قبل المشكلة وبين محاولة علاجها بعد ما تتحول لنزاع.\n\n"
        "كمان لازم يتراجع أثر القرار على التشغيل والتكلفة والعلاقة مع الطرف الآخر. أحيانًا يكون التصرف صحيحًا من الناحية القانونية في الأصل، لكن طريقة تنفيذه أو صياغة المستندات المصاحبة له تخلق نزاعًا كان ممكن تجنبه. لذلك الأفضل إن المراجعة القانونية ما تكونش مجرد سؤال: هل ده قانوني؟ وإنما تشمل أيضًا: ما المخاطر؟ ما البدائل؟ وما الإجراء أو المستند الذي يقلل احتمال النزاع ويحافظ على موقف الشركة إذا وقع الخلاف؟\n\n"
        "وعمليًا، أي شركة تتعامل مع المسألة دي بشكل منظم هتحتاج تحدد المستندات الأساسية، المسؤول عن اتخاذ القرار، المواعيد والالتزامات، وآلية التعامل مع الإخلال أو الاعتراض. وكلما اتعملت المراجعة في مرحلة مبكرة، كانت تكلفة التصحيح أقل، وكانت الإدارة أقدر على اختيار البديل المناسب وهي فاهمة تبعاته القانونية والتجارية."
    )
    text = text + fallback
    text = _fit_linkedin_char_limit(text, api_key=api_key, model=model, topic=topic, legal_sources=legal_sources)
    print(f"LinkedIn depth gate: fallback applied; final={_linkedin_word_count(text)} words / {len(text)} chars.")
    return text


def _capture_editorial_assets(*args, **kwargs):
    global _latest_editorial
    result = _original_prepare_editorial_assets(*args, **kwargs)
    config = kwargs.get("config") or {}
    topic = str(kwargs.get("topic", "") or "").strip()
    legal_sources = str(kwargs.get("legal_sources", "") or "").strip()
    result["linkedin_post"] = _strengthen_linkedin_post(
        result.get("linkedin_post", ""),
        api_key=config.get("gemini_api_key", ""),
        model=config.get("gemini_model", ""),
        topic=topic,
        legal_sources=legal_sources,
    )
    _latest_editorial = dict(result)
    _latest_editorial["legal_sources"] = legal_sources
    _latest_editorial.setdefault("similarity_score", "")
    _latest_editorial.setdefault("rewrite_applied", "NO")
    if "زاوية جديدة:" in topic:
        _latest_editorial["angle"] = topic.split("زاوية جديدة:", 1)[1].strip()
    try:
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
                refreshed["linkedin_post"] = _strengthen_linkedin_post(
                    refreshed.get("linkedin_post", ""),
                    api_key=config.get("gemini_api_key", ""),
                    model=config.get("gemini_model", ""),
                    topic=topic,
                    legal_sources=legal_sources,
                )
                refreshed["similarity_score"] = f"{score_after:.4f}"
                refreshed["rewrite_applied"] = "YES"
                _latest_editorial = dict(refreshed)
                _latest_editorial["legal_sources"] = legal_sources
                _latest_editorial["angle"] = topic.split("زاوية جديدة:", 1)[1].strip() if "زاوية جديدة:" in topic else ""
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
    enriched.setdefault("legal_sources", str(_latest_editorial.get("legal_sources", "")))
    enriched.setdefault("angle", str(_latest_editorial.get("angle", "")))
    try:
        _original_log_publication(service, spreadsheet_id, **enriched)
    except Exception as exc:
        print(f"Analytics logging failed (non-blocking): {exc}")


def _single_telegram_notify(text: str) -> None:
    compact = str(text or "").strip()
    try:
        if compact.startswith(("🟡", "🟠", "🚨", "❌")):
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


def _linkedin_interaction_diagnostic(**kwargs) -> None:
    topic = str(kwargs.get("topic", "") or "").strip()
    post_urn = str(kwargs.get("post_urn", "") or "").strip()
    comment = kwargs.get("comment") or {}
    like = kwargs.get("like") or {}
    print("LinkedIn interaction diagnostic:")
    print(f"  topic={topic}")
    print(f"  post_urn={post_urn}")
    print(f"  comment_status={comment.get('status', '')} | http={comment.get('http_status', '')} | error={comment.get('error', '')}")
    print(f"  post_like_status={like.get('status', '')} | http={like.get('http_status', '')} | error={like.get('error', '')}")


def _smart_target_datetime(row: dict[str, str]):
    target_date = parse_date(row.get("تاريخ النشر", ""))
    target_time = parse_time(row.get("ساعة النشر", ""))
    if target_date is None or target_time is None:
        return None
    cairo_now = now_cairo()
    return datetime(target_date.year, target_date.month, target_date.day, target_time.hour, target_time.minute, 0, tzinfo=cairo_now.tzinfo)


def _smart_is_due(row: dict[str, str], current) -> bool:
    """
    A row is due whenever its scheduled Cairo time has passed and it has not
    been successfully published or explicitly cancelled.

    PROCESSING is treated as recoverable after 30 minutes so an interrupted
    run cannot strand the daily slot forever. Recent PROCESSING rows are kept
    untouched to avoid duplicate publication during a live/overlapping run.
    """
    status = str(row.get("الحالة", "READY")).strip().upper()
    if status in {"PUBLISHED", "CANCELLED"}:
        return False

    target = _smart_target_datetime(row)
    if target is None or current < target:
        return False

    if status == "PROCESSING":
        last_run_raw = str(row.get("وقت آخر تشغيل", "") or "").strip()
        try:
            last_run = datetime.fromisoformat(last_run_raw.replace("Z", "+00:00")) if last_run_raw else None
        except ValueError:
            last_run = None
        if last_run is not None:
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=current.tzinfo)
            return current - last_run >= timedelta(minutes=30)
        # If the timestamp is malformed/missing, recover only after the slot
        # itself has been overdue for at least 30 minutes.
        return current - target >= timedelta(minutes=30)

    # READY/FAILED/PARTIAL_FAILED/blank and other non-terminal states remain
    # retryable. This is deliberate: component failures must not strand a post.
    return True


def _due_diagnostics(rows: list[dict[str, str]], current) -> None:
    status_counts: dict[str, int] = {}
    overdue = 0
    for row in rows:
        status = str(row.get("الحالة", "")).strip().upper() or "<BLANK>"
        status_counts[status] = status_counts.get(status, 0) + 1
        target = _smart_target_datetime(row)
        if target is not None and target <= current and status not in {"PUBLISHED", "CANCELLED"}:
            overdue += 1
    print(f"Due diagnostics: overdue_unpublished={overdue}; statuses={status_counts}")


def _recover_stale_processing_rows(*, service, spreadsheet_id: str, sheet_name: str, rows: list[dict[str, str]], current) -> int:
    """
    Recover rows stranded in PROCESSING after a crashed/interrupted publisher run.
    A live run should not be touched; only PROCESSING rows older than 30 minutes
    and already past their scheduled time are returned to READY.
    """
    recovered = 0
    stale_after = timedelta(minutes=30)
    for row_number, row in enumerate(rows, start=2):
        if str(row.get("الحالة", "")).strip().upper() != "PROCESSING":
            continue
        target = _smart_target_datetime(row)
        if target is None or current < target:
            continue
        last_run_raw = str(row.get("وقت آخر تشغيل", "") or "").strip()
        try:
            last_run = datetime.fromisoformat(last_run_raw.replace("Z", "+00:00")) if last_run_raw else None
        except ValueError:
            last_run = None
        if last_run is None:
            # Unknown processing age is safer to leave untouched than to duplicate-publish.
            continue
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=current.tzinfo)
        if current - last_run < stale_after:
            continue
        update_row(service, spreadsheet_id, sheet_name, row_number, {
            "الحالة": "READY",
            "آخر خطأ": "Recovered stale PROCESSING row after interrupted publisher run.",
        })
        print(f"Publisher recovery: row {row_number} PROCESSING for {current - last_run}; reset to READY.")
        row["الحالة"] = "READY"
        recovered += 1
    return recovered


def _smart_main() -> None:
    print("=" * 70)
    print("KHYRAT LEGAL CONTENT ENGINE - V2 SMART SOCIAL PIPELINE")
    print("=" * 70)
    current = now_cairo()
    print(f"Current Cairo time: {current.isoformat()}")
    config = production_main.load_config()
    service = create_service(config["service_account_info"])
    sheet_name = sheet_name_from_range(config["sheet_range"])
    ensure_headers(service, config["sheet_id"], sheet_name)
    values = get_values(service, config["sheet_id"], config["sheet_range"])
    if not values:
        print("No rows found.")
        return
    try:
        prepared = recycle_month_if_needed(service=service, spreadsheet_id=config["sheet_id"], sheet_name=sheet_name, current=current.date())
        print(f"Monthly planner: reconciled current month; changes={prepared}.")
        values = get_values(service, config["sheet_id"], config["sheet_range"])
    except Exception as planner_exc:
        print(f"Monthly planner unavailable; preserving publishing flow: {planner_exc}")
    rows = [row_to_dict(row) for row in values[1:]]
    recovered = _recover_stale_processing_rows(
        service=service,
        spreadsheet_id=config["sheet_id"],
        sheet_name=sheet_name,
        rows=rows,
        current=current,
    )
    if recovered:
        values = get_values(service, config["sheet_id"], config["sheet_range"])
        rows = [row_to_dict(row) for row in values[1:]]
    candidates = [(i, r) for i, r in enumerate(rows, start=2) if _smart_is_due(r, current)]
    if not candidates:
        _due_diagnostics(rows, current)
        print("No due rows found.")
        return
    history = get_bank_rows(service, config["sheet_id"])
    selected = choose_due_row(candidates, history)
    if selected is None:
        selected = candidates[0]
    row_number, row = selected
    print(f"Decision engine: selected row {row_number} using historical topic/category/angle signals.")
    production_main.process_row(service=service, config=config, sheet_name=sheet_name, row_number=row_number, row=row, current=current)


production_main._prepare_editorial_assets = _capture_editorial_assets
production_main.log_publication = _capture_publication_analytics
production_main.notify = _single_telegram_notify
production_main.notify_linkedin_interaction = _linkedin_interaction_diagnostic
production_main._is_due = _smart_is_due
production_main._failed_retry = _smart_failed_retry

if __name__ == "__main__":
    _smart_main()
