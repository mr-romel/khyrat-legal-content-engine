from __future__ import annotations

import os
import time
import traceback
from difflib import SequenceMatcher
from pathlib import Path

from analytics import log_publication
from comment_engine import generate_comments
from editorial_review import review_and_prepare
from content_planner import classify
from facebook_publisher import FacebookPublishError, add_comment as facebook_add_comment, like_post as facebook_like_post, publish_photo
from gemini import generate_post
from image_generator import ImageGenerationError, create_legal_image
from linkedin_publisher import LinkedInPublishError, add_comment as linkedin_add_comment, publish_to_linkedin, resolve_member_urn
from post_bank import add_published_post, build_previous_context, get_bank_rows
from sheets import update_row
from telegram_bot import notify, send_review_request, notify_linkedin_interaction

GENERATED_DIR = Path("generated")
COMMENT_DELAY_SECONDS = 12
DRY_RUN = os.getenv("KHYRAT_DRY_RUN", "false").strip().lower() in {"1", "true", "yes", "on"}


def github_raw_url(relative_path: str) -> str:
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    branch = os.getenv("GITHUB_REF_NAME", "main").strip() or "main"
    if not repository:
        return ""
    normalized = relative_path.replace("\\", "/").lstrip("/")
    return f"https://raw.githubusercontent.com/{repository}/{branch}/{normalized}"


def _normalized_topic(value: str) -> str:
    chars = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in (value or ""))
    return " ".join(chars.split())


def _duplicate_score(topic: str, bank_rows: list[dict[str, str]]) -> tuple[float, str]:
    normalized = _normalized_topic(topic)
    best_score = 0.0
    best_topic = ""
    for row in bank_rows:
        candidate = _normalized_topic(row.get("الموضوع", ""))
        if not candidate:
            continue
        score = SequenceMatcher(None, normalized, candidate).ratio()
        if score > best_score:
            best_score = score
            best_topic = row.get("الموضوع", "")
    return best_score, best_topic


def _notify_review(row_number: int, row: dict[str, str], review_level: str, review_text: str, config) -> None:
    send_review_request(row_number=row_number, topic=row.get("الموضوع", ""), post=row.get("المحتوى", ""), reason=review_text, sheet_id=config["sheet_id"], status=review_level)


def _publish_comments_facebook(post_id: str, comments: list[str], config) -> int:
    published = 0
    for message in comments[:5]:
        result = facebook_add_comment(post_id=post_id, page_access_token=config["facebook_page_access_token"], graph_version=config["facebook_graph_version"], message=message)
        if result.get("status") == "PUBLISHED":
            published += 1
        time.sleep(COMMENT_DELAY_SECONDS)
    return published


def _publish_extra_linkedin_comments(post_urn: str, author_urn: str, comments: list[str], config) -> int:
    published = 0
    for message in comments[1:5]:
        result = linkedin_add_comment(token=config["linkedin_access_token"], actor_urn=author_urn, post_urn=post_urn, message=message)
        if result.status == "PUBLISHED":
            published += 1
        time.sleep(COMMENT_DELAY_SECONDS)
    return published


def _prepare_editorial_assets(*, config, topic: str, facebook_post: str, legal_sources: str) -> dict:
    comments = generate_comments(api_key=config["gemini_api_key"], model=config["gemini_model"], topic=topic, post=facebook_post, legal_sources=legal_sources)
    reviewed = review_and_prepare(api_key=config["gemini_api_key"], model=config["gemini_model"], topic=topic, facebook_post=facebook_post, facebook_comments=comments["facebook_comments"], linkedin_comments=comments["linkedin_comments"], legal_sources=legal_sources)
    print("Editorial gate: spelling/grammar review completed; LinkedIn professional rewrite completed.")
    return reviewed


def _generate_if_needed(*, service, config, sheet_name, row_number, row, current, topic, bank_rows):
    existing_post = str(row.get("المحتوى", "") or "").strip()
    existing_image_url = str(row.get("رابط الصورة", "") or "").strip()
    raw_id = row.get("ID", "") or f"row-{row_number}"
    safe_id = "".join(char if char.isalnum() or char in "-_" else "_" for char in raw_id)
    image_path = GENERATED_DIR / f"{safe_id}.jpg"
    recovery = str(row.get("الحالة", "")).strip().upper() in {"FAILED", "PARTIAL_FAILED", "READY_FOR_SOCIAL_PUBLISH"}
    if recovery and existing_post and image_path.is_file():
        print("Recovery mode: reusing existing generated content/image; no duplicate AI generation.")
        return existing_post, existing_image_url, image_path, "CLEAR", ""
    previous_context = build_previous_context(bank_rows)
    duplicate_score, duplicate_topic = _duplicate_score(topic, bank_rows)
    if duplicate_score >= 0.88:
        print(f"Duplicate guard: similarity={duplicate_score:.2f} with '{duplicate_topic}'.")
        previous_context += f"\nIMPORTANT: avoid repeating this recent topic verbatim: {duplicate_topic}"
    result = generate_post(api_key=config["gemini_api_key"], model=config["gemini_model"], topic=topic, legal_sources=row.get("المصادر القانونية", ""), previous_context=previous_context)
    post = str(result.get("post", "") or "").strip()
    image_brief = str(result.get("image_brief", "") or "").strip()
    review_level = str(result.get("review_level", "REVIEW") or "REVIEW").upper()
    review_flags = result.get("review_flags", [])
    review_text = " | ".join(str(item).strip() for item in review_flags if str(item).strip())
    if not post or not image_brief:
        raise RuntimeError("Gemini returned incomplete content.")
    if review_level == "BLOCK":
        update_row(service, config["sheet_id"], sheet_name, row_number, {"الحالة": "NEEDS_REVIEW", "المحتوى": post, "وصف الصورة": image_brief, "آخر خطأ": review_text or "Legal review required.", "وقت آخر تشغيل": current.isoformat()})
        _notify_review(row_number, {**row, "المحتوى": post}, "BLOCK", review_text, config)
        return None, None, None, "BLOCK", review_text
    if review_level == "REVIEW":
        notify("🟡 Review advisory — سيتم النشر تلقائيًا لأن الملاحظة لا تستوجب إيقاف التشغيل.\n" f"الموضوع: {topic}\n" f"الملاحظة: {review_text or 'مراجعة مستحسنة'}")
    create_legal_image(topic=topic, image_brief=image_brief, output_path=str(image_path), cloudflare_account_id=config["cloudflare_account_id"], cloudflare_api_token=config["cloudflare_api_token"])
    image_url = github_raw_url(str(image_path).replace("\\", "/"))
    update_row(service, config["sheet_id"], sheet_name, row_number, {"الحالة": "READY_FOR_SOCIAL_PUBLISH", "المحتوى": post, "وصف الصورة": image_brief, "رابط الصورة": image_url, "وقت آخر تشغيل": current.isoformat()})
    return post, image_url, image_path, review_level, review_text


def process_row(*, service, config, sheet_name: str, row_number: int, row: dict[str, str], current) -> None:
    topic = row.get("الموضوع", "").strip()
    if not topic:
        raise RuntimeError(f"Row {row_number} has no topic.")
    print(f"Processing row {row_number}: {topic}")
    bank_rows = get_bank_rows(service, config["sheet_id"])
    original_status = str(row.get("الحالة", "")).strip().upper()
    try:
        if DRY_RUN:
            print("=" * 70)
            print("KHYRAT LEGAL CONTENT ENGINE - SAFE DRY RUN")
            print("No Facebook/LinkedIn publishing, likes, or real comments will be performed.")
            post, image_url, image_path, review_level, review_text = _generate_if_needed(service=service, config=config, sheet_name=sheet_name, row_number=row_number, row=row, current=current, topic=topic, bank_rows=bank_rows)
            if review_level == "BLOCK":
                print(f"DRY RUN result: BLOCK / review required: {review_text or 'no details'}")
                return
            if not post or not image_path:
                raise RuntimeError("Dry run did not produce content/image assets.")
            editorial = _prepare_editorial_assets(config=config, topic=topic, facebook_post=post, legal_sources=row.get("المصادر القانونية", ""))
            print(f"DRY RUN generated: Facebook comments={len(editorial['facebook_comments'])}/5 | LinkedIn comments={len(editorial['linkedin_comments'])}/5")
            print(f"DRY RUN LinkedIn post length: {len(editorial['linkedin_post'])} characters")
            print(f"DRY RUN image: {image_path}")
            print("DRY RUN completed successfully; no social API write was attempted.")
            return
        update_row(service, config["sheet_id"], sheet_name, row_number, {"الحالة": "PROCESSING" if original_status not in {"FAILED", "PARTIAL_FAILED", "READY_FOR_SOCIAL_PUBLISH"} else original_status, "آخر خطأ": "", "وقت آخر تشغيل": current.isoformat()})
        pillar, objective = classify(topic, row.get("المحتوى", ""))
        post, image_url, image_path, review_level, review_text = _generate_if_needed(service=service, config=config, sheet_name=sheet_name, row_number=row_number, row=row, current=current, topic=topic, bank_rows=bank_rows)
        if review_level == "BLOCK":
            return
        if not post or not image_path:
            raise RuntimeError("Content/image generation did not produce publishable assets.")
        editorial = _prepare_editorial_assets(config=config, topic=topic, facebook_post=post, legal_sources=row.get("المصادر القانونية", ""))
        facebook_post = editorial["facebook_post"]
        linkedin_post = editorial["linkedin_post"]
        facebook_comments_ready = editorial["facebook_comments"]
        linkedin_comments_ready = editorial["linkedin_comments"]
        facebook_post_id = str(row.get("Facebook Post ID", "") or "").strip() if original_status in {"FAILED", "PARTIAL_FAILED", "READY_FOR_SOCIAL_PUBLISH"} else ""
        linkedin_post_id = str(row.get("LinkedIn Post ID", "") or "").strip() if original_status in {"FAILED", "PARTIAL_FAILED", "READY_FOR_SOCIAL_PUBLISH"} else ""
        facebook_comments = linkedin_comments = 0
        if facebook_post_id and str(row.get("Facebook Status", "")).strip().upper() == "PUBLISHED":
            print(f"Idempotency: Facebook already published as {facebook_post_id}; skipping duplicate publish.")
        else:
            try:
                facebook = publish_photo(page_id=config["facebook_page_id"], page_access_token=config["facebook_page_access_token"], graph_version=config["facebook_graph_version"], image_path=image_path, caption=facebook_post)
                facebook_post_id = facebook["post_id"]
                update_row(service, config["sheet_id"], sheet_name, row_number, {"Facebook Status": "PUBLISHED", "Facebook Post ID": facebook_post_id})
                try:
                    facebook_comments = _publish_comments_facebook(facebook_post_id, facebook_comments_ready, config)
                except Exception as exc:
                    print(f"Facebook comment engine failed: {exc}")
                try:
                    like = facebook_like_post(post_id=facebook_post_id, page_access_token=config["facebook_page_access_token"], graph_version=config["facebook_graph_version"])
                    print(f"Facebook like: {like['status']}")
                except Exception as exc:
                    print(f"Facebook like failed: {exc}")
            except FacebookPublishError as exc:
                error = f"Facebook: {exc}"
                print(error)
                update_row(service, config["sheet_id"], sheet_name, row_number, {"Facebook Status": "FAILED", "آخر خطأ": error})
                notify(f"🚨 Facebook publishing failed\nالموضوع: {topic}\nالسبب: {exc}")
        if linkedin_post_id and str(row.get("LinkedIn Status", "")).strip().upper() == "PUBLISHED":
            print(f"Idempotency: LinkedIn already published as {linkedin_post_id}; skipping duplicate publish.")
        else:
            try:
                linkedin_access_token = config["linkedin_access_token"]
                linkedin_author_urn = (config.get("linkedin_author_urn", "") or "").strip() or resolve_member_urn(linkedin_access_token)
                linkedin = publish_to_linkedin(token=linkedin_access_token, author_urn=linkedin_author_urn, image_path=image_path, commentary=linkedin_post, first_comment=linkedin_comments_ready[0])
                linkedin_post_id = linkedin["post_urn"]
                try:
                    notify_linkedin_interaction(topic=topic, post_urn=linkedin_post_id, comment=linkedin["comment"], like=linkedin["like"])
                except Exception as exc:
                    print(f"Telegram LinkedIn diagnostic failed: {exc}")
                linkedin_comments = 1 if linkedin["comment"]["status"] == "PUBLISHED" else 0
                try:
                    linkedin_comments += _publish_extra_linkedin_comments(linkedin_post_id, linkedin_author_urn, linkedin_comments_ready, config)
                except Exception as exc:
                    print(f"LinkedIn comment engine failed: {exc}")
                update_row(service, config["sheet_id"], sheet_name, row_number, {"LinkedIn Status": "PUBLISHED", "LinkedIn Post ID": linkedin_post_id, "LinkedIn Comment Status": "PUBLISHED" if linkedin_comments else "FAILED"})
            except LinkedInPublishError as exc:
                error = f"LinkedIn: {exc}"
                print(error)
                update_row(service, config["sheet_id"], sheet_name, row_number, {"LinkedIn Status": "FAILED", "آخر خطأ": error})
                notify(f"🚨 LinkedIn publishing failed\nالموضوع: {topic}\nالسبب: {exc}")
        fb_ok = bool(facebook_post_id)
        li_ok = bool(linkedin_post_id)
        final_status = "FAILED" if not fb_ok and not li_ok else "PUBLISHED" if fb_ok and li_ok else "PARTIAL_FAILED"
        update_row(service, config["sheet_id"], sheet_name, row_number, {"الحالة": final_status, "Facebook Status": "PUBLISHED" if fb_ok else "FAILED", "Facebook Post ID": facebook_post_id, "LinkedIn Status": "PUBLISHED" if li_ok else "FAILED", "LinkedIn Post ID": linkedin_post_id, "وقت آخر تشغيل": current.isoformat()})
        if final_status == "PUBLISHED":
            try:
                add_published_post(service, config["sheet_id"], source_row_id=row.get("ID", ""), topic=topic, content=facebook_post, publish_date=current.date().isoformat(), facebook_post_id=facebook_post_id, linkedin_post_id=linkedin_post_id, image_url=image_url or "", legal_sources=row.get("المصادر القانونية", ""), angle=row.get("ملاحظات", ""), objective=objective, review_level=review_level)
                log_publication(service, config["sheet_id"], source_row_id=row.get("ID", ""), topic=topic, pillar=pillar, objective=objective, facebook_post_id=facebook_post_id, linkedin_post_id=linkedin_post_id, facebook_comments=str(facebook_comments), linkedin_comments=str(linkedin_comments), status=final_status)
            except Exception as exc:
                print(f"PostBank/Analytics logging failed: {exc}")
            notify("✅ Khyrat Legal Content Engine\n" f"تم نشر: {topic}\n" f"Facebook: {'✅' if fb_ok else '❌'} | LinkedIn: {'✅' if li_ok else '❌'}\n" f"التعليقات: Facebook {facebook_comments}/5 | LinkedIn {linkedin_comments}/5")
        elif final_status == "PARTIAL_FAILED":
            notify("🟠 Partial failure — سيتم استكمال المنصة الفاشلة تلقائيًا في التشغيل القادم دون تكرار المنصة الناجحة.\n" f"الموضوع: {topic}")
    except (ImageGenerationError, FacebookPublishError, LinkedInPublishError, RuntimeError) as exc:
        print(f"Pipeline failed: {exc}")
        print(traceback.format_exc())
        update_row(service, config["sheet_id"], sheet_name, row_number, {"الحالة": "FAILED", "آخر خطأ": str(exc), "وقت آخر تشغيل": current.isoformat()})
        notify(f"❌ Pipeline failed\nالموضوع: {topic}\nالسبب: {exc}")
