from __future__ import annotations

import os
import time
import traceback
from difflib import SequenceMatcher
from pathlib import Path

from analytics import log_publication
from comment_engine import generate_comments
from config import ConfigError, load_config
from content_planner import classify
from facebook_publisher import FacebookPublishError, add_comment as facebook_add_comment, like_post as facebook_like_post, publish_photo
from gemini import generate_post
from image_generator import ImageGenerationError, create_legal_image
from linkedin_publisher import LinkedInPublishError, add_comment as linkedin_add_comment, publish_to_linkedin, resolve_member_urn
from post_bank import add_published_post, build_previous_context, get_bank_rows
from sheets import HEADERS, create_service, ensure_headers, get_values, row_to_dict, update_row
from telegram_bot import notify, send_review_request
from utils import now_cairo, parse_date, parse_time, sheet_name_from_range


GENERATED_DIR = Path("generated")
COMMENT_DELAY_SECONDS = 12


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


def _is_due(row: dict[str, str], current) -> bool:
    status = str(row.get("الحالة", "READY")).strip().upper()
    if status not in {"READY", "FAILED"}:
        return False
    target_date = parse_date(row.get("تاريخ النشر", ""))
    target_time = parse_time(row.get("ساعة النشر", ""))
    if target_date is None or target_time is None:
        return False
    if current.date() < target_date:
        return False
    target = current.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)
    delta = (current - target).total_seconds()
    return 0 <= delta < 3600


def _failed_retry(row: dict[str, str], current) -> bool:
    return str(row.get("الحالة", "")).strip().upper() == "FAILED" and bool(row.get("الموضوع", "").strip())


def _notify_review(row_number: int, row: dict[str, str], review_level: str, review_text: str, config) -> None:
    send_review_request(
        row_number=row_number,
        topic=row.get("الموضوع", ""),
        post=row.get("المحتوى", ""),
        reason=review_text,
        sheet_id=config["sheet_id"],
        status=review_level,
    )


def _publish_comments_facebook(post_id: str, comments: list[str], config) -> int:
    published = 0
    for message in comments[:5]:
        result = facebook_add_comment(
            post_id=post_id,
            page_access_token=config["facebook_page_access_token"],
            graph_version=config["facebook_graph_version"],
            message=message,
        )
        if result.get("status") == "PUBLISHED":
            published += 1
        time.sleep(COMMENT_DELAY_SECONDS)
    return published


def _publish_extra_linkedin_comments(post_urn: str, author_urn: str, comments: list[str], config) -> int:
    published = 0
    for message in comments[1:5]:
        result = linkedin_add_comment(
            token=config["linkedin_access_token"],
            actor_urn=author_urn,
            post_urn=post_urn,
            message=message,
        )
        if result.status == "PUBLISHED":
            published += 1
        time.sleep(COMMENT_DELAY_SECONDS)
    return published


def process_row(*, service, config, sheet_name: str, row_number: int, row: dict[str, str], current) -> None:
    topic = row.get("الموضوع", "").strip()
    if not topic:
        raise RuntimeError(f"Row {row_number} has no topic.")

    print(f"Processing row {row_number}: {topic}")
    update_row(service, config["sheet_id"], sheet_name, row_number, {
        "الحالة": "PROCESSING",
        "Facebook Status": "PROCESSING",
        "آخر خطأ": "",
        "وقت آخر تشغيل": current.isoformat(),
    })

    bank_rows = get_bank_rows(service, config["sheet_id"])
    previous_context = build_previous_context(bank_rows)
    duplicate_score, duplicate_topic = _duplicate_score(topic, bank_rows)
    if duplicate_score >= 0.88:
        print(f"Duplicate guard: similarity={duplicate_score:.2f} with '{duplicate_topic}'.")
        previous_context += f"\nIMPORTANT: avoid repeating this recent topic verbatim: {duplicate_topic}"

    pillar, objective = classify(topic)

    try:
        result = generate_post(
            api_key=config["gemini_api_key"],
            model=config["gemini_model"],
            topic=topic,
            legal_sources=row.get("المصادر القانونية", ""),
            previous_context=previous_context,
        )
        post = str(result.get("post", "") or "").strip()
        image_brief = str(result.get("image_brief", "") or "").strip()
        review_level = str(result.get("review_level", "REVIEW") or "REVIEW").upper()
        review_flags = result.get("review_flags", [])
        review_text = " | ".join(str(item).strip() for item in review_flags if str(item).strip())
        if not post or not image_brief:
            raise RuntimeError("Gemini returned incomplete content.")

        if review_level == "BLOCK":
            update_row(service, config["sheet_id"], sheet_name, row_number, {
                "الحالة": "NEEDS_REVIEW",
                "المحتوى": post,
                "وصف الصورة": image_brief,
                "آخر خطأ": review_text or "Legal review required.",
                "وقت آخر تشغيل": current.isoformat(),
            })
            _notify_review(row_number, {**row, "المحتوى": post}, "BLOCK", review_text, config)
            print("BLOCK: this row waits for human approval; other scheduled runs remain independent.")
            return

        if review_level == "REVIEW":
            notify(
                "🟡 Review advisory — تم السماح بالنشر تلقائيًا.\n"
                f"الموضوع: {topic}\n"
                f"الملاحظة: {review_text or 'مراجعة مستحسنة'}"
            )

        raw_id = row.get("ID", "") or f"row-{row_number}"
        safe_id = "".join(char if char.isalnum() or char in "-_" else "_" for char in raw_id)
        image_path = GENERATED_DIR / f"{safe_id}.jpg"
        create_legal_image(
            topic=topic,
            image_brief=image_brief,
            output_path=str(image_path),
            cloudflare_account_id=config["cloudflare_account_id"],
            cloudflare_api_token=config["cloudflare_api_token"],
        )
        image_url = github_raw_url(str(image_path).replace("\\", "/"))

        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "الحالة": "READY_FOR_SOCIAL_PUBLISH",
            "المحتوى": post,
            "وصف الصورة": image_brief,
            "رابط الصورة": image_url,
            "وقت آخر تشغيل": current.isoformat(),
        })

        facebook_post_id = ""
        linkedin_post_id = ""
        facebook_comments = 0
        linkedin_comments = 0

        # Facebook is isolated from LinkedIn so one platform failure does not stop the other.
        try:
            facebook = publish_photo(
                page_id=config["facebook_page_id"],
                page_access_token=config["facebook_page_access_token"],
                graph_version=config["facebook_graph_version"],
                image_path=image_path,
                caption=post,
            )
            facebook_post_id = facebook["post_id"]
            update_row(service, config["sheet_id"], sheet_name, row_number, {
                "Facebook Status": "PUBLISHED",
                "Facebook Post ID": facebook_post_id,
            })

            try:
                comments = generate_comments(
                    api_key=config["gemini_api_key"],
                    model=config["gemini_model"],
                    topic=topic,
                    post=post,
                    legal_sources=row.get("المصادر القانونية", ""),
                )
                facebook_comments = _publish_comments_facebook(facebook_post_id, comments["facebook_comments"], config)
            except Exception as exc:
                print(f"Facebook comment engine failed: {exc}")

            like = facebook_like_post(
                post_id=facebook_post_id,
                page_access_token=config["facebook_page_access_token"],
                graph_version=config["facebook_graph_version"],
            )
            print(f"Facebook like: {like['status']}")
        except FacebookPublishError as exc:
            error = f"Facebook: {exc}"
            print(error)
            update_row(service, config["sheet_id"], sheet_name, row_number, {
                "Facebook Status": "FAILED",
                "آخر خطأ": error,
            })
            notify(f"🚨 Facebook publishing failed\nالموضوع: {topic}\nالسبب: {exc}")

        # LinkedIn is independently attempted even if Facebook failed.
        try:
            linkedin_access_token = config["linkedin_access_token"]
            linkedin_author_urn = (config.get("linkedin_author_urn", "") or "").strip()
            if not linkedin_author_urn:
                linkedin_author_urn = resolve_member_urn(linkedin_access_token)

            linkedin = publish_to_linkedin(
                token=linkedin_access_token,
                author_urn=linkedin_author_urn,
                image_path=image_path,
                commentary=post,
                first_comment="لو عندك موقف قانوني مشابه، اكتب سؤالك في التعليقات.",
            )
            linkedin_post_id = linkedin["post_urn"]
            linkedin_comments = 1 if linkedin["comment"]["status"] == "PUBLISHED" else 0

            try:
                comments = generate_comments(
                    api_key=config["gemini_api_key"],
                    model=config["gemini_model"],
                    topic=topic,
                    post=post,
                    legal_sources=row.get("المصادر القانونية", ""),
                )
                linkedin_comments += _publish_extra_linkedin_comments(
                    linkedin_post_id,
                    linkedin_author_urn,
                    comments["linkedin_comments"],
                    config,
                )
            except Exception as exc:
                print(f"LinkedIn comment engine failed: {exc}")

            print(f"LinkedIn post succeeded: {linkedin_post_id}")
            update_row(service, config["sheet_id"], sheet_name, row_number, {
                "LinkedIn Status": "PUBLISHED",
                "LinkedIn Post ID": linkedin_post_id,
                "LinkedIn Comment Status": "PUBLISHED" if linkedin_comments else "FAILED",
            })
        except LinkedInPublishError as exc:
            error = f"LinkedIn: {exc}"
            print(error)
            update_row(service, config["sheet_id"], sheet_name, row_number, {
                "LinkedIn Status": "FAILED",
                "آخر خطأ": error,
            })
            notify(f"🚨 LinkedIn publishing failed\nالموضوع: {topic}\nالسبب: {exc}")

        if not facebook_post_id and not linkedin_post_id:
            raise RuntimeError("Both Facebook and LinkedIn publishing failed.")

        final_status = "PUBLISHED" if facebook_post_id or linkedin_post_id else "FAILED"
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "الحالة": final_status,
            "Facebook Status": "PUBLISHED" if facebook_post_id else "FAILED",
            "Facebook Post ID": facebook_post_id,
            "LinkedIn Status": "PUBLISHED" if linkedin_post_id else "FAILED",
            "LinkedIn Post ID": linkedin_post_id,
            "وقت آخر تشغيل": current.isoformat(),
        })

        try:
            add_published_post(
                service,
                config["sheet_id"],
                source_row_id=row.get("ID", ""),
                topic=topic,
                content=post,
                publish_date=current.date().isoformat(),
                facebook_post_id=facebook_post_id,
                linkedin_post_id=linkedin_post_id,
                image_url=image_url,
                legal_sources=row.get("المصادر القانونية", ""),
                angle=row.get("ملاحظات", ""),
                objective=objective,
                review_level=review_level,
            )
            log_publication(
                service,
                config["sheet_id"],
                source_row_id=row.get("ID", ""),
                topic=topic,
                pillar=pillar,
                objective=objective,
                facebook_post_id=facebook_post_id,
                linkedin_post_id=linkedin_post_id,
                facebook_comments=str(facebook_comments),
                linkedin_comments=str(linkedin_comments),
                status=final_status,
            )
        except Exception as exc:
            print(f"PostBank/Analytics logging failed: {exc}")

        notify(
            "✅ Khyrat Legal Content Engine\n"
            f"تم نشر: {topic}\n"
            f"Facebook: {'✅' if facebook_post_id else '❌'} | LinkedIn: {'✅' if linkedin_post_id else '❌'}\n"
            f"التعليقات: Facebook {facebook_comments}/5 | LinkedIn {linkedin_comments}/5"
        )

    except (ImageGenerationError, FacebookPublishError, LinkedInPublishError) as exc:
        error_text = f"{type(exc).__name__}: {exc}"
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "الحالة": "FAILED",
            "آخر خطأ": error_text,
            "وقت آخر تشغيل": current.isoformat(),
        })
        notify(f"🚨 Content pipeline failed\nالموضوع: {topic}\nالسبب: {error_text}")
        raise
    except Exception as exc:
        error_text = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "الحالة": "FAILED",
            "آخر خطأ": error_text,
            "وقت آخر تشغيل": current.isoformat(),
        })
        notify(f"🚨 Content pipeline failed\nالموضوع: {topic}\nالسبب: {error_text}")
        raise


def main() -> None:
    print("=" * 70)
    print("KHYRAT LEGAL CONTENT ENGINE - V2 SMART SOCIAL PIPELINE")
    print("=" * 70)
    config = load_config()
    service = create_service(config["service_account_info"])
    sheet_name = sheet_name_from_range(config["sheet_range"])
    ensure_headers(service, config["sheet_id"], sheet_name)

    values = get_values(service, config["sheet_id"], f"{sheet_name}!A:U")
    if not values:
        print("Google Sheet is empty.")
        return

    current = now_cairo()
    print(f"Current Cairo time: {current.isoformat()}")

    due_rows: list[tuple[int, dict[str, str]]] = []
    failed_rows: list[tuple[int, dict[str, str]]] = []
    approved_rows: list[tuple[int, dict[str, str]]] = []

    for index, raw_row in enumerate(values[1:], start=2):
        row = row_to_dict(raw_row)
        try:
            if _is_due(row, current):
                due_rows.append((index, row))
            elif str(row.get("الحالة", "")).strip().upper() == "APPROVED":
                approved_rows.append((index, row))
            elif _failed_retry(row, current):
                failed_rows.append((index, row))
        except Exception as exc:
            update_row(service, config["sheet_id"], sheet_name, index, {
                "الحالة": "FAILED",
                "آخر خطأ": str(exc),
                "وقت آخر تشغيل": current.isoformat(),
            })

    # Priority: the scheduled post first. Then approved exception items. Then failed backlog.
    candidate = (due_rows or approved_rows or failed_rows)
    if not candidate:
        print("No content is due right now.")
        return

    row_number, row = candidate[0]
    process_row(
        service=service,
        config=config,
        sheet_name=sheet_name,
        row_number=row_number,
        row=row,
        current=current,
    )


if __name__ == "__main__":
    try:
        main()
    except ConfigError as exc:
        print(f"CONFIGURATION ERROR: {exc}")
        raise SystemExit(2)
