from __future__ import annotations

import os
import traceback
from pathlib import Path

from config import ConfigError, load_config
from facebook_publisher import (
    FacebookPublishError,
    publish_photo,
)
from gemini import generate_post
from image_generator import (
    ImageGenerationError,
    create_legal_image,
)
from linkedin_publisher import (
    LinkedInPublishError,
    publish_to_linkedin,
    resolve_member_urn,
)
from sheets import (
    HEADERS,
    create_service,
    ensure_headers,
    get_values,
    row_to_dict,
    update_row,
)
from utils import (
    is_due,
    now_cairo,
    sheet_name_from_range,
)


GENERATED_DIR = Path("generated")


def github_raw_url(relative_path: str) -> str:
    repository = os.getenv(
        "GITHUB_REPOSITORY",
        "",
    ).strip()

    branch = (
        os.getenv(
            "GITHUB_REF_NAME",
            "main",
        ).strip()
        or "main"
    )

    if not repository:
        return ""

    normalized = (
        relative_path
        .replace("\\", "/")
        .lstrip("/")
    )

    return (
        "https://raw.githubusercontent.com/"
        f"{repository}/{branch}/{normalized}"
    )


def process_row(
    *,
    service,
    config,
    sheet_name: str,
    row_number: int,
    row: dict,
    current,
) -> None:

    topic = (
        row.get("الموضوع", "")
        or ""
    ).strip()

    if not topic:
        raise RuntimeError(
            f"Row {row_number} has no topic."
        )

    print(
        f"Processing row {row_number}: {topic}"
    )

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
        # ======================================================
        # 1. CONTENT
        # ======================================================

        print("Generating legal content...")

        result = generate_post(
            api_key=config["gemini_api_key"],
            model=config["gemini_model"],
            topic=topic,
            legal_sources=(
                row.get(
                    "المصادر القانونية",
                    "",
                )
                or ""
            ),
            previous_context="",
        )

        post = (
            result.get("post", "")
            or ""
        ).strip()

        image_brief = (
            result.get("image_brief", "")
            or ""
        ).strip()

        review_flags = result.get(
            "review_flags",
            [],
        )

        legal_sources_used = result.get(
            "legal_sources_used",
            [],
        )

        if not post:
            raise RuntimeError(
                "Gemini returned an empty post."
            )

        if not image_brief:
            raise RuntimeError(
                "Gemini returned an empty image brief."
            )

        if not isinstance(
            review_flags,
            list,
        ):
            review_flags = [str(review_flags)]

        if not isinstance(
            legal_sources_used,
            list,
        ):
            legal_sources_used = [
                str(legal_sources_used)
            ]

        review_flags_text = " | ".join(
            str(item).strip()
            for item in review_flags
            if str(item).strip()
        )

        sources_text = " | ".join(
            str(item).strip()
            for item in legal_sources_used
            if str(item).strip()
        )

        # ======================================================
        # 2. IMAGE FILE
        # ======================================================

        raw_id = (
            row.get("ID", "")
            or f"row-{row_number}"
        ).strip()

        safe_id = "".join(
            ch
            if ch.isalnum()
            or ch in "-_"
            else "_"
            for ch in raw_id
        )

        image_path = (
            GENERATED_DIR
            / f"{safe_id}.jpg"
        )

        # ======================================================
        # 3. IMAGE
        # ======================================================

        print(
            "Generating real AI image with Cloudflare..."
        )

        create_legal_image(
            topic=topic,
            image_brief=image_brief,
            output_path=str(image_path),
            cloudflare_account_id=config[
                "cloudflare_account_id"
            ],
            cloudflare_api_token=config[
                "cloudflare_api_token"
            ],
        )

        image_url = github_raw_url(
            str(image_path).replace(
                "\\",
                "/",
            )
        )

        generation_status = (
            "READY_FOR_SOCIAL_PUBLISH"
            if not review_flags_text
            else "NEEDS_REVIEW"
        )

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
                "Facebook Status": (
                    "READY"
                    if not review_flags_text
                    else "BLOCKED"
                ),
                "المصادر القانونية": (
                    sources_text
                    or row.get(
                        "المصادر القانونية",
                        "",
                    )
                ),
                "آخر خطأ": review_flags_text,
                "وقت آخر تشغيل":
                    current.isoformat(),
            },
        )

        print(
            f"Generated image: {image_path}"
        )

        print(
            f"Image URL: {image_url}"
        )

        print(
            f"Generation status: {generation_status}"
        )

        if review_flags_text:
            print(
                "Manual legal review required; "
                "social publishing skipped."
            )
            return

        # ======================================================
        # 4. FACEBOOK
        # ======================================================

        print(
            "Publishing image + caption to Facebook..."
        )

        facebook_result = publish_photo(
            page_id=config[
                "facebook_page_id"
            ],
            page_access_token=config[
                "facebook_page_access_token"
            ],
            graph_version=config[
                "facebook_graph_version"
            ],
            image_path=image_path,
            caption=post,
        )

        facebook_post_id = (
            facebook_result.get(
                "post_id",
                "",
            )
            or ""
        ).strip()

        if not facebook_post_id:
            raise FacebookPublishError(
                "Facebook returned no Post ID."
            )

        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            {
                "Facebook Status":
                    "PUBLISHED",
                "Facebook Post ID":
                    facebook_post_id,
                "آخر خطأ": "",
            },
        )

        print(
            "Facebook publish succeeded: "
            f"{facebook_post_id}"
        )

        # ======================================================
        # 5. LINKEDIN
        # ======================================================

        linkedin_status = "FAILED"
        linkedin_post_id = ""
        linkedin_comment_status = ""
        linkedin_like_status = ""

        print(
            "Publishing to LinkedIn..."
        )

        try:
            author_urn = resolve_member_urn(
                config[
                    "linkedin_access_token"
                ]
            )

            linkedin_result = publish_to_linkedin(
                access_token=config[
                    "linkedin_access_token"
                ],
                author_urn=author_urn,
                image_path=image_path,
                commentary=post,
                first_comment=(
                    "لو عندك موقف قانوني مشابه، "
                    "اكتب سؤالك في التعليقات."
                ),
            )

            linkedin_status = "PUBLISHED"

            linkedin_post_id = (
                linkedin_result.get(
                    "post_urn",
                    "",
                )
                or ""
            )

            linkedin_comment_status = (
                linkedin_result
                .get(
                    "comment",
                    {},
                )
                .get(
                    "status",
                    "",
                )
            )

            linkedin_like_status = (
                linkedin_result
                .get(
                    "like",
                    {},
                )
                .get(
                    "status",
                    "",
                )
            )

            print(
                "LinkedIn post succeeded: "
                f"{linkedin_post_id}"
            )

            print(
                "LinkedIn comment: "
                f"{linkedin_comment_status}"
            )

            print(
                "LinkedIn like: "
                f"{linkedin_like_status}"
            )

        except LinkedInPublishError as exc:
            linkedin_status = "FAILED"

            print(
                "LinkedIn publishing failed: "
                f"{exc}"
            )

            update_row(
                service,
                config["sheet_id"],
                sheet_name,
                row_number,
                {
                    "LinkedIn Status":
                        "FAILED",
                    "آخر خطأ":
                        f"LinkedIn: {exc}",
                },
            )

        # ======================================================
        # 6. FINAL SHEET STATE
        # ======================================================

        final_update = {
            "الحالة": "PUBLISHED",
            "Facebook Status":
                "PUBLISHED",
            "Facebook Post ID":
                facebook_post_id,
            "وقت آخر تشغيل":
                current.isoformat(),
        }

        if linkedin_status == "PUBLISHED":
            final_update["LinkedIn Status"] = "PUBLISHED"
            final_update["LinkedIn Post ID"] = (
                linkedin_post_id
            )
            final_update[
                "LinkedIn Comment Status"
            ] = linkedin_comment_status
            final_update[
                "LinkedIn Like Status"
            ] = linkedin_like_status
        else:
            final_update[
                "LinkedIn Status"
            ] = "FAILED"

        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            final_update,
        )

        print(
            "Full social publishing pipeline completed."
        )

    except (
        FacebookPublishError,
        ImageGenerationError,
    ) as exc:

        error_text = (
            f"{type(exc).__name__}: {exc}"
        )

        print(
            "PUBLISHING/IMAGE ERROR"
        )

        print(error_text)

        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            {
                "الحالة": "FAILED",
                "Facebook Status": "FAILED",
                "آخر خطأ": error_text,
                "وقت آخر تشغيل":
                    current.isoformat(),
            },
        )

        raise

    except Exception as exc:

        error_text = (
            f"{type(exc).__name__}: {exc}"
        )

        print(
            "PROCESSING ERROR"
        )

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
                "وقت آخر تشغيل":
                    current.isoformat(),
            },
        )

        raise


def main() -> None:

    print("=" * 70)
    print(
        "KHYRAT LEGAL CONTENT ENGINE - "
        "FULL SOCIAL PIPELINE"
    )
    print("=" * 70)

    config = load_config()

    service = create_service(
        config["service_account_info"]
    )

    sheet_name = sheet_name_from_range(
        config["sheet_range"]
    )

    ensure_headers(
        service,
        config["sheet_id"],
        sheet_name,
    )

    values = get_values(
        service,
        config["sheet_id"],
        f"{sheet_name}!A:U",
    )

    if not values:
        print(
            "Google Sheet is empty."
        )
        return

    headers = values[0]

    if headers[: len(HEADERS)] != HEADERS:
        raise RuntimeError(
            "Sheet headers do not match expected template."
        )

    rows = []

    for index, raw_row in enumerate(
        values[1:],
        start=2,
    ):
        rows.append(
            (
                index,
                row_to_dict(raw_row),
            )
        )

    current = now_cairo()

    print(
        f"Current Cairo time: "
        f"{current.isoformat()}"
    )

    due_rows = []

    for row_number, row in rows:

        try:
            if is_due(
                row,
                current,
            ):
                due_rows.append(
                    (
                        row_number,
                        row,
                    )
                )

        except Exception as exc:
            error_text = str(exc)

            update_row(
                service,
                config["sheet_id"],
                sheet_name,
                row_number,
                {
                    "الحالة": "FAILED",
                    "آخر خطأ": error_text,
                    "وقت آخر تشغيل":
                        current.isoformat(),
                },
            )

    if not due_rows:
        print(
            "No content is due right now."
        )
        return

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
        print(
            f"CONFIGURATION ERROR: {exc}"
        )
        raise SystemExit(2)
