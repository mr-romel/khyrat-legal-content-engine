from __future__ import annotations

import json
import os
import re
import traceback
from difflib import SequenceMatcher
from pathlib import Path

from analytics import log_publication
from comment_engine import generate_comments
from config import load_config
from content_planner import classify
from content_diversity import build_diversity_context
from content_system import choose_visual_concept, infer_audience_persona, record_fingerprint
from editorial_review import review_and_prepare
from facebook_publisher import FacebookPublishError, delete_post as delete_facebook_post, publish_photo, publish_text
from gemini import generate_post
from image_generator import ImageGenerationError, brand_published_image, create_legal_image
from image_qa import ImageQAError, qa_image, summarize_qa
from legal_research import research_legal_topic
from social_content import append_hashtags, sanitize_social_copy, split_hashtags
from linkedin_publisher import LinkedInPublishError, delete_post as delete_linkedin_post, publish_text_to_linkedin, publish_to_linkedin, resolve_member_urn
from post_bank import add_published_post, build_previous_context, get_bank_rows
from sheets import create_service, ensure_headers, get_values, row_to_dict, update_row
from telegram_bot import notify, send_review_request
from utils import now_cairo, parse_date, parse_time, sheet_name_from_range

GENERATED_DIR = Path("generated")

FACEBOOK_COMMENT_LIMIT = 7
LINKEDIN_COMMENT_LIMIT = 7
COMMENT_BACKFILL_LIMIT = 3
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
    contact_cta = (
        "لو محتاج تقييم موقفك القانوني على وقائعك ومستنداتك، ما تعتمدش على المعلومة العامة وحدها.\n"
        "واتساب مباشر: https://wa.me/201022718375\n"
        "صفحة اسأل محمود: https://www.facebook.com/AskMahmoudNow"
    ) if "wa.me/201022718375" not in text else ""
    addition_text = "\n\n".join(additions).strip()
    return text + (("\n\n" + addition_text) if addition_text else "") + (("\n\n" + contact_cta) if contact_cta else "")


def _prepare_editorial_assets(*, config, topic: str, facebook_post: str, legal_sources: str) -> dict:
    comments = generate_comments(api_key=config["gemini_api_key"], model=config["gemini_model"], topic=topic, post=facebook_post, legal_sources=legal_sources)
    target_count = len(comments["facebook_comments"])
    reviewed = review_and_prepare(api_key=config["gemini_api_key"], model=config["gemini_model"], topic=topic, facebook_post=facebook_post, facebook_comments=comments["facebook_comments"][:5], linkedin_comments=comments["linkedin_comments"], legal_sources=legal_sources)
    reviewed_fb = list(reviewed.get("facebook_comments", []))[:target_count]
    reviewed_li = list(reviewed.get("linkedin_comments", []))[:target_count]
    if len(reviewed_fb) < target_count:
        reviewed_fb.extend(comments["facebook_comments"][len(reviewed_fb):target_count])
    if len(reviewed_li) < target_count:
        reviewed_li.extend(comments["linkedin_comments"][len(reviewed_li):target_count])
    reviewed["facebook_comments"] = reviewed_fb[:target_count]
    reviewed["linkedin_comments"] = reviewed_li[:target_count]
    reviewed["facebook_post"] = _ensure_facebook_cta(reviewed["facebook_post"])

    # Shared social-content contract: both platforms always receive the same
    # topic-derived hashtag set while keeping their platform-specific body.
    reviewed["facebook_post"] = append_hashtags(sanitize_social_copy(reviewed["facebook_post"]), topic)
    linkedin_body, _ = split_hashtags(reviewed.get("linkedin_post", ""))
    reviewed["linkedin_post"] = append_hashtags(sanitize_social_copy(linkedin_body), topic)

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


def _fallback_post(topic: str, legal_sources: str = "") -> str:
    topic = str(topic or "").strip()
    sources = str(legal_sources or "").strip()
    source_note = f"\n\nالمصادر القانونية المشار إليها: {sources}" if sources else ""
    return (
        f"معلومة قانونية مهمة عن: {topic}.\n\n"
        "القاعدة العامة لا تُفهم بمعزل عن الوقائع والمستندات والإجراءات القانونية الصحيحة. "
        "قبل اتخاذ أي إجراء، راجع صفة الأطراف، المستندات المتاحة، والآثار القانونية المحتملة، "
        "واطلب المشورة القانونية المتخصصة عند الحاجة."
        f"{source_note}"
    )


def _generate_if_needed(*, service, config, sheet_name, row_number, row, current, topic, bank_rows):
    """Generate content through the original direct Cloudflare image path.

    Character references and Gemini image-QA loops are intentionally removed.
    Image failure never creates a fake visual and never blocks social publication.
    """
    existing_post = str(row.get("المحتوى", "") or "").strip()
    existing_image_url = str(row.get("رابط الصورة", "") or "").strip()
    raw_id = row.get("ID", "") or f"row-{row_number}"
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in raw_id)
    image_path = GENERATED_DIR / f"{safe_id}.jpg"

    previous_context = build_previous_context(bank_rows) + "\n" + build_diversity_context(topic, build_previous_context(bank_rows))
    audience, audience_goal = infer_audience_persona(topic, existing_post, "LINKEDIN")
    visual_id, visual_name = choose_visual_concept(topic, existing_post)
    previous_context += f"\nAUDIENCE: {audience}\nAUDIENCE GOAL: {audience_goal}\nVISUAL CONCEPT: {visual_id} / {visual_name}"
    try:
        strategy_rows = get_values(service, config["sheet_id"], "StrategyRecommendations!A:I")
        if len(strategy_rows) > 1:
            latest_strategy = strategy_rows[-6:]
            previous_context += "\nCURRENT CONTENT STRATEGY SIGNALS:\n" + "\n".join(" | ".join(map(str, x)) for x in latest_strategy)
    except Exception as strategy_exc:
        print(f"Strategy context unavailable: {strategy_exc}")
    duplicate_score, duplicate_topic = _duplicate_score(topic, bank_rows)
    if duplicate_score >= 0.88:
        previous_context += f"\nIMPORTANT: avoid repeating this recent topic verbatim: {duplicate_topic}"

    # Research current law and verified judicial principles before generating any platform copy.
    sheet_legal_sources = str(row.get("المصادر القانونية", "") or "").strip()
    try:
        legal_sources = research_legal_topic(topic, sheet_legal_sources)
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "المصادر القانونية": legal_sources[:12000],
        })
        print("Legal research: refreshed current legislation + verified court sources before content generation.")
    except Exception as research_exc:
        legal_sources = sheet_legal_sources
        print(f"Legal research unavailable; preserving existing legal sources: {research_exc}")

    try:
        result = generate_post(
            api_key=config["gemini_api_key"],
            model=config["gemini_model"],
            topic=topic,
            legal_sources=legal_sources,
            previous_context=previous_context,
        )
        post = str(result.get("post", "") or "").strip() or existing_post or _fallback_post(topic, legal_sources)
        image_brief = str(result.get("image_brief", "") or "").strip() or f"Concrete scene extracted from the published post: {post[:1200]}"
        review_level = str(result.get("review_level", "CLEAR") or "CLEAR").upper()
        review_text = " | ".join(str(x).strip() for x in result.get("review_flags", []) if str(x).strip())
    except Exception as exc:
        post = existing_post or _fallback_post(topic, legal_sources)
        image_brief = f"Concrete scene extracted from the published post: {post[:1200]}"
        review_level = "ADVISORY"
        review_text = f"Content generation unavailable; fallback text used: {exc}"
        print(f"Content generation unavailable — continuing with fallback content: {exc}")

    generated_image_path = None
    current_image_brief = image_brief

    # FINAL PROJECT RULE:
    # Publishing is NEVER blocked by image generation.
    # There is NO image fallback/card/media-search path.
    # The image is generated from the complete post, exactly once for this row.
    # If generation fails, publish the post without an image.
    existing_image_mode = str(row.get("Image Mode", "") or "").strip().upper()
    image_attempted = str(row.get("Image QA Attempt", "") or "").strip() == "1"
    reusable_existing = (
        "FALLBACK" not in existing_image_mode
        and image_path.is_file()
        and image_path.stat().st_size > 0
    )

    if reusable_existing:
        generated_image_path = image_path
        print(f"Image reuse: preserving existing generated asset {image_path}; no regeneration.")
    elif not image_attempted:
        try:
            create_legal_image(
                topic=topic,
                image_brief=current_image_brief,
                post_context=post,
                output_path=str(image_path),
                cloudflare_account_id=config["cloudflare_account_id"],
                cloudflare_api_token=config["cloudflare_api_token"],
            )
            if not image_path.is_file() or image_path.stat().st_size == 0:
                raise ImageGenerationError("Generated image file was empty.")

            brand_published_image(str(image_path))
            generated_image_path = image_path
            image_url = github_raw_url(str(image_path))
            update_row(service, config["sheet_id"], sheet_name, row_number, {
                "رابط الصورة": image_url,
                "Image Mode": "DIRECT_CLOUDFLARE",
                "Image QA Attempt": "1",
                "Image QA Status": "ACCEPTED_SINGLE_GENERATION",
                "Image QA Score": "",
                "Image QA Issues": "",
                "المحتوى": post,
                "وصف الصورة": current_image_brief,
                "وقت آخر تشغيل": current.isoformat(),
            })
            print("Image generated exactly once from the complete published post and locked for this row.")
        except ImageGenerationError as image_exc:
            print(f"Image generation failed once; publishing continues without an image: {image_exc}")
            update_row(service, config["sheet_id"], sheet_name, row_number, {
                "Image Generation Attempt": "1",
                "Image QA Attempt": "1",
                "Image QA Status": "IMAGE_GENERATION_FAILED_PUBLISH_ANYWAY",
                "Image QA Issues": str(image_exc)[:1500],
                "Image Mode": "NONE",
                "رابط الصورة": "",
                "وصف الصورة": current_image_brief,
                "وقت آخر تشغيل": current.isoformat(),
            })
    else:
        print("Image generation was already attempted for this row; no regeneration. Publishing continues without image.")

    image_url = (
        existing_image_url
        if reusable_existing
        else (github_raw_url(str(generated_image_path)) if generated_image_path else "")
    )

    return post, image_url, generated_image_path, review_level, review_text, legal_sources


def _backfill_latest_three_comment_queues(*, service, config, sheet_name: str, rows: list[dict[str, str]], current) -> None:
    """One-time-safe historical engagement: only the three most recent published posts.
    Never scans or queues comments for older historical posts; new posts continue through process_row normally.
    """
    published = []
    for row_number, row in enumerate(rows, start=2):
        status = str(row.get("الحالة", "")).strip().upper()
        if status != "PUBLISHED":
            continue
        if not (str(row.get("Facebook Post ID", "")).strip() or str(row.get("LinkedIn Post ID", "")).strip()):
            continue
        published.append((row_number, row))
    latest = published[-COMMENT_BACKFILL_LIMIT:]
    if not latest:
        return
    for row_number, row in latest:
        fb_queue = str(row.get("Facebook Comment Queue", "") or "").strip()
        li_queue = str(row.get("LinkedIn Comment Queue", "") or "").strip()
        if fb_queue or li_queue:
            continue
        topic = str(row.get("الموضوع", "") or "").strip()
        post = str(row.get("المحتوى", "") or "").strip()
        if not topic or not post:
            continue
        try:
            editorial = _prepare_editorial_assets(config=config, topic=topic, facebook_post=post, legal_sources=legal_sources)
            update_row(service, config["sheet_id"], sheet_name, row_number, {
                "Facebook Comment Queue": json.dumps(editorial["facebook_comments"], ensure_ascii=False),
                "LinkedIn Comment Queue": json.dumps(editorial["linkedin_comments"], ensure_ascii=False),
                "Facebook Comments Published": row.get("Facebook Comments Published", "") or "0",
                "LinkedIn Comments Published": row.get("LinkedIn Comments Published", "") or "0",
                "وقت آخر تشغيل": current.isoformat(),
            })
            print(f"Comment backfill queued: row={row_number} topic={topic} count={len(editorial['linkedin_comments'])}")
        except Exception as exc:
            print(f"Comment backfill failed for row {row_number}: {exc}")



def _is_bad_published_image(row: dict[str, str]) -> bool:
    mode = str(row.get("Image Mode", "") or "").strip().upper()
    qa = str(row.get("Image QA Status", "") or "").strip().upper()
    repair_attempted = qa.startswith("IMAGE_REPAIR_") or qa == "REPAIRED_SINGLE_GENERATION"
    if repair_attempted:
        return False
    return "FALLBACK" in mode or "FALLBACK" in qa or mode in {"IMAGE_REQUIRED", "NONE"}


def _repair_published_bad_image(*, service, config, sheet_name: str, row_number: int, row: dict[str, str], current) -> None:
    """
    Repair a post that was already published with a fallback/card image.

    The repair is deliberately narrow:
    - keep the exact published post text;
    - generate exactly one replacement image from that post;
    - delete the old social posts only after the new image exists;
    - publish the same text once with the replacement image;
    - clear the fallback marker so this path cannot repeat.
    """
    topic = str(row.get("الموضوع", "") or "").strip()
    post = str(row.get("المحتوى", "") or "").strip()
    if not topic or not post:
        raise RuntimeError("Image repair requires an existing topic and published post.")

    raw_id = str(row.get("ID", "") or f"row-{row_number}")
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in raw_id)
    image_path = GENERATED_DIR / f"{safe_id}.jpg"
    image_brief = str(row.get("وصف الصورة", "") or "").strip() or f"Concrete scene extracted from the published post: {post[:1400]}"

    print(f"IMAGE REPAIR: generating exactly one replacement image for row {row_number}.")
    update_row(service, config["sheet_id"], sheet_name, row_number, {
        "Image QA Attempt": "1",
        "Image QA Status": "IMAGE_REPAIR_IN_PROGRESS",
        "وقت آخر تشغيل": current.isoformat(),
    })
    try:
        create_legal_image(
            topic=topic,
            image_brief=image_brief,
            post_context=post,
            output_path=str(image_path),
            cloudflare_account_id=config["cloudflare_account_id"],
            cloudflare_api_token=config["cloudflare_api_token"],
        )
        if not image_path.is_file() or image_path.stat().st_size == 0:
            raise ImageGenerationError("Replacement image file was empty.")
        brand_published_image(str(image_path))
    except ImageGenerationError as exc:
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "Image QA Attempt": "1",
            "Image QA Status": "IMAGE_REPAIR_GENERATION_FAILED",
            "Image QA Issues": str(exc)[:1500],
            "Image Mode": "IMAGE_REPAIR_FAILED",
            "وقت آخر تشغيل": current.isoformat(),
        })
        raise

    image_url = github_raw_url(str(image_path))
    facebook_old = str(row.get("Facebook Post ID", "") or "").strip()
    linkedin_old = str(row.get("LinkedIn Post ID", "") or "").strip()

    # Do not create duplicates. Remove the known bad posts before publishing
    # the repaired versions, and only after the replacement image is ready.
    if facebook_old:
        delete_facebook_post(
            post_id=facebook_old,
            page_access_token=config["facebook_page_access_token"],
            graph_version=config["facebook_graph_version"],
        )
    if linkedin_old:
        delete_linkedin_post(
            token=config["linkedin_access_token"],
            post_urn=linkedin_old,
        )

    facebook_post = append_hashtags(sanitize_social_copy(post), topic)
    linkedin_post = append_hashtags(sanitize_social_copy(post), topic)
    fb = publish_photo(
        page_id=config["facebook_page_id"],
        page_access_token=config["facebook_page_access_token"],
        graph_version=config["facebook_graph_version"],
        image_path=image_path,
        caption=facebook_post,
    )
    token = config["linkedin_access_token"]
    author = (config.get("linkedin_author_urn", "") or "").strip() or resolve_member_urn(token)
    li = publish_to_linkedin(
        token=token,
        author_urn=author,
        image_path=image_path,
        commentary=linkedin_post,
        first_comment="",
    )

    update_row(service, config["sheet_id"], sheet_name, row_number, {
        "الحالة": "PUBLISHED",
        "رابط الصورة": image_url,
        "Image Mode": "DIRECT_CLOUDFLARE",
        "Image QA Attempt": "1",
        "Image QA Status": "REPAIRED_SINGLE_GENERATION",
        "Image QA Score": "",
        "Image QA Issues": "",
        "Facebook Status": "PUBLISHED",
        "Facebook Post ID": fb["post_id"],
        "Facebook Comment Status": "QUEUED",
        "Facebook Reaction Status": "QUEUED",
        "LinkedIn Status": "PUBLISHED",
        "LinkedIn Post ID": li["post_urn"],
        "LinkedIn Comment Status": "QUEUED",
        "LinkedIn Reaction Status": "QUEUED",
        "آخر خطأ": "",
        "وقت آخر تشغيل": current.isoformat(),
    })
    print(f"IMAGE REPAIR COMPLETE: row={row_number} | Facebook={fb['post_id']} | LinkedIn={li['post_urn']}")
    try:
        add_published_post(
            service,
            config["sheet_id"],
            source_row_id=row.get("ID", ""),
            topic=topic,
            content=facebook_post,
            publish_date=current.date().isoformat(),
            facebook_post_id=fb["post_id"],
            linkedin_post_id=li["post_urn"],
            image_url=image_url,
            legal_sources=row.get("المصادر القانونية", ""),
            angle=row.get("ملاحظات", ""),
            objective="IMAGE_REPAIR",
            review_level="CLEAR",
        )
    except Exception as exc:
        print(f"Image repair PostBank logging failed: {exc}")


def process_row(*, service, config, sheet_name: str, row_number: int, row: dict[str, str], current) -> None:
    topic = row.get("الموضوع", "").strip()
    if not topic:
        raise RuntimeError(f"Row {row_number} has no topic.")
    print(f"Processing row {row_number}: {topic}")
    original_status = str(row.get("الحالة", "")).strip().upper()
    if not DRY_RUN and original_status == "PUBLISHED" and _is_bad_published_image(row):
        try:
            _repair_published_bad_image(
                service=service,
                config=config,
                sheet_name=sheet_name,
                row_number=row_number,
                row=row,
                current=current,
            )
        except Exception as repair_exc:
            print(f"Image repair failed; existing publication remains untouched and the pipeline continues: {repair_exc}")
        return

    if DRY_RUN:
        bank_rows = get_bank_rows(service, config["sheet_id"])
        post, _, image_path, level, reason, legal_sources = _generate_if_needed(service=service, config=config, sheet_name=sheet_name, row_number=row_number, row=row, current=current, topic=topic, bank_rows=bank_rows)
        editorial = _prepare_editorial_assets(config=config, topic=topic, facebook_post=post, legal_sources=legal_sources)
        print(f"DRY RUN: Facebook comments={len(editorial['facebook_comments'])}/20 | LinkedIn comments={len(editorial['linkedin_comments'])}/5 | image={image_path}")
        return

    update_row(service, config["sheet_id"], sheet_name, row_number, {"الحالة": "PROCESSING" if original_status not in {"FAILED", "PARTIAL_FAILED", "READY_FOR_SOCIAL_PUBLISH"} else original_status, "آخر خطأ": "", "وقت آخر تشغيل": current.isoformat()})
    bank_rows = get_bank_rows(service, config["sheet_id"])
    pillar, objective = classify(topic, row.get("المحتوى", ""))
    try:
        post, image_url, image_path, review_level, review_text, legal_sources = _generate_if_needed(service=service, config=config, sheet_name=sheet_name, row_number=row_number, row=row, current=current, topic=topic, bank_rows=bank_rows)
        image_available = bool(image_path and Path(image_path).is_file())
        if not image_available:
            print("No generated image is available; publication continues as text-only. Image generation never blocks publishing.")
        if not post:
            post = _fallback_post(topic, row.get("المصادر القانونية", ""))
        try:
            editorial = _prepare_editorial_assets(config=config, topic=topic, facebook_post=post, legal_sources=row.get("المصادر القانونية", ""))
        except Exception as editorial_exc:
            print(f"Editorial/comment generation unavailable — publishing post without generated engagement bundle: {editorial_exc}")
            editorial = {"facebook_post": post, "linkedin_post": post, "facebook_comments": [], "linkedin_comments": []}
        facebook_post = append_hashtags(sanitize_social_copy(editorial["facebook_post"]), topic)
        linkedin_body, _ = split_hashtags(editorial.get("linkedin_post", ""))
        linkedin_post = append_hashtags(sanitize_social_copy(linkedin_body), topic)
        try:
            update_row(service, config["sheet_id"], sheet_name, row_number, {
                "Facebook Comment Queue": json.dumps(editorial["facebook_comments"], ensure_ascii=False),
                "LinkedIn Comment Queue": json.dumps(editorial["linkedin_comments"], ensure_ascii=False),
                "Facebook Comments Published": row.get("Facebook Comments Published", "") or "0",
                "LinkedIn Comments Published": row.get("LinkedIn Comments Published", "") or "0",
            })
        except Exception as queue_exc:
            print(f"Engagement queue persistence unavailable — social publication continues: {queue_exc}")


        facebook_post_id = str(row.get("Facebook Post ID", "") or "").strip() if original_status in {"FAILED", "PARTIAL_FAILED", "READY_FOR_SOCIAL_PUBLISH"} else ""
        linkedin_post_id = str(row.get("LinkedIn Post ID", "") or "").strip() if original_status in {"FAILED", "PARTIAL_FAILED", "READY_FOR_SOCIAL_PUBLISH"} else ""
        facebook_comments = 0
        linkedin_comments = 0
        linkedin_interaction_errors: list[str] = []
        publication_errors: list[str] = []

        if facebook_post_id and str(row.get("Facebook Status", "")).strip().upper() == "PUBLISHED":
            print(f"Idempotency: Facebook already published as {facebook_post_id}; skipping duplicate publish.")
        else:
            try:
                facebook = (publish_photo(page_id=config["facebook_page_id"], page_access_token=config["facebook_page_access_token"], graph_version=config["facebook_graph_version"], image_path=image_path, caption=facebook_post) if image_available else publish_text(page_id=config["facebook_page_id"], page_access_token=config["facebook_page_access_token"], graph_version=config["facebook_graph_version"], message=facebook_post))
                facebook_post_id = facebook["post_id"]
                row["Facebook Status"] = "PUBLISHED"
                try:
                    update_row(service, config["sheet_id"], sheet_name, row_number, {"Facebook Status": "PUBLISHED", "Facebook Post ID": facebook_post_id, "Facebook Comment Status": "QUEUED", "Facebook Reaction Status": "QUEUED"})
                except Exception as state_exc:
                    print(f"Facebook state persistence unavailable after successful publish: {state_exc}")
                try:
                    print("Facebook engagement queued for dedicated worker.")
                except Exception as exc:
                    print(f"Facebook comment engine failed: {exc}")
            except FacebookPublishError as exc:
                error = f"Facebook: {exc}"
                publication_errors.append(error)
                row["Facebook Status"] = "FAILED"
                try:
                    update_row(service, config["sheet_id"], sheet_name, row_number, {"Facebook Status": "FAILED", "آخر خطأ": error})
                except Exception as state_exc:
                    print(f"Facebook failure state could not be persisted: {state_exc}")
                notify(f"🚨 Facebook publishing failed\nالموضوع: {topic}\nالسبب: {exc}")

        linkedin_status = str(row.get("LinkedIn Status", "")).strip().upper()
        if linkedin_post_id and linkedin_status == "PUBLISHED":
            print(f"Idempotency: LinkedIn post already published as {linkedin_post_id}; skipping duplicate LinkedIn post.")
        else:
            try:
                token = config["linkedin_access_token"]
                author = (config.get("linkedin_author_urn", "") or "").strip() or resolve_member_urn(token)
                linkedin = (publish_to_linkedin(token=token, author_urn=author, image_path=image_path, commentary=linkedin_post, first_comment="") if image_available else publish_text_to_linkedin(token=token, author_urn=author, commentary=linkedin_post))
                linkedin_post_id = linkedin["post_urn"]
                row["LinkedIn Status"] = "PUBLISHED"
                comment_result = linkedin.get("comment") or {}
                like_result = linkedin.get("like") or {}
                linkedin_interaction_errors.extend([x for x in (comment_result.get("error"), like_result.get("error")) if x])
                try:
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
                except Exception as state_exc:
                    print(f"LinkedIn state persistence unavailable after successful publish: {state_exc}")
            except LinkedInPublishError as exc:
                error = f"LinkedIn: {exc}"
                publication_errors.append(error)
                row["LinkedIn Status"] = "FAILED"
                try:
                    update_row(service, config["sheet_id"], sheet_name, row_number, {"LinkedIn Status": "FAILED", "آخر خطأ": error})
                except Exception as state_exc:
                    print(f"LinkedIn failure state could not be persisted: {state_exc}")
                notify(f"🚨 LinkedIn publishing failed\nالموضوع: {topic}\nالسبب: {exc}")

        fb_ok = bool(facebook_post_id) and str(row.get("Facebook Status", "") or "").strip().upper() == "PUBLISHED"
        li_post_ok = bool(linkedin_post_id) and str(row.get("LinkedIn Status", "") or "").strip().upper() == "PUBLISHED"
        if not fb_ok and not li_post_ok:
            final_status = "FAILED"
        elif fb_ok and li_post_ok:
            final_status = "PUBLISHED"
        else:
            final_status = "PARTIAL_FAILED"
        final_error = " | ".join(publication_errors + linkedin_interaction_errors)[:1500]
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
                record_fingerprint(service, config["sheet_id"], post_id=facebook_post_id, topic=topic, post=facebook_post, angle=row.get("ملاحظات", ""), objective=objective, platform="FACEBOOK")
                record_fingerprint(service, config["sheet_id"], post_id=linkedin_post_id, topic=topic, post=linkedin_post, angle=row.get("ملاحظات", ""), objective=objective, platform="LINKEDIN")
            except Exception as exc:
                print(f"PostBank/Analytics logging failed: {exc}")
            notify(
                f"✅ Khyrat Legal Content Engine\nتم نشر: {topic}\n"
                f"Facebook: {'✅' if fb_ok else '❌'} | LinkedIn: {'✅' if li_post_ok else '❌'}\n"
                f"التعليقات: Facebook 3-7 | LinkedIn 3-7 (تم وضعها في Queue ويشغلها Engagement Worker)"
            )
        else:
            detail = final_error or "Social publication did not complete; row remains retryable."
            notify(f"🟠 Publication retry scheduled automatically.\nالموضوع: {topic}\nالسبب: {detail}")
            print(f"Non-blocking publication failure; scheduler will retry: {detail}")
        return
    except Exception as exc:
        print(f"Non-blocking pipeline error: {exc}")
        print(traceback.format_exc())
        try:
            update_row(service, config["sheet_id"], sheet_name, row_number, {"الحالة": "FAILED", "آخر خطأ": str(exc)[:1500], "وقت آخر تشغيل": current.isoformat()})
        except Exception as sheet_exc:
            print(f"Sheet failure recording error (also non-blocking): {sheet_exc}")
        notify(f"🟠 Pipeline issue — التشغيل مستمر وسيتم إعادة المحاولة تلقائيًا.\nالموضوع: {topic}\nالسبب: {exc}")
        return


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
    # Historical backfill is deliberately hard-limited to the latest 3 published posts.
    # This runs before normal scheduling; it never processes older posts.
    try:
        _backfill_latest_three_comment_queues(service=service, config=config, sheet_name=sheet_name, rows=rows, current=current)
    except Exception as exc:
        print(f"Latest-3 comment backfill unavailable; normal publishing continues: {exc}")
    repair_candidates = [
        (i, r) for i, r in enumerate(rows, start=2)
        if str(r.get("الحالة", "")).strip().upper() == "PUBLISHED"
        and _is_bad_published_image(r)
    ]
    if repair_candidates:
        row_number, row = repair_candidates[0]
        print(f"Found published row requiring image repair: row={row_number}")
        try:
            process_row(service=service, config=config, sheet_name=sheet_name, row_number=row_number, row=row, current=current)
        except Exception as exc:
            print(f"Image repair failed; normal publishing selection continues: {exc}")
            print(traceback.format_exc())

    candidates = [(i, r) for i, r in enumerate(rows, start=2) if _is_due(r, current)]
    if not candidates:
        candidates = [(i, r) for i, r in enumerate(rows, start=2) if _failed_retry(r, current)][:1]
    if not candidates:
        print("No due rows found.")
        return
    row_number, row = candidates[0]
    try:
        process_row(service=service, config=config, sheet_name=sheet_name, row_number=row_number, row=row, current=current)
    except Exception as exc:
        print(f"Top-level non-blocking row failure: {exc}")
        print(traceback.format_exc())


if __name__ == "__main__":
    main()
