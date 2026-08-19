from __future__ import annotations

import os
import traceback
from pathlib import Path

from config import ConfigError, load_config

from facebook_publisher import (
    FacebookPublishError,
    add_comment as facebook_add_comment,
    like_post as facebook_like_post,
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


def github_raw_url(
    relative_path: str,
) -> str:

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
    sheet_name,
    row_number,
    row,
    current,
):

    topic = (
        row.get(
            "الموضوع",
            "",
        )
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
            "الحالة":
                "PROCESSING",
            "Facebook Status":
                "PROCESSING",
            "آخر خطأ":
                "",
            "وقت آخر تشغيل":
                current.isoformat(),
        },
    )

    try:

        # ======================================================
        # 1. CONTENT GENERATION
        # ======================================================

        print(
            "Generating legal content..."
        )

        result = generate_post(
            api_key=config[
                "gemini_api_key"
            ],
            model=config[
                "gemini_model"
            ],
            topic=topic,
            legal_sources=row.get(
                "المصادر القانونية",
                "",
            ),
            previous_context="",
        )

        post = (
            result.get(
                "post",
                "",
            )
            or ""
        ).strip()

        image_brief = (
            result.get(
                "image_brief",
                "",
            )
            or ""
        ).strip()

        review_level = (
            result.get(
                "review_level",
                "REVIEW",
            )
            or "REVIEW"
        ).upper()

        review_flags = result.get(
            "review_flags",
            [],
        )

        review_text = " | ".join(
            str(item).strip()
            for item in review_flags
            if str(item).strip()
        )

        print(
            f"Legal review level: "
            f"{review_level}"
        )

        if review_text:
            print(
                f"Legal review notes: "
                f"{review_text}"
            )

        if not post:
            raise RuntimeError(
                "Gemini returned an empty post."
            )

        if not image_brief:
            raise RuntimeError(
                "Gemini returned an empty image brief."
            )

        # ======================================================
        # BLOCK = STOP
        # REVIEW = CONTINUE
        # CLEAR = CONTINUE
        # ======================================================

        if review_level == "BLOCK":

            print(
                "CONTENT BLOCKED: "
                "manual legal review is required."
            )

            update_row(
                service,
                config["sheet_id"],
                sheet_name,
                row_number,
                {
                    "الحالة":
                        "NEEDS_REVIEW",

                    "آخر خطأ":
                        review_text
                        or "Legal review required.",

                    "وقت آخر تشغيل":
                        current.isoformat(),
                },
            )

            return

        # ======================================================
        # 2. IMAGE GENERATION
        # ======================================================

        raw_id = (
            row.get(
                "ID",
                "",
            )
            or f"row-{row_number}"
        ).strip()

        safe_id = "".join(
            char
            if char.isalnum()
            or char in "-_"
            else "_"
            for char in raw_id
        )

        image_path = (
            GENERATED_DIR
            / f"{safe_id}.jpg"
        )

        print(
            "Generating real AI image with Cloudflare..."
        )

        create_legal_image(
            topic=topic,
            image_brief=image_brief,
            output_path=str(
                image_path
            ),
            cloudflare_account_id=
                config[
                    "cloudflare_account_id"
                ],
            cloudflare_api_token=
                config[
                    "cloudflare_api_token"
                ],
        )

        image_url = github_raw_url(
            str(image_path)
            .replace(
                "\\",
                "/",
            )
        )

        generation_status = (
            "READY_FOR_SOCIAL_PUBLISH"
        )

        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            {
                "الحالة":
                    generation_status,

                "المحتوى":
                    post,

                "وصف الصورة":
                    image_brief,

                "رابط الصورة":
                    image_url,

                "وقت آخر تشغيل":
                    current.isoformat(),
            },
        )

        print(
            f"Generated image: "
            f"{image_path}"
        )

        # ======================================================
        # 3. FACEBOOK
        # ======================================================

        print(
            "Publishing image + caption "
            "to Facebook..."
        )

        facebook = publish_photo(
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
            facebook[
                "post_id"
            ]
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
            },
        )

        print(
            "Facebook publish succeeded: "
            f"{facebook_post_id}"
        )

        # ======================================================
        # 4. FACEBOOK COMMENT
        # ======================================================

        facebook_comment = (
            facebook_add_comment(
                post_id=
                    facebook_post_id,

                page_access_token=
                    config[
                        "facebook_page_access_token"
                    ],

                graph_version=
                    config[
                        "facebook_graph_version"
                    ],

                message=(
                    "لو عندك موقف قانوني مشابه، "
                    "اكتب سؤالك في التعليقات "
                    "وخلينا نوضح لك حقك."
                ),
            )
        )

        print(
            "Facebook comment: "
            f"{facebook_comment['status']}"
        )

        # ======================================================
        # 5. FACEBOOK LIKE
        # ======================================================

        facebook_like = (
            facebook_like_post(
                post_id=
                    facebook_post_id,

                page_access_token=
                    config[
                        "facebook_page_access_token"
                    ],

                graph_version=
                    config[
                        "facebook_graph_version"
                    ],
            )
        )

        print(
            "Facebook like: "
            f"{facebook_like['status']}"
        )

        # ======================================================
        # 6. LINKEDIN
        # ======================================================

        print(
            "Publishing to LinkedIn..."
        )

        linkedin_access_token = (
            config[
                "linkedin_access_token"
            ]
        )

        linkedin_author_urn = (
            config.get(
                "linkedin_author_urn",
                "",
            )
            or ""
        ).strip()

        try:

            if not linkedin_author_urn:

                print(
                    "Resolving LinkedIn "
                    "member identity..."
                )

                linkedin_author_urn = (
                    resolve_member_urn(
                        linkedin_access_token
                    )
                )

                print(
                    "LinkedIn member identity "
                    "resolved."
                )

            linkedin = (
                publish_to_linkedin(
                    token=
                        linkedin_access_token,

                    author_urn=
                        linkedin_author_urn,

                    image_path=
                        image_path,

                    commentary=
                        post,

                    first_comment=(
                        "لو عندك موقف قانوني مشابه، "
                        "اكتب سؤالك في التعليقات."
                    ),
                )
            )

            print(
                "LinkedIn post succeeded: "
                f"{linkedin['post_urn']}"
            )

            print(
                "LinkedIn comment: "
                f"{linkedin['comment']['status']}"
            )

            print(
                "LinkedIn like: "
                f"{linkedin['like']['status']}"
            )

            update_row(
                service,
                config["sheet_id"],
                sheet_name,
                row_number,
                {
                    "LinkedIn Status":
                        "PUBLISHED",

                    "LinkedIn Post ID":
                        linkedin[
                            "post_urn"
                        ],

                    "LinkedIn Comment Status":
                        linkedin[
                            "comment"
                        ]["status"],

                    "LinkedIn Like Status":
                        linkedin[
                            "like"
                        ]["status"],
                },
            )

        except LinkedInPublishError as exc:

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
        # 7. FINAL STATE
        # ======================================================

        update_data = {
            "الحالة":
                "PUBLISHED",

            "Facebook Status":
                "PUBLISHED",

            "Facebook Post ID":
                facebook_post_id,

            "وقت آخر تشغيل":
                current.isoformat(),
        }

        if review_level == "REVIEW":

            print(
                "Published with legal review note: "
                f"{review_text}"
            )

        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            update_data,
        )

        print(
            "Full social publishing pipeline "
            "completed successfully."
        )

    except (
        FacebookPublishError,
        ImageGenerationError,
    ) as exc:

        error_text = (
            f"{type(exc).__name__}: "
            f"{exc}"
        )

        print(
            "PUBLISHING/IMAGE ERROR"
        )

        print(
            error_text
        )

        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            {
                "الحالة":
                    "FAILED",

                "Facebook Status":
                    "FAILED",

                "آخر خطأ":
                    error_text,

                "وقت آخر تشغيل":
                    current.isoformat(),
            },
        )

        raise

    except Exception as exc:

        error_text = (
            f"{type(exc).__name__}: "
            f"{exc}"
        )

        print(
            "PROCESSING ERROR"
        )

        print(
            error_text
        )

        traceback.print_exc()

        update_row(
            service,
            config["sheet_id"],
            sheet_name,
            row_number,
            {
                "الحالة":
                    "FAILED",

                "آخر خطأ":
                    error_text,

                "وقت آخر تشغيل":
                    current.isoformat(),
            },
        )

        raise


def main():

    print(
        "=" * 70
    )

    print(
        "KHYRAT LEGAL CONTENT ENGINE - "
        "FULL SOCIAL PIPELINE"
    )

    print(
        "=" * 70
    )

    config = load_config()

    service = create_service(
        config[
            "service_account_info"
        ]
    )

    sheet_name = (
        sheet_name_from_range(
            config["sheet_range"]
        )
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

    if headers[
        :len(HEADERS)
    ] != HEADERS:

        raise RuntimeError(
            "Sheet headers do not match "
            "expected template."
        )

    current = now_cairo()

    print(
        f"Current Cairo time: "
        f"{current.isoformat()}"
    )

    due_rows = []

    for index, raw_row in enumerate(
        values[1:],
        start=2,
    ):

        row = row_to_dict(
            raw_row
        )

        try:

            if is_due(
                row,
                current,
            ):

                due_rows.append(
                    (
                        index,
                        row,
                    )
                )

        except Exception as exc:

            update_row(
                service,
                config["sheet_id"],
                sheet_name,
                index,
                {
                    "الحالة":
                        "FAILED",

                    "آخر خطأ":
                        str(exc),

                    "وقت آخر تشغيل":
                        current.isoformat(),
                },
            )

    if not due_rows:

        print(
            "No content is due right now."
        )

        return

    row_number, row = (
        due_rows[0]
    )

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
