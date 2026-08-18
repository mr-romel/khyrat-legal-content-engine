from __future__ import annotations

import os
import traceback
from pathlib import Path

from config import ConfigError, load_config
from facebook_publisher import (
    FacebookPublishError,
    create_first_comment,
    like_post,
    publish_photo,
)
from gemini import generate_post
from image_generator import ImageGenerationError, create_legal_image
from linkedin_publisher import LinkedInPublishError, create_comment as li_create_comment, like_post as li_like_post, publish_image_post
from sheets import HEADERS, create_service, ensure_headers, get_values, row_to_dict, update_row
from utils import is_due, now_cairo, sheet_name_from_range

GENERATED_DIR = Path("generated")


def github_raw_url(relative_path: str) -> str:
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    branch = os.getenv("GITHUB_REF_NAME", "main").strip() or "main"
    if not repository:
        return ""
    normalized = relative_path.replace("\\", "/").lstrip("/")
    return f"https://raw.githubusercontent.com/{repository}/{branch}/{normalized}"


def _build_first_comment(topic: str) -> str:
    return (
        f"لو عندك موقف مشابه في موضوع «{topic}»، اكتب سؤالك في التعليقات، "
        "وشارك البوست مع شخص ممكن يهمه يعرف حقه."
    )


def process_row(*, service, config: dict, sheet_name: str, row_number: int, row: dict, current) -> None:
    topic = (row.get("الموضوع", "") or "").strip()
    if not topic:
        raise RuntimeError(f"Row {row_number} has no topic.")

    print(f"Processing row {row_number}: {topic}")

    update_row(
        service,
        config["sheet_id"],
        sheet_name,
        row_number,
        {
            "الحالة": "PROCESSING",
            "Facebook Status": "PROCESSING",
            "LinkedIn Status": "PROCESSING",
            "آخر خطأ": "",
            "وقت آخر تشغيل": current.isoformat(),
        },
    )

    try:
        print("Generating legal content...")
        result = generate_post(
            api_key=config["gemini_api_key"],
            model=config["gemini_model"],
            topic=topic,
            legal_sources=row.get("المصادر القانونية", "") or "",
            previous_context="",
        )

        post = (result.get("post", "") or "").strip()
        image_brief = (result.get("image_brief", "") or "").strip()
        review_flags = result.get("review_flags", [])
        legal_sources_used = result.get("legal_sources_used", [])

        if not post:
            raise RuntimeError("Gemini returned an empty post.")
        if not image_brief:
            raise RuntimeError("Gemini returned an empty image brief.")

        if not isinstance(review_flags, list):
            review_flags = [str(review_flags)]
        if not isinstance(legal_sources_used, list):
            legal_sources_used = [str(legal_sources_used)]

        review_flags_text = " | ".join(
            str(item).strip() for item in review_flags if str(item).strip()
        )
        sources_text = " | ".join(
            str(item).strip() for item in legal_sources_used if str(item).strip()
        )

        raw_id = (row.get("ID", "") or f"row-{row_number}").strip()
        safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in raw_id)
        image_path = GENERATED_DIR / f"{safe_id}.jpg"

        print("Generating real AI image with Cloudflare...")
        create_legal_image(
            topic=topic,
            image_brief=image_brief,
            output_path=str(image_path),
            cloudflare_account_id=config["cloudflare_account_id"],
            cloudflare_api_token=config["cloudflare_api_token"],
        )

        image_url = github_raw_url(str(image_path).replace("\\", "/"))
        generation_status = "NEEDS_REVIEW" if review_flags_text else "READY_FOR_SOCIAL_PUBLISH"

        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            {
                "الحالة": generation_status,
                "المحتوى": post,
                "وصف الصورة": image_brief,
                "رابط الصورة": image_url,
                "المصادر القانونية": sources_text or row.get("المصادر القانونية", ""),
                "آخر خطأ": review_flags_text,
                "وقت آخر تشغيل": current.isoformat(),
            },
        )

        print(f"Generated image: {image_path}")
        print(f"Image URL: {image_url}")
        print(f"Generation status: {generation_status}")

        if review_flags_text:
            update_row(
                service,
                config["sheet_id"],
                sheet_name,
                row_number,
                {
                    "Facebook Status": "BLOCKED",
                    "LinkedIn Status": "BLOCKED",
                },
            )
            print("Publishing skipped: legal review is required.")
            return

        # --------------------------------------------------------
        # FACEBOOK
        # --------------------------------------------------------
        fb_post_id = (row.get("Facebook Post ID", "") or "").strip()
        fb_comment_id = (row.get("Facebook Comment ID", "") or "").strip()

        if not fb_post_id:
            print("Publishing image + caption to Facebook...")
            fb_result = publish_photo(
                page_id=config["facebook_page_id"],
                page_access_token=config["facebook_page_access_token"],
                graph_version=config["facebook_graph_version"],
                image_path=image_path,
                caption=post,
            )
            fb_post_id = fb_result["post_id"]
        else:
            print(f"Facebook post already recorded: {fb_post_id}")

        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            {
                "Facebook Status": "PUBLISHED",
                "Facebook Post ID": fb_post_id,
            },
        )

        # Best-effort engagement: never undo a successful publish.
        comment_status = "SKIPPED"
        like_status = "SKIPPED"

        try:
            if not fb_comment_id:
                fb_comment_id = create_first_comment(
                    post_id=fb_post_id,
                    page_access_token=config["facebook_page_access_token"],
                    graph_version=config["facebook_graph_version"],
                    message=_build_first_comment(topic),
                )
            comment_status = "PUBLISHED"
        except Exception as exc:
            comment_status = f"FAILED: {exc}"
            print(f"Facebook first comment warning: {exc}")

        try:
            like_post(
                post_id=fb_post_id,
                page_access_token=config["facebook_page_access_token"],
                graph_version=config["facebook_graph_version"],
            )
            like_status = "LIKED"
        except Exception as exc:
            like_status = f"FAILED: {exc}"
            print(f"Facebook like warning: {exc}")

        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            {
                "Facebook Comment Status": comment_status,
                "Facebook Comment ID": fb_comment_id,
                "Facebook Like Status": like_status,
            },
        )

        print(f"Facebook publish succeeded: {fb_post_id}")
        print(f"Facebook comment: {comment_status}")
        print(f"Facebook like: {like_status}")

        # --------------------------------------------------------
        # LINKEDIN
        # --------------------------------------------------------
        if not config["linkedin_enabled"]:
            print("LinkedIn: not configured yet; Facebook stage remains successful.")
            update_row(
                service,
                config["sheet_id"],
                sheet_name,
                row_number,
                {"LinkedIn Status": "NOT_CONFIGURED"},
            )
        else:
            li_post_id = (row.get("LinkedIn Post ID", "") or "").strip()
            if not li_post_id:
                print("Publishing image + caption to LinkedIn...")
                li_result = publish_image_post(
                    token=config["linkedin_access_token"],
                    author_urn=config["linkedin_author_urn"],
                    image_path=image_path,
                    commentary=post,
                    version=config["linkedin_version"],
                )
                li_post_id = li_result["post_urn"]
                li_image_id = li_result["image_urn"]
                update_row(
                    service,
                    config["sheet_id"],
                    sheet_name,
                    row_number,
                    {
                        "LinkedIn Status": "PUBLISHED",
                        "LinkedIn Post ID": li_post_id,
                        "LinkedIn Image ID": li_image_id,
                    },
                )

                li_comment_status = "SKIPPED"
                li_like_status = "SKIPPED"
                try:
                    li_create_comment(
                        token=config["linkedin_access_token"],
                        actor_urn=config["linkedin_author_urn"],
                        post_urn=li_post_id,
                        message=_build_first_comment(topic),
                        version=config["linkedin_version"],
                    )
                    li_comment_status = "PUBLISHED"
                except Exception as exc:
                    li_comment_status = f"FAILED: {exc}"
                    print(f"LinkedIn comment warning: {exc}")

                try:
                    li_like_post(
                        token=config["linkedin_access_token"],
                        actor_urn=config["linkedin_author_urn"],
                        post_urn=li_post_id,
                        version=config["linkedin_version"],
                    )
                    li_like_status = "LIKED"
                except Exception as exc:
                    li_like_status = f"FAILED: {exc}"
                    print(f"LinkedIn like warning: {exc}")

                update_row(
                    service,
                    config["sheet_id"],
                    sheet_name,
                    row_number,
                    {
                        "LinkedIn Status": "PUBLISHED",
                    },
                )
                print(f"LinkedIn publish succeeded: {li_post_id}")
                print(f"LinkedIn comment: {li_comment_status}")
                print(f"LinkedIn like: {li_like_status}")
            else:
                print(f"LinkedIn post already recorded: {li_post_id}")

        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            {
                "الحالة": "PUBLISHED",
                "آخر خطأ": "",
                "وقت آخر تشغيل": current.isoformat(),
            },
        )

        print("Full social publishing pipeline completed successfully.")

    except (FacebookPublishError, ImageGenerationError, LinkedInPublishError) as exc:
        error_text = f"{type(exc).__name__}: {exc}"
        print("PIPELINE ERROR")
        print(error_text)
        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            {
                "الحالة": "FAILED",
                "آخر خطأ": error_text,
                "وقت آخر تشغيل": current.isoformat(),
            },
        )
        raise
    except Exception as exc:
        error_text = f"{type(exc).__name__}: {exc}"
        print("PROCESSING ERROR")
        print(error_text)
        traceback.print_exc()
        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            {
                "الحالة": "FAILED",
                "آخر خطأ": error_text,
                "وقت آخر تشغيل": current.isoformat(),
            },
        )
        raise


def main() -> None:
    print("=" * 70)
    print("KHYRAT LEGAL CONTENT ENGINE - FULL SOCIAL PIPELINE")
    print("=" * 70)

    config = load_config()
    service = create_service(config["service_account_info"])
    sheet_name = sheet_name_from_range(config["sheet_range"])
    ensure_headers(service, config["sheet_id"], sheet_name)

    values = get_values(
        service,
        config["sheet_id"],
        f"{sheet_name}!A:U",
    )

    if not values:
        print("Google Sheet is empty.")
        return

    headers = values[0]
    if headers[: len(HEADERS)] != HEADERS:
        raise RuntimeError(
            "Sheet headers do not match the current template."
        )

    current = now_cairo()
    print(f"Current Cairo time: {current.isoformat()}")

    due_rows = []
    for row_number, raw_row in enumerate(values[1:], start=2):
        row = row_to_dict(raw_row)
        try:
            if is_due(row, current):
                due_rows.append((row_number, row))
        except Exception as exc:
            update_row(
                service,
                config["sheet_id"],
                sheet_name,
                row_number,
                {
                    "الحالة": "FAILED",
                    "آخر خطأ": str(exc),
                    "وقت آخر تشغيل": current.isoformat(),
                },
            )

    if not due_rows:
        print("No content is due right now.")
        return

    # Still one scheduled item per invocation, but all social actions for that
    # item happen inside the same run.
    row_number, row = due_rows[0]
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
