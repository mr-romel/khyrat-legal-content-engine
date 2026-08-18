from pathlib import Path
import os
import traceback

from config import load_config, ConfigError
from sheets import (
    HEADERS,
    create_service,
    get_values,
    row_to_dict,
    update_row,
    ensure_headers,
)
from gemini import generate_post
from image_generator import create_legal_image
from facebook_publisher import FacebookPublishError, publish_photo
from utils import now_cairo, is_due, sheet_name_from_range


GENERATED_DIR = Path("generated")


def github_raw_url(relative_path: str) -> str:
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    branch = os.getenv("GITHUB_REF_NAME", "main").strip() or "main"

    if not repository:
        return ""

    normalized = relative_path.replace("\\", "/").lstrip("/")
    return (
        f"https://raw.githubusercontent.com/"
        f"{repository}/{branch}/{normalized}"
    )


def main():
    print("=" * 70)
    print("KHYRAT LEGAL CONTENT ENGINE - FACEBOOK PUBLISHING")
    print("=" * 70)
    config = load_config()
    service = create_service(config["service_account_info"])

    sheet_name = sheet_name_from_range(config["sheet_range"])
    ensure_headers(service, config["sheet_id"], sheet_name)

    values = get_values(
        service,
        config["sheet_id"],
        f"{sheet_name}!A:Q",
    )

    if not values:
        print("Google Sheet is empty. Add at least one content row.")
        return

    headers = values[0]
    if headers[: len(HEADERS)] != HEADERS:
        raise RuntimeError(
            "Sheet headers do not match the expected template. "
            "Replace row 1 with the template headers."
        )

    rows = []
    for index, raw_row in enumerate(values[1:], start=2):
        row = row_to_dict(raw_row)
        rows.append((index, row))

    current = now_cairo()
    print(f"Current Cairo time: {current.isoformat()}")
    due_rows = []
    for row_number, row in rows:
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
            print(f"Row {row_number} rejected: {exc}")

    if not due_rows:
        print("No content is due right now.")
        return

    # MVP safety: one item per run.
    row_number, row = due_rows[0]
    topic = row.get("الموضوع", "").strip()

    if not topic:
        raise RuntimeError(
            f"Row {row_number} has no topic in 'الموضوع'."
        )

    print(f"Processing row {row_number}: {topic}")
    update_row(
        service,
        config["sheet_id"],
        sheet_name,
        row_number,
        {
            "الحالة": "PROCESSING",
            "Facebook Status": "PROCESSING",
            "آخر خطأ": "",
            "وقت آخر تشغيل": current.isoformat(),
        },
    )

    try:
        result = generate_post(
            api_key=config["gemini_api_key"],
            model=config["gemini_model"],
            topic=topic,
            legal_sources=row.get("المصادر القانونية", ""),
            previous_context="",
        )
        post = result["post"].strip()
        image_brief = result["image_brief"].strip()

        safe_id = (row.get("ID") or f"row-{row_number}").strip()
        safe_id = "".join(
            ch if ch.isalnum() or ch in "-_" else "_"
            for ch in safe_id
        )

        image_path = GENERATED_DIR / f"{safe_id}.jpg"

        create_legal_image(
            topic=topic,
            image_brief=image_brief,
            output_path=str(image_path),
        )

        relative_image_path = str(image_path).replace("\\", "/")
        image_url = github_raw_url(relative_image_path)

        review_flags = result.get("review_flags", [])
        review_flags_text = " | ".join(
            str(item).strip() for item in review_flags if str(item).strip()
        )

        sources = result.get("legal_sources_used", [])
        sources_text = " | ".join(
            str(item).strip() for item in sources if str(item).strip()
        )

        status = "READY_FOR_SOCIAL_PUBLISH"
        if review_flags_text:
            status = "NEEDS_REVIEW"

        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            {
                "الحالة": status,
                "المحتوى": post,
                "وصف الصورة": image_brief,
                "رابط الصورة": image_url,
                "Facebook Status": "READY" if not review_flags_text else "BLOCKED",
                "المصادر القانونية": sources_text or row.get("المصادر القانونية", ""),
                "آخر خطأ": review_flags_text,
                "وقت آخر تشغيل": current.isoformat(),
            },
        )

        print(f"Generated image: {image_path}")
        print(f"Image URL: {image_url}")
        print(f"Generation status: {status}")

        # Never publish automatically when legal review is required.
        if review_flags_text:
            print("Facebook publish skipped: item requires legal review.")
            return

        facebook_result = publish_photo(
            page_id=config["facebook_page_id"],
            page_access_token=config["facebook_page_access_token"],
            graph_version=config["facebook_graph_version"],
            image_path=image_path,
            caption=post,
        )

        facebook_post_id = facebook_result["post_id"]

        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            {
                "الحالة": "PUBLISHED",
                "Facebook Status": "PUBLISHED",
                "Facebook Post ID": facebook_post_id,
                "آخر خطأ": "",
                "وقت آخر تشغيل": current.isoformat(),
            },
        )

        print(f"Facebook publish succeeded: {facebook_post_id}")
        print("Facebook publishing stage completed successfully.")

    except FacebookPublishError as exc:
        error_text = f"{type(exc).__name__}: {exc}"
        print("FACEBOOK PUBLISH ERROR")
        print(error_text)
        traceback.print_exc()
        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            {
                "الحالة": "FAILED",
                "Facebook Status": "FAILED",
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
                "Facebook Status": "FAILED",
                "آخر خطأ": error_text,
                "وقت آخر تشغيل": current.isoformat(),
            },
        )

        raise


if __name__ == "__main__":
    try:
        main()
    except ConfigError as exc:
        print(f"CONFIGURATION ERROR: {exc}")
        raise SystemExit(2)
