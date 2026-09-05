from __future__ import annotations

import os
import time
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
from linkedin_publisher import LinkedInPublishError, add_comment as linkedin_add_comment, like_post as linkedin_like_post, publish_to_linkedin, resolve_member_urn
from post_bank import add_published_post, build_previous_context, get_bank_rows
from sheets import create_service, ensure_headers, get_values, row_to_dict, update_row
from telegram_bot import notify, notify_linkedin_interaction, send_review_request
from utils import now_cairo, parse_date, parse_time, sheet_name_from_range

GENERATED_DIR = Path("generated")
COMMENT_DELAY_SECONDS = 12
FACEBOOK_COMMENT_LIMIT = 20
LINKEDIN_COMMENT_LIMIT = 5
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


def _publish_comments_facebook(post_id: str, comments: list[str], config) -> int:
    published = 0
    for index, message in enumerate(comments[:FACEBOOK_COMMENT_LIMIT], start=1):
        result = facebook_add_comment(post_id=post_id, page_access_token=config["facebook_page_access_token"], graph_version=config["facebook_graph_version"], message=message)
        count = int(result.get("published_count", 1) or 0)
        if result.get("status") == "PUBLISHED":
            published += count
        print(f"Facebook comment {index}: {result.get('status')} | like={result.get('like_status')} | like_error={result.get('like_error', '')}")
        time.sleep(COMMENT_DELAY_SECONDS)
    return published


def _publish_extra_linkedin_comments(post_urn: str, author_urn: str, comments: list[str], config) -> tuple[int, list[str], bool]:
    published, failures, permission_blocked = 0, [], False
    for index, message in enumerate(comments[1:LINKEDIN_COMMENT_LIMIT], start=2):
        result = linkedin_add_comment(token=config["linkedin_access_token"], actor_urn=author_urn, post_urn=post_urn, message=message)
        if result.status == "PUBLISHED":
            published += 1
        else:
            failures.append(f"comment {index}: {result.error or result.status}")
            permission_blocked = permission_blocked or _is_permission_blocked(result)
            if permission_blocked:
                break
        print(f"LinkedIn comment {index}/{LINKEDIN_COMMENT_LIMIT}: {result.status} | http={result.http_status} | error={result.error}")
        time.sleep(COMMENT_DELAY_SECONDS)
    return published, failures, permission_blocked


def _prepare_editorial_assets(*, config, topic: str, facebook_post: str, legal_sources: str) -> dict:
    comments = generate_comments(api_key=config["gemini_api_key"], model=config["gemini_model"], topic=topic, post=facebook_post, legal_sources=legal_sources)
    reviewed = review_and_prepare(api_key=config["gemini_api_key"], model=config["gemini_model"], topic=topic, facebook_post=facebook_post, facebook_comments=comments["facebook_comments"][:5], linkedin_comments=comments["linkedin_comments"], legal_sources=legal_sources)
    reviewed["facebook_comments"] = reviewed["facebook_comments"] + comments["facebook_comments"][5:FACEBOOK_COMMENT_LIMIT]
    reviewed["facebook_post"] = _ensure_facebook_cta(reviewed["facebook_post"])
    return reviewed


def _generate_if_needed(*, service, config, sheet_name, row_number, row, current, topic, bank_rows):
    existing_post = str(row.get("المحتوى", "") or "").strip()
    existing_image_url = str(row.get("رابط الصورة", "") or "").strip()
    raw_id = row.get("ID", "") or f"row-{row_number}"
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in raw_id)
    image_path = GENERATED_DIR / f"{safe_id}.jpg"
    recovery = str(row.get("الحالة", "")).strip().upper() in {"FAILED", "PARTIAL_FAILED", "READY_FOR_SOCIAL_PUBLISH"}
    if recovery and existing_post and image_path.is_file():
        return existing_post, existing_image_url, image_path, "CLEAR", ""
    previous_context = build_previous_context(bank_rows) + "\n" + build_diversity_context(topic, build_previous_context(bank_rows))
    duplicate_score, duplicate_topic = _duplicate_score(topic, bank_rows)
    if duplicate_score >= 0.88:
        previous_context += f"\nIMPORTANT: avoid repeating this recent topic verbatim: {duplicate_topic}"
    result = generate_post(api_key=config["gemini_api_key"], model=config["gemini_model"], topic=topic, legal_sources=row.get("المصادر القانونية", ""), previous_context=previous_context)
    post = str(result.get("post", "") or "").strip()
    image_brief = str(result.get("image_brief", "") or "").strip()
    review_level = str(result.get("review_level", "REVIEW") or "REVIEW").upper()
    review_text = " | ".join(str(x).strip() for x in result.get("review_flags", []) if str(x).strip())
    if not post or not image_brief:
        raise RuntimeError("Gemini returned incomplete content.")
    if review_level == "BLOCK":
        update_row(service, config["sheet_id"], sheet_name, row_number, {"الحالة": "NEEDS_REVIEW", "المحتوى": post, "وصف الصورة": image_brief, "آخر خطأ": review_text or "Legal review required.", "وقت آخر تشغيل": current.isoformat()})
        _notify_review(row_number, {**row, "المحتوى": post}, "BLOCK", review_text, config)
        return None, None, None, "BLOCK", review_text
    if review_level == "REVIEW":
        notify(f"🟡 Review advisory — سيتم النشر تلقائيًا.\nالموضوع: {topic}\nالملاحظة: {review_text or 'مراجعة مستحسنة'}")
    create_legal_image(topic=topic, image_brief=image_brief, output_path=str(image_path), cloudflare_account_id=config["cloudflare_account_id"], cloudflare_api_token=config["cloudflare_api_token"])
    image_url = github_raw_url(str(image_path))
    update_row(service, config["sheet_id"], sheet_name, row_number, {"الحالة": "READY_FOR_SOCIAL_PUBLISH", "المحتوى": post, "وصف الصورة": image_brief, "رابط الصورة": image_url, "وقت آخر تشغيل": current.isoformat()})
    return post, image_url, image_path, review_level, review_text


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
        facebook_comments_ready, linkedin_comments_ready = editorial["facebook_comments"], editorial["linkedin_comments"]

        facebook_post_id = str(row.get("Facebook Post ID", "") or "").strip() if original_status in {"FAILED", "PARTIAL_FAILED", "READY_FOR_SOCIAL_PUBLISH"} else ""
        linkedin_post_id = str(row.get("LinkedIn Post ID", "") or "").strip() if original_status in {"FAILED", "PARTIAL_FAILED", "READY_FOR_SOCIAL_PUBLISH"} else ""
        facebook_comments = 0
        linkedin_comments = 0
        linkedin_interaction_errors: list[str] = []
        linkedin_comment_status = str(row.get("LinkedIn Comment Status", "")).strip().upper()
        linkedin_reaction_status = str(row.get("LinkedIn Reaction Status", "")).strip().upper()

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
                    print(f"Facebook like: {facebook_like_post(post_id=facebook_post_id, page_access_token=config['facebook_page_access_token'], graph_version=config['facebook_graph_version'])['status']}")
                except Exception as exc:
                    print(f"Facebook like failed: {exc}")
            except FacebookPublishError as exc:
                error = f"Facebook: {exc}"
                update_row(service, config["sheet_id"], sheet_name, row_number, {"Facebook Status": "FAILED", "آخر خطأ": error})
                notify(f"🚨 Facebook publishing failed\nالموضوع: {topic}\nالسبب: {exc}")

        linkedin_status = str(row.get("LinkedIn Status", "")).strip().upper()
        if linkedin_post_id and linkedin_status == "PUBLISHED":
            print(f"Idempotency: LinkedIn post already published as {linkedin_post_id}; retrying only eligible interactions.")
            token = config["linkedin_access_token"]
            author = (config.get("linkedin_author_urn", "") or "").strip() or resolve_member_urn(token)
            if linkedin_comment_status not in {"PUBLISHED", "DISABLED"}:
                try:
                    result = linkedin_add_comment(token=token, actor_urn=author, post_urn=linkedin_post_id, message=linkedin_comments_ready[0])
                    if result.status == "PUBLISHED":
                        linkedin_comments = 1
                    elif _is_permission_blocked(result):
                        linkedin_comment_status = "DISABLED"
                        linkedin_interaction_errors.append(result.error or "LinkedIn comment permission unavailable")
                    else:
                        linkedin_interaction_errors.append(result.error or result.status)
                except Exception as exc:
                    if _is_permission_blocked(exc):
                        linkedin_comment_status = "DISABLED"
                    else:
                        linkedin_interaction_errors.append(f"first comment retry: {exc}")
            if linkedin_comment_status == "PUBLISHED":
                linkedin_comments = max(linkedin_comments, 1)
            if linkedin_comment_status not in {"DISABLED", "FAILED"} and linkedin_comments:
                try:
                    extra_count, extra_errors, blocked = _publish_extra_linkedin_comments(linkedin_post_id, author, linkedin_comments_ready, config)
                    linkedin_comments += extra_count
                    linkedin_interaction_errors.extend(extra_errors)
                    if blocked:
                        linkedin_comment_status = "DISABLED"
                except Exception as exc:
                    linkedin_interaction_errors.append(str(exc))
            if linkedin_comment_status not in {"DISABLED", "PUBLISHED"}:
                linkedin_comment_status = "PUBLISHED" if linkedin_comments >= LINKEDIN_COMMENT_LIMIT else "FAILED"
            if linkedin_reaction_status not in {"LIKED", "DISABLED"}:
                try:
                    reaction = linkedin_like_post(token=token, actor_urn=author, post_urn=linkedin_post_id)
                    if reaction.status == "LIKED":
                        linkedin_reaction_status = "LIKED"
                    elif _is_permission_blocked(reaction):
                        linkedin_reaction_status = "DISABLED"
                        linkedin_interaction_errors.append(reaction.error or "LinkedIn reaction permission unavailable")
                    else:
                        linkedin_reaction_status = "FAILED"
                        linkedin_interaction_errors.append(reaction.error or reaction.status)
                except Exception as exc:
                    linkedin_reaction_status = "DISABLED" if _is_permission_blocked(exc) else "FAILED"
                    if linkedin_reaction_status == "FAILED":
                        linkedin_interaction_errors.append(f"reaction retry: {exc}")
            update_row(service, config["sheet_id"], sheet_name, row_number, {"LinkedIn Comment Status": linkedin_comment_status or "FAILED", "LinkedIn Reaction Status": linkedin_reaction_status or "FAILED", "آخر خطأ": " | ".join(linkedin_interaction_errors)[:1500]})
        else:
            try:
                token = config["linkedin_access_token"]
                author = (config.get("linkedin_author_urn", "") or "").strip() or resolve_member_urn(token)
                linkedin = publish_to_linkedin(token=token, author_urn=author, image_path=image_path, commentary=linkedin_post, first_comment=linkedin_comments_ready[0])
                linkedin_post_id = linkedin["post_urn"]
                comment_result, like_result = linkedin["comment"], linkedin["like"]
                comment_status = _interaction_status(comment_result, "PUBLISHED", "DISABLED")
                reaction_status = _interaction_status(like_result, "LIKED", "DISABLED")
                if comment_status == "PUBLISHED":
                    linkedin_comments = 1
                if comment_status != "PUBLISHED":
                    linkedin_interaction_errors.append(comment_result.get("error") or comment_result.get("status") or "first comment failed")
                if reaction_status != "LIKED":
                    linkedin_interaction_errors.append(like_result.get("error") or like_result.get("status") or "post reaction failed")
                if comment_status == "PUBLISHED":
                    try:
                        extra_count, extra_errors, blocked = _publish_extra_linkedin_comments(linkedin_post_id, author, linkedin_comments_ready, config)
                        linkedin_comments += extra_count
                        linkedin_interaction_errors.extend(extra_errors)
                        if blocked:
                            comment_status = "DISABLED"
                        elif linkedin_comments >= LINKEDIN_COMMENT_LIMIT:
                            comment_status = "PUBLISHED"
                    except Exception as exc:
                        linkedin_interaction_errors.append(str(exc))
                update_row(service, config["sheet_id"], sheet_name, row_number, {"LinkedIn Status": "PUBLISHED", "LinkedIn Post ID": linkedin_post_id, "LinkedIn Comment Status": comment_status, "LinkedIn Reaction Status": reaction_status, "آخر خطأ": " | ".join(linkedin_interaction_errors)[:1500]})
                permission_only = bool(linkedin_interaction_errors) and all(_is_permission_blocked(x) for x in [comment_result, like_result] if x.get("status") != "PUBLISHED" and x.get("status") != "LIKED")
                if linkedin_interaction_errors and not permission_only:
                    try:
                        notify_linkedin_interaction(topic=topic, post_urn=linkedin_post_id, comment=comment_result, like=like_result)
                    except Exception as exc:
                        print(f"Telegram LinkedIn diagnostic failed: {exc}")
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
        update_row(service, config["sheet_id"], sheet_name, row_number, {"الحالة": final_status, "Facebook Status": "PUBLISHED" if fb_ok else "FAILED", "Facebook Post ID": facebook_post_id, "LinkedIn Status": "PUBLISHED" if li_post_ok else "FAILED", "LinkedIn Post ID": linkedin_post_id, "وقت آخر تشغيل": current.isoformat(), "آخر خطأ": final_error})
        if final_status == "PUBLISHED":
            try:
                add_published_post(service, config["sheet_id"], source_row_id=row.get("ID", ""), topic=topic, content=facebook_post, publish_date=current.date().isoformat(), facebook_post_id=facebook_post_id, linkedin_post_id=linkedin_post_id, image_url=image_url or "", legal_sources=row.get("المصادر القانونية", ""), angle=row.get("ملاحظات", ""), objective=objective, review_level=review_level)
                log_publication(service, config["sheet_id"], source_row_id=row.get("ID", ""), topic=topic, pillar=pillar, objective=objective, facebook_post_id=facebook_post_id, linkedin_post_id=linkedin_post_id, facebook_comments=str(facebook_comments), linkedin_comments=str(linkedin_comments), status=final_status)
            except Exception as exc:
                print(f"PostBank/Analytics logging failed: {exc}")
            interaction_note = " | LinkedIn interactions: disabled by API permissions" if any(x == "DISABLED" for x in (linkedin_comment_status, linkedin_reaction_status)) else ""
            notify(f"✅ Khyrat Legal Content Engine\nتم نشر: {topic}\nFacebook: {'✅' if fb_ok else '❌'} | LinkedIn: {'✅' if li_post_ok else '❌'}\nالتعليقات: Facebook {facebook_comments}/20 | LinkedIn {linkedin_comments}/5{interaction_note}")
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
