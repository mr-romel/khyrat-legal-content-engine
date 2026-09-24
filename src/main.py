from __future__ import annotations

import json
import os
import traceback
from difflib import SequenceMatcher
from pathlib import Path

from analytics import log_publication
from comment_engine import generate_comments
from config import load_config
from content_planner import classify
from content_diversity import build_diversity_context
from editorial_review import review_and_prepare
from facebook_publisher import FacebookPublishError, add_comment as facebook_add_comment, like_post as facebook_like_post, publish_photo
from gemini import generate_post
from image_generator import ImageGenerationError, create_legal_image
from image_qa import ImageQAError, QA_MAX_RETRIES, qa_image, summarize_qa
from social_content import append_hashtags, split_hashtags
from linkedin_publisher import LinkedInPublishError, publish_to_linkedin, resolve_member_urn
from post_bank import add_published_post, build_previous_context, get_bank_rows
from sheets import create_service, ensure_headers, get_values, row_to_dict, update_row
from telegram_bot import notify, notify_linkedin_interaction, send_review_request
from utils import now_cairo, parse_date, parse_time, sheet_name_from_range

GENERATED_DIR = Path("generated")
FACEBOOK_COMMENT_LIMIT = 7
LINKEDIN_COMMENT_LIMIT = 7
DRY_RUN = os.getenv("KHYRAT_DRY_RUN", "false").strip().lower() in {"1", "true", "yes", "on"}


def github_raw_url(relative_path: str) -> str:
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    branch = os.getenv("GITHUB_REF_NAME", "main").strip() or "main"
    if not repository:
        return ""
    return f"https://raw.githubusercontent.com/{repository}/{relative_path.replace(chr(92), '/').lstrip('/')}"


def _normalized_topic(value: str) -> str:
    chars = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in (value or ""))
    return " ".join(chars.split())


def _duplicate_score(topic: str, bank_rows: list[dict[str, str]]) -> tuple[float, str]:
    normalized = _normalized_topic(topic)
    best_score, best_topic = 0.0, ""
    for row in bank_rows:
        candidate = _normalized_topic(row.get("الموضوع", ""))
        if candidate:
            score = SequenceMatcher(None, normalized, candidate).ratio()
            if score > best_score:
                best_score, best_topic = score, row.get("الموضوع", "")
    return best_score, best_topic


def _is_due(row: dict[str, str], current) -> bool:
    status = str(row.get("الحالة", "READY")).strip().upper()
    if status not in {"READY", "FAILED", "PARTIAL_FAILED"}:
        return False
    target_date = parse_date(row.get("تاريخ النشر", ""))
    target_time = parse_time(row.get("ساعة النشر", ""))
    if target_date is None or target_time is None:
        return False
    target = current.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)
    return 0 <= (current - target).total_seconds() < 3600 and current.date() >= target_date


def _failed_retry(row: dict[str, str], current) -> bool:
    return str(row.get("الحالة", "")).strip().upper() in {"FAILED", "PARTIAL_FAILED"} and bool(row.get("الموضوع", "").strip())


def _is_permission_blocked(value) -> bool:
    if isinstance(value, dict):
        if int(value.get("http_status", 0) or 0) == 403:
            return True
        value = value.get("error", "")
    else:
        if int(getattr(value, "http_status", 0) or 0) == 403:
            return True
        value = getattr(value, "error", value)
    text = str(value or "").upper()
    return "HTTP 403" in text or "NOT ENOUGH PERMISSIONS" in text or "PARTNERAPISOCIALACTIONS.CREATE" in text or "PARTNERAPIREACTIONS.CREATE" in text


def _interaction_status(result, success_status: str, disabled_status: str) -> str:
    if isinstance(result, dict):
        status = result.get("status", "")
    else:
        status = getattr(result, "status", "")
    if status == success_status:
        return success_status
    return disabled_status if _is_permission_blocked(result) else "FAILED"


def _notify_review(row_number: int, row: dict[str, str], review_level: str, review_text: str, config) -> None:
    send_review_request(row_number=row_number, topic=row.get("الموضوع", ""), post=row.get("المحتوى", ""), reason=review_text, sheet_id=config["sheet_id"], status=review_level)


def _ensure_facebook_cta(post: str) -> str:
    text = (post or "").strip()
    if not text:
        return text
    additions = []
    lowered = text.casefold()
    if not any(word in lowered for word in ("شارك", "ابعت", "ابعته", "شير")):
        additions.append("لو شايف إن المعلومة دي ممكن تفيد حد تعرفه، ابعتله المنشور بدل ما المعلومة توصله متأخر.")
    if not any(word in lowered for word in ("سؤالك", "استفسارك", "موقف مشابه", "التعليقات")):
        additions.append("ولو عندك موقف مشابه، اكتب سؤالك في التعليقات ونوضح لك الإطار القانوني العام للمسألة.")
    return text + ("\n\n" + "\n".join(additions) if additions else "")


def _prepare_editorial_assets(*, config, topic: str, facebook_post: str, legal_sources: str) -> dict:
    comments = generate_comments(api_key=config["gemini_api_key"], model=config["gemini_model"], topic=topic, post=facebook_post, legal_sources=legal_sources)
    reviewed = review_and_prepare(api_key=config["gemini_api_key"], model=config["gemini_model"], topic=topic, facebook_post=facebook_post, facebook_comments=comments["facebook_comments"][:5], linkedin_comments=comments["linkedin_comments"], legal_sources=legal_sources)
    reviewed["facebook_comments"] = reviewed["facebook_comments"] + comments["facebook_comments"][5:FACEBOOK_COMMENT_LIMIT]
    reviewed["facebook_post"] = _ensure_facebook_cta(reviewed["facebook_post"])

    # Shared social-content contract: both platforms always receive the same
    # topic-derived hashtag set while keeping their platform-specific body.
    reviewed["facebook_post"] = append_hashtags(reviewed["facebook_post"], topic)
    linkedin_body, _ = split_hashtags(reviewed.get("linkedin_post", ""))
    reviewed["linkedin_post"] = append_hashtags(linkedin_body, topic)

    # Preserve the hashtag suffix when LinkedIn approaches its safe 2,900-char
    # publication ceiling; never hard-truncate the body mid-sentence.
    linkedin_post = reviewed["linkedin_post"]
    if len(linkedin_post) > 2900:
        body, tag_suffix = split_hashtags(linkedin_post)
        budget = 2900 - len(tag_suffix) - 2
        if budget < 2200:
            budget = 2200
        if len(body) > budget:
            body = body[:budget].rsplit(" ", 1)[0].rstrip()
        reviewed["linkedin_post"] = f"{body}\n\n{tag_suffix}".strip()
    return reviewed


def _generate_if_needed(*, service, config, sheet_name, row_number, row, current, topic, bank_rows):
    existing_post = str(row.get("المحتوى", "") or "").strip()
    existing_image_url = str(row.get("رابط الصورة", "") or "").strip()
    raw_id = row.get("ID", "") or f"row-{row_number}"
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in raw_id)
    image_path = GENERATED_DIR / f"{safe_id}.jpg"
    recovery = str(row.get("الحالة", "")).strip().upper() in {"FAILED", "PARTIAL_FAILED", "READY_FOR_SOCIAL_PUBLISH"}

    if recovery and existing_post and image_path.is_file():
        try:
            qa = qa_image(
                api_key=config["gemini_api_key"],
                image_path=str(image_path),
                topic=topic,
                image_brief=str(row.get("وصف الصورة", "") or "").strip() or "Existing generated visual for this legal topic.",
                model=os.getenv("KHYRAT_IMAGE_QA_MODEL", config["gemini_model"]),
                image_mode=str(row.get("Image Mode", "") or "CONTEXT_ONLY").strip().upper() or "CONTEXT_ONLY",
            )
        except ImageQAError as exc:
            reason = f"Image QA unavailable: {exc}"
            update_row(service, config["sheet_id"], sheet_name, row_number, {
                "Image QA Status": "ERROR", "Image QA Issues": reason,
                "آخر خطأ": reason, "وقت آخر تشغيل": current.isoformat()
            })
            print(f"Image QA hard failure during recovery — publication blocked | الموضوع: {topic} | السبب: {exc}")
            return existing_post, existing_image_url, image_path, "BLOCK", reason

        qa_reason = summarize_qa(qa)
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "Image QA Status": qa.get("decision", "BLOCK"), "Image QA Score": qa.get("overall_score", 0),
            "Image QA Issues": qa_reason, "Image QA Attempt": "RECOVERY",
            "وقت آخر تشغيل": current.isoformat()
        })
        if qa.get("decision") != "PASS":
            update_row(service, config["sheet_id"], sheet_name, row_number, {
                "Image QA Issues": qa_reason or "Existing image did not pass visual QA.",
                "آخر خطأ": ""
            })
            print(f"Existing image QA blocked publication | الموضوع: {topic} | النتيجة: {qa_reason or 'visual defects detected'}")
            return existing_post, existing_image_url, image_path, "BLOCK", qa_reason
        return existing_post, existing_image_url, image_path, "CLEAR", ""

    previous_context = build_previous_context(bank_rows) + "\n" + build_diversity_context(topic, build_previous_context(bank_rows))
    duplicate_score, duplicate_topic = _duplicate_score(topic, bank_rows)
    if duplicate_score >= 0.88:
        previous_context += f"\nIMPORTANT: avoid repeating this recent topic verbatim: {duplicate_topic}"

    result = generate_post(
        api_key=config["gemini_api_key"], model=config["gemini_model"], topic=topic,
        legal_sources=row.get("المصادر القانونية", ""), previous_context=previous_context
    )
    post = str(result.get("post", "") or "").strip()
    image_brief = str(result.get("image_brief", "") or "").strip()
    image_mode = str(result.get("image_mode", "CONTEXT_ONLY") or "CONTEXT_ONLY").strip().upper()
    if image_mode not in {"REFERENCE_SUBJECT", "CONTEXT_ONLY"}:
        image_mode = "CONTEXT_ONLY"
    review_level = str(result.get("review_level", "REVIEW") or "REVIEW").upper()
    review_text = " | ".join(str(x).strip() for x in result.get("review_flags", []) if str(x).strip())
    if not post or not image_brief:
        raise RuntimeError("Gemini returned incomplete content.")

    if review_level == "BLOCK":
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "الحالة": "NEEDS_REVIEW", "المحتوى": post, "وصف الصورة": image_brief,
            "آخر خطأ": review_text or "Legal review required.", "وقت آخر تشغيل": current.isoformat()
        })
        _notify_review(row_number, {**row, "المحتوى": post}, "BLOCK", review_text, config)
        return None, None, None, "BLOCK", review_text
    if review_level == "REVIEW":
        notify(f"🟡 Review advisory — سيتم النشر تلقائيًا.\nالموضوع: {topic}\nالملاحظة: {review_text or 'مراجعة مستحسنة'}")

    qa_last: dict = {}
    working_brief = image_brief
    for attempt in range(1, QA_MAX_RETRIES + 1):
        create_legal_image(
            topic=topic, image_brief=working_brief, output_path=str(image_path),
            cloudflare_account_id=config["cloudflare_account_id"],
            cloudflare_api_token=config["cloudflare_api_token"],
            gemini_api_key=config["gemini_api_key"],
            image_mode=image_mode,
        )

        try:
            qa_last = qa_image(
                api_key=config["gemini_api_key"], image_path=str(image_path), topic=topic,
                image_brief=working_brief,
                model=os.getenv("KHYRAT_IMAGE_QA_MODEL", config["gemini_model"]),
                image_mode=image_mode,
            )
        except ImageQAError as exc:
            reason = f"Image QA unavailable: {exc}"
            update_row(service, config["sheet_id"], sheet_name, row_number, {
                "الحالة": "NEEDS_IMAGE_REVIEW", "Image QA Status": "ERROR", "Image Mode": image_mode,
                "Image QA Attempt": attempt, "Image QA Issues": reason,
                "المحتوى": post, "وصف الصورة": image_brief,
                "آخر خطأ": reason, "وقت آخر تشغيل": current.isoformat()
            })
            print(f"Image QA hard failure — publication blocked | الموضوع: {topic} | السبب: {exc}")
            return post, github_raw_url(str(image_path)), image_path, "BLOCK", reason

        qa_status = str(qa_last.get("decision", "BLOCK")).upper()
        qa_score = qa_last.get("overall_score", 0)
        qa_reason = summarize_qa(qa_last)
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "Image QA Status": qa_status, "Image QA Score": qa_score,
            "Image QA Issues": qa_reason, "Image QA Attempt": attempt,
            "المحتوى": post, "وصف الصورة": image_brief, "Image Mode": image_mode, "وقت آخر تشغيل": current.isoformat()
        })

        if qa_status == "PASS":
            image_url = github_raw_url(str(image_path))
            update_row(service, config["sheet_id"], sheet_name, row_number, {
                "الحالة": "READY_FOR_SOCIAL_PUBLISH", "رابط الصورة": image_url, "Image Mode": image_mode,
                "Image QA Status": "PASS", "Image QA Score": qa_score,
                "Image QA Issues": qa_reason, "Image QA Attempt": attempt,
                "آخر خطأ": "", "وقت آخر تشغيل": current.isoformat()
            })
            print(
                f"Image preview/QA PASS: attempt={attempt} score={qa_score} "
                f"composition={qa_last.get('composition_score')} relevance={qa_last.get('relevance_score')} "
                f"text_detected={qa_last.get('text_detected')}"
            )
            return post, image_url, image_path, review_level, review_text

        if qa_status == "BLOCK":
            break

        correction = str(qa_last.get("regeneration_prompt", "")).strip()
        working_brief = f"{image_brief}\n\nFINAL IMAGE QA CORRECTIONS — MUST FIX:\n{correction or 'Fix every detected visual QA defect while preserving the legal story and reference identity.'}"
        print(f"Image preview/QA REGENERATE: attempt={attempt} | {qa_reason or correction}")

    final_reason = summarize_qa(qa_last) or "Final generated image did not pass visual QA."
    update_row(service, config["sheet_id"], sheet_name, row_number, {
        "الحالة": "NEEDS_IMAGE_REVIEW", "Image QA Status": "BLOCK",
        "Image QA Score": qa_last.get("overall_score", 0), "Image QA Issues": final_reason,
        "Image QA Attempt": QA_MAX_RETRIES, "المحتوى": post, "وصف الصورة": image_brief,
        "آخر خطأ": final_reason, "وقت آخر تشغيل": current.isoformat()
    })
    print(f"Image preview/QA BLOCK — publication blocked | الموضوع: {topic} | السبب: {final_reason}")
    image_url = github_raw_url(str(image_path))
    return post, image_url, image_path, "BLOCK", final_reason

def process_row(*, service, config, sheet_name: str, row_number: int, row: dict[str, str], current) -> None:
    topic = row.get("الموضوع", "").strip()
    if not topic:
        raise RuntimeError(f"Row {row_number} has no topic.")
    print(f"Processing row {row_number}: {topic}")
    original_status = str(row.get("الحالة", "")).strip().upper()
    if DRY_RUN:
        bank_rows = get_bank_rows(service, config["sheet_id"])
        post, _, image_path, level, reason = _generate_if_needed(service=service, config=config, sheet_name=sheet_name, row_number=row_number, row=row, current=current, topic=topic, bank_rows=bank_rows)
        if level == "BLOCK":
            return
        editorial = _prepare_editorial_assets(config=config, topic=topic, facebook_post=post, legal_sources=row.get("المصادر القانونية", ""))
        print(f"DRY RUN: Facebook comments={len(editorial['facebook_comments'])}/20 | LinkedIn comments={len(editorial['linkedin_comments'])}/5 | image={image_path}")
        return

    update_row(service, config["sheet_id"], sheet_name, row_number, {"الحالة": "PROCESSING" if original_status not in {"FAILED", "PARTIAL_FAILED", "READY_FOR_SOCIAL_PUBLISH"} else original_status, "آخر خطأ": "", "وقت آخر تشغيل": current.isoformat()})
    bank_rows = get_bank_rows(service, config["sheet_id"])
    pillar, objective = classify(topic, row.get("المحتوى", ""))
    try:
        post, image_url, image_path, review_level, review_text = _generate_if_needed(service=service, config=config, sheet_name=sheet_name, row_number=row_number, row=row, current=current, topic=topic, bank_rows=bank_rows)
        if review_level == "BLOCK":
            return
        if not post or not image_path:
            raise RuntimeError("Content/image generation did not produce publishable assets.")
        editorial = _prepare_editorial_assets(config=config, topic=topic, facebook_post=post, legal_sources=row.get("المصادر القانونية", ""))
        facebook_post, linkedin_post = editorial["facebook_post"], editorial["linkedin_post"]
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "Facebook Comment Queue": json.dumps(editorial["facebook_comments"], ensure_ascii=False),
            "LinkedIn Comment Queue": json.dumps(editorial["linkedin_comments"], ensure_ascii=False),
            "Facebook Comments Published": row.get("Facebook Comments Published", "") or "0",
            "LinkedIn Comments Published": row.get("LinkedIn Comments Published", "") or "0",
        })


        facebook_post_id = str(row.get("Facebook Post ID", "") or "").strip() if original_status in {"FAILED", "PARTIAL_FAILED", "READY_FOR_SOCIAL_PUBLISH"} else ""
        linkedin_post_id = str(row.get("LinkedIn Post ID", "") or "").strip() if original_status in {"FAILED", "PARTIAL_FAILED", "READY_FOR_SOCIAL_PUBLISH"} else ""
        facebook_comments = 0
        linkedin_comments = 0
        linkedin_interaction_errors: list[str] = []

        if facebook_post_id and str(row.get("Facebook Status", "")).strip().upper() == "PUBLISHED":
            print(f"Idempotency: Facebook already published as {facebook_post_id}; skipping duplicate publish.")
        else:
            try:
                facebook = publish_photo(page_id=config["facebook_page_id"], page_access_token=config["facebook_page_access_token"], graph_version=config["facebook_graph_version"], image_path=image_path, caption=facebook_post)
                facebook_post_id = facebook["post_id"]
                update_row(service, config["sheet_id"], sheet_name, row_number, {"Facebook Status": "PUBLISHED", "Facebook Post ID": facebook_post_id, "Facebook Comment Status": "QUEUED", "Facebook Reaction Status": "QUEUED"})
                try:
                    print("Facebook engagement queued for dedicated worker.")
                except Exception as exc:
                    print(f"Facebook comment engine failed: {exc}")
            except FacebookPublishError as exc:
                error = f"Facebook: {exc}"
                update_row(service, config["sheet_id"], sheet_name, row_number, {"Facebook Status": "FAILED", "آخر خطأ": error})
                notify(f"🚨 Facebook publishing failed\nالموضوع: {topic}\nالسبب: {exc}")

        linkedin_status = str(row.get("LinkedIn Status", "")).strip().upper()
        if linkedin_post_id and linkedin_status == "PUBLISHED":
            print(f"Idempotency: LinkedIn post already published as {linkedin_post_id}; skipping duplicate LinkedIn post.")
        else:
            try:
                token = config["linkedin_access_token"]
                author = (config.get("linkedin_author_urn", "") or "").strip() or resolve_member_urn(token)
                linkedin = publish_to_linkedin(token=token, author_urn=author, image_path=image_path, commentary=linkedin_post, first_comment="")
                linkedin_post_id = linkedin["post_urn"]
                comment_result, like_result = linkedin["comment"], linkedin["like"]
                linkedin_interaction_errors.extend([x for x in (comment_result.get("error"), like_result.get("error")) if x])
                update_row(
                    service,
                    config["sheet_id"],
                    sheet_name,
                    row_number,
                    {
                        "LinkedIn Status": "PUBLISHED",
                        "LinkedIn Post ID": linkedin_post_id,
                        "LinkedIn Comment Status": "QUEUED",
                        "LinkedIn Reaction Status": "QUEUED",
                        "آخر خطأ": " | ".join(linkedin_interaction_errors)[:1500],
                    },
                )
            except LinkedInPublishError as exc:
                error = f"LinkedIn: {exc}"
                update_row(service, config["sheet_id"], sheet_name, row_number, {"LinkedIn Status": "FAILED", "آخر خطأ": error})
                notify(f"🚨 LinkedIn publishing failed\nالموضوع: {topic}\nالسبب: {exc}")

        fb_ok = bool(facebook_post_id) and str(row.get("Facebook Status", "PUBLISHED") or "PUBLISHED").strip().upper() == "PUBLISHED"
        li_post_ok = bool(linkedin_post_id)
        if not fb_ok and not li_post_ok:
            final_status = "FAILED"
        elif fb_ok and li_post_ok:
            final_status = "PUBLISHED"
        else:
            final_status = "PARTIAL_FAILED"
        final_error = " | ".join(linkedin_interaction_errors)[:1500]
        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            {
                "الحالة": final_status,
                "Facebook Status": "PUBLISHED" if fb_ok else "FAILED",
                "Facebook Post ID": facebook_post_id,
                "LinkedIn Status": "PUBLISHED" if li_post_ok else "FAILED",
                "LinkedIn Post ID": linkedin_post_id,
                "LinkedIn Comment Status": "QUEUED" if li_post_ok else str(row.get("LinkedIn Comment Status", "")).strip().upper(),
                "LinkedIn Reaction Status": "QUEUED" if li_post_ok else str(row.get("LinkedIn Reaction Status", "")).strip().upper(),
                "وقت آخر تشغيل": current.isoformat(),
                "آخر خطأ": final_error,
            },
        )
        if final_status == "PUBLISHED":
            try:
                add_published_post(service, config["sheet_id"], source_row_id=row.get("ID", ""), topic=topic, content=facebook_post, publish_date=current.date().isoformat(), facebook_post_id=facebook_post_id, linkedin_post_id=linkedin_post_id, image_url=image_url or "", legal_sources=row.get("المصادر القانونية", ""), angle=row.get("ملاحظات", ""), objective=objective, review_level=review_level)
                log_publication(service, config["sheet_id"], source_row_id=row.get("ID", ""), topic=topic, pillar=pillar, objective=objective, facebook_post_id=facebook_post_id, linkedin_post_id=linkedin_post_id, facebook_comments="0", linkedin_comments="0", status=final_status)
            except Exception as exc:
                print(f"PostBank/Analytics logging failed: {exc}")
            notify(
                f"✅ Khyrat Legal Content Engine\nتم نشر: {topic}\n"
                f"Facebook: {'✅' if fb_ok else '❌'} | LinkedIn: {'✅' if li_post_ok else '❌'}\n"
                f"التعليقات: Facebook 3-7 | LinkedIn 3-7 (تم وضعها في Queue ويشغلها Engagement Worker)"
            )
        else:
            detail = final_error or "LinkedIn publishing did not complete."
            notify(f"🟠 Partial failure — سيتم استكمال المنصة الفاشلة تلقائيًا في التشغيل القادم دون تكرار المنصة الناجحة.\nالموضوع: {topic}\nLinkedIn: {detail}")
    except (ImageGenerationError, FacebookPublishError, LinkedInPublishError, RuntimeError) as exc:
        print(f"Pipeline failed: {exc}")
        print(traceback.format_exc())
        update_row(service, config["sheet_id"], sheet_name, row_number, {"الحالة": "FAILED", "آخر خطأ": str(exc), "وقت آخر تشغيل": current.isoformat()})
        notify(f"❌ Pipeline failed\nالموضوع: {topic}\nالسبب: {exc}")


def main() -> None:
    print("=" * 70)
    print("KHYRAT LEGAL CONTENT ENGINE - V2 SMART SOCIAL PIPELINE")
    print("=" * 70)
    current = now_cairo()
    print(f"Current Cairo time: {current.isoformat()}")
    config = load_config()
    service = create_service(config["service_account_info"])
    sheet_name = sheet_name_from_range(config["sheet_range"])
    ensure_headers(service, config["sheet_id"], sheet_name)
    values = get_values(service, config["sheet_id"], config["sheet_range"])
    if not values:
        print("No rows found.")
        return
    rows = [row_to_dict(row) for row in values[1:]]
    candidates = [(i, r) for i, r in enumerate(rows, start=2) if _is_due(r, current)]
    if not candidates:
        candidates = [(i, r) for i, r in enumerate(rows, start=2) if _failed_retry(r, current)][:1]
    if not candidates:
        print("No due rows found.")
        return
    row_number, row = candidates[0]
    process_row(service=service, config=config, sheet_name=sheet_name, row_number=row_number, row=row, current=current)


if __name__ == "__main__":
    main()
