from __future__ import annotations

import os

from comment_engine import generate_comments
from config import load_config
from gemini_runtime import generate_post
from sheets import create_service, get_values, row_to_dict


def main() -> None:
    print("=" * 70)
    print("KHYRAT LEGAL CONTENT ENGINE - SAFE COMMENT DRY RUN")
    print("=" * 70)
    print("SOCIAL PUBLISHING: DISABLED")
    print("GOOGLE SHEETS WRITE: DISABLED")
    print("POSTBANK CREATION/UPDATE: DISABLED")
    print("FACEBOOK: NO WRITE")
    print("LINKEDIN: NO WRITE")
    print("LIKES: NO WRITE")
    print("COMMENTS: NO WRITE")
    print("IMAGE GENERATION: DISABLED")
    print("AI CONTENT/COMMENT GENERATION: ENABLED")
    print("GEMINI: RETRY + FALLBACK MODEL ENABLED")
    print("=" * 70)

    if os.getenv("KHYRAT_DRY_RUN", "").strip().lower() not in {"1", "true", "yes", "on"}:
        raise RuntimeError("Safe dry run requires KHYRAT_DRY_RUN=true.")

    config = load_config()
    service = create_service(config["service_account_info"])
    values = get_values(service, config["sheet_id"], config["sheet_range"])

    if not values or len(values) < 2:
        raise RuntimeError("Google Sheet contains no usable content rows for the safe test.")

    rows = [row_to_dict(row) for row in values[1:]]
    selected = None
    for index, row in enumerate(rows, start=2):
        topic = str(row.get("الموضوع", "")).strip()
        if topic:
            selected = (index, row)
            break

    if selected is None:
        raise RuntimeError("No row with a topic was found for the safe test.")

    row_number, row = selected
    topic = str(row.get("الموضوع", "")).strip()
    legal_sources = str(row.get("المصادر القانونية", "")).strip()
    existing_post = str(row.get("المحتوى", "")).strip()

    print(f"Selected test row: {row_number}")
    print(f"Test topic: {topic}")

    if existing_post:
        post = existing_post
        print("Using existing post content from the selected row; no Sheet write will occur.")
    else:
        print("Generating temporary post content with resilient Gemini runtime...")
        result = generate_post(
            api_key=config["gemini_api_key"],
            model=config["gemini_model"],
            topic=topic,
            legal_sources=legal_sources,
            previous_context="Safe dry-run: no PostBank access is performed.",
        )
        post = str(result.get("post", "")).strip()
        if not post:
            raise RuntimeError("Gemini returned empty temporary post content.")

    print("Generating temporary Facebook/LinkedIn comment packages...")
    comments = generate_comments(
        api_key=config["gemini_api_key"],
        model=config["gemini_model"],
        topic=topic,
        post=post,
        legal_sources=legal_sources,
    )

    facebook_comments = comments.get("facebook_comments", [])
    linkedin_comments = comments.get("linkedin_comments", [])

    if len(facebook_comments) != 5 or len(linkedin_comments) != 5:
        raise RuntimeError(
            "Safe dry run failed: expected exactly 5 comments per platform."
        )

    print(
        "SAFE DRY RUN result: "
        f"Facebook comments={len(facebook_comments)}/5 | "
        f"LinkedIn comments={len(linkedin_comments)}/5"
    )
    print("SAFE DRY RUN completed successfully.")
    print("No Facebook/LinkedIn API write was attempted.")
    print("No Google Sheet write was attempted.")
    print("No PostBank sheet was created or modified.")
    print("No Cloudflare image generation was attempted.")


if __name__ == "__main__":
    main()
