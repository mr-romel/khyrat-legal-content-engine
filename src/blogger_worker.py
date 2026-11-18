from __future__ import annotations

import json
import os
import re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from blogger_publisher import BloggerPublishError, blog_id, publish_article, upload_blogger_image, build_article_html, prepare_article, _article_copy, _fallback_article, normalize_blogger_labels, service as blogger_service
from blogger_ui_publisher import BloggerUIPublishError, publish_article_ui, _public_post_permalink
from config import load_blogger_config
from sheets import create_service, ensure_headers, get_values, row_to_dict, update_row, HEADERS
from utils import parse_date
from legal_research import has_verified_legal_source, research_legal_topic
from telegram_bot import configured as telegram_configured, send_message as telegram_send_message

BLOGGER_ARTIFACT_DIR = "generated/blogger"


def _mark_blogger_failed(service, config: dict, sheet_name: str, row_number: int, reason: str) -> None:
    """Persist a truthful retryable failure state without hiding the original exception."""
    try:
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "Blogger Status": "FAILED",
            "Blogger Last Error": str(reason or "Unknown Blogger failure")[:1500],
        })
    except Exception as state_exc:
        print(f"Blogger failure state could not be persisted for row {row_number}: {state_exc}")


def _refresh_missing_legal_sources(topic: str, legal_sources: str) -> str:
    """Always require a fresh retrieval; old Sheet sources remain reference notes only."""
    try:
        return research_legal_topic(topic, legal_sources)
    except Exception as research_exc:
        print(f"Blogger live legal research unavailable; stale sources will not pass the gate: {research_exc}")
        return ""

def _internal_terms(value: str) -> set[str]:
    text = str(value or "").casefold()
    text = re.sub(r"[إأآٱ]", "ا", text).replace("ى", "ي").replace("ة", "ه")
    words = re.findall(r"[a-z0-9\u0621-\u064a]{3,}", text)
    stop = {"في", "من", "على", "عن", "الى", "الي", "ما", "هل", "كيف", "مع", "هذا", "هذه", "التي", "الذي", "القانون", "القانوني", "مصر"}
    return {word for word in words if word not in stop}


def _blogger_feed_entries(feed_type: str) -> list[dict[str, str]]:
    base = os.getenv("BLOGGER_URL", "https://askmahmoudkhyrat.blogspot.com/").strip().rstrip("/")
    url = f"{base}/feeds/{feed_type}/default"
    response = requests.get(url, params={"alt": "json", "max-results": "100"}, timeout=25)
    response.raise_for_status()
    entries = response.json().get("feed", {}).get("entry", []) or []
    result = []
    for entry in entries:
        title = str((entry.get("title") or {}).get("$t", "")).strip()
        href = next((str(link.get("href", "")).strip() for link in entry.get("link", []) or [] if link.get("rel") == "alternate"), "")
        if title and href.startswith(base + "/"):
            result.append({"title": title, "url": href})
    return result


def _related_internal_pages(topic: str, *, limit: int = 3) -> list[dict[str, str]]:
    """Choose verified live Blogger pages/posts using practice-area routing and title overlap."""
    try:
        pages = _blogger_feed_entries("pages")
        posts = _blogger_feed_entries("posts")
    except Exception as exc:
        print(f"Blogger internal links: public feed unavailable; no speculative links added: {exc}")
        return []

    rules = [
        (("جنائي", "جريمة", "اتهام", "محضر", "بلاغ", "حبس", "تحقيق"), "محامي قضايا جنائية في القاهرة والجيزة"),
        (("أسرة", "طلاق", "نفقة", "حضانة", "رؤية", "خلع"), "محامي أحوال شخصية وأسرة في القاهرة والجيزة"),
        (("عمل", "عامل", "موظف", "فصل", "مرتب", "أجر", "إجاز"), "محامي قضايا العمل ومستحقات العامل في مصر"),
        (("عقد", "اتفاق", "صياغة", "تعاقد"), "مراجعة وصياغة العقود للشركات والأفراد"),
        (("شركة", "شركات", "تأسيس", "شريك", "تجارة"), "الخدمات القانونية للشركات وتأسيسها"),
        (("تعويض", "مسؤولية", "ضرر", "مطالبة"), "قضايا التعويض والمسؤولية المدنية"),
    ]
    page_by_title = {item["title"]: item for item in pages}
    chosen: list[dict[str, str]] = []
    seen: set[str] = set()
    for markers, title in rules:
        if any(marker in topic for marker in markers):
            item = page_by_title.get(title)
            if item and item["url"] not in seen:
                chosen.append(item)
                seen.add(item["url"])
                break
    hub = page_by_title.get("الخدمات القانونية للأفراد والشركات")
    if hub and hub["url"] not in seen and len(chosen) < limit:
        chosen.append(hub)
        seen.add(hub["url"])

    source_terms = _internal_terms(topic)
    ranked = []
    for item in posts:
        if item["url"] in seen or "الجزائر" in item["title"] or "الجزائري" in item["title"]:
            continue
        overlap = source_terms & _internal_terms(item["title"])
        if len(overlap) >= 2:
            ranked.append((len(overlap), item["title"], item))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    for _score, _title, item in ranked:
        if len(chosen) >= limit:
            break
        if item["url"] not in seen:
            chosen.append(item)
            seen.add(item["url"])
    print(f"Blogger internal links selected={len(chosen)} for topic={topic!r}")
    return chosen


def github_raw_url(relative_path: str) -> str:
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    branch = os.getenv("GITHUB_REF_NAME", "main").strip() or "main"
    if not repository:
        return ""
    return f"https://raw.githubusercontent.com/{repository}/{branch}/{relative_path.replace(chr(92), '/').lstrip('/')}"


def resolve_image_path(image_url: str, source_id: str, row_number: int) -> str:
    """Resolve the exact published image, downloading the raw URL when needed."""
    candidates = []
    if source_id:
        safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in source_id)
        candidates.extend([
            Path("generated") / (safe_id + ".jpg"),
            Path("generated") / (source_id + ".jpg"),
        ])
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return str(candidate)
    url = str(image_url or "").strip()
    if not url:
        return ""
    try:
        out = Path(BLOGGER_ARTIFACT_DIR) / ("row_" + str(row_number)) / "source-image.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        out.write_bytes(response.content)
        if out.stat().st_size > 0:
            return str(out)
    except Exception as exc:
        print(f"Blogger image download failed for row {row_number}: {exc}")
    return ""

def repair_published_image(svc, bid: str, row: dict[str, str]) -> bool:
    post_id = str(row.get("Blogger Post ID", "")).strip()
    source_id = str(row.get("ID", "")).strip()
    old_url = str(row.get("رابط الصورة", "")).strip()
    image_path = Path(resolve_image_path(old_url, source_id, 0)) if source_id else Path("")
    if not post_id or not image_path.is_file() or not old_url:
        return False
    try:
        current = svc.posts().get(blogId=bid, postId=post_id).execute()
        content = str(current.get("content", "") or "")
        hosted = upload_blogger_image(str(image_path))
        if hosted in content:
            return True
        figure = f'<figure><img src="{hosted}" alt="صورة توضيحية للمقال" loading="eager" style="width:100%;height:auto;border-radius:12px"></figure>'
        if old_url and old_url in content:
            repaired = content.replace(old_url, hosted, 1)
        elif "<article" in content:
            repaired = content.replace("<article", figure + "<article", 1)
        else:
            repaired = figure + content
        svc.posts().patch(blogId=bid, postId=post_id, body={"content": repaired}).execute()
        print(f"Blogger image repaired for post {post_id}: {hosted}")
        return True
    except Exception as exc:
        print(f"Blogger image repair unavailable for {post_id}: {exc}")
        return False

def regenerate_duplicate_published_image(svc, sheet_service, spreadsheet_id: str, sheet_name: str, bid: str, row_number: int, row: dict[str, str]) -> bool:
    """Generate and attach a new topic-specific image when a published row reuses another row's image."""
    import hashlib
    from image_generator import create_legal_image, _supports_topic_specific_local_scene
    from image_qa import qa_image
    from gemini import _deterministic_legal_scene
    post_id = str(row.get("Blogger Post ID", "")).strip()
    source_id = str(row.get("ID", "row-" + str(row_number))).strip()
    topic = str(row.get("الموضوع", "")).strip()
    post = str(row.get("المحتوى", "")).strip()
    old_url = str(row.get("رابط الصورة", "")).strip()
    if not post_id or not topic or not post:
        return False
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in source_id)
    image_path = Path(BLOGGER_ARTIFACT_DIR) / ("row_" + str(row_number)) / ("dedup-" + safe_id + ".jpg")
    image_path.parent.mkdir(parents=True, exist_ok=True)
    brief = _deterministic_legal_scene(topic, post) or post[:1400]
    provider = "local_scene" if _supports_topic_specific_local_scene(topic, brief) else "auto"
    create_legal_image(
        topic=topic, image_brief=brief, visual_description=brief,
        post_context=post, output_path=str(image_path),
        api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        cloudflare_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip(),
        cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN", "").strip(),
        provider=provider,
    )
    qa = qa_image(
        api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        image_path=str(image_path), topic=topic, image_brief=brief,
    )
    if str(qa.get("decision", "")).upper() != "PASS":
        raise RuntimeError(f"BLOGGER_IMAGE_REPAIR_QA_BLOCKED: {qa.get('issues', [])}")
    new_url = upload_blogger_image(str(image_path))
    current = svc.posts().get(blogId=bid, postId=post_id).execute()
    content = str(current.get("content", "") or "")
    if old_url and old_url in content:
        content = content.replace(old_url, new_url, 1)
    else:
        figure = f'<figure><img src="{new_url}" alt="{topic}" loading="eager" style="width:100%;height:auto;border-radius:12px"></figure>'
        content = figure + content
    svc.posts().patch(blogId=bid, postId=post_id, body={"content": content}).execute()
    update_row(sheet_service, spreadsheet_id, sheet_name, row_number, {
        "رابط الصورة": new_url,
        "Image SHA256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        "Image Mode": "POST_DERIVED_AI_GENERATION",
        "Image QA Status": "REPAIRED_SINGLE_GENERATION",
        "Image QA Issues": "",
        "Image QA Score": str(qa.get("overall_score", "")),
    })
    print(f"BLOGGER_DUPLICATE_IMAGE_REPAIRED: row={row_number}; post_id={post_id}; source_id={source_id}")
    return True

def _norm_text(value: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return " ".join(text.split()).casefold()

def _find_existing_blogger_post_for_row(svc, bid: str, row: dict[str, str]) -> dict | None:
    """Find an already-inserted Blogger article after a publish response was lost."""
    topic = str(row.get("الموضوع", "") or "").strip()
    post = _norm_text(str(row.get("المحتوى", "") or ""))
    if not topic or not post:
        return None
    stop = {"قانون", "المصري", "مصر", "في", "من", "على", "عن", "قبل", "بعد", "جديد", "جديدة", "عملية", "أي", "إجراء", "زاوية", "checklist"}
    terms = [term for term in _norm_text(topic).split() if len(term) >= 3 and term not in stop]
    if not terms:
        return None
    matches = []
    token = None
    while True:
        kwargs = {"blogId": bid, "maxResults": 500, "fetchBodies": True}
        if token:
            kwargs["pageToken"] = token
        data = svc.posts().list(**kwargs).execute()
        for item in data.get("items", []) or []:
            title = _norm_text(item.get("title", ""))
            body = _norm_text(item.get("content", ""))
            title_score = sum(1 for term in terms if term in title)
            body_score = sum(1 for term in terms if term in body)
            excerpt_match = len(post) >= 120 and post[:120] in body
            if title_score >= min(2, len(terms)) or excerpt_match or body_score >= max(3, min(4, len(terms))):
                matches.append((title_score, body_score, str(item.get("published", "") or item.get("updated", "")), item))
        token = data.get("nextPageToken")
        if not token:
            break
    if not matches:
        return None
    matches.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return matches[0][3]


def _repair_existing_blogger_post_image(svc, bid: str, post_id: str, row_number: int, row: dict[str, str]) -> tuple[str, int, str]:
    """Replace a generic/failed Blogger hero with one topic-specific, locally QA-approved scene."""
    from gemini import _deterministic_legal_scene
    from image_generator import create_legal_image, _supports_topic_specific_local_scene
    from image_qa import qa_image

    topic = str(row.get("الموضوع", "") or "").strip()
    post = str(row.get("المحتوى", "") or "").strip()
    brief = _deterministic_legal_scene(topic, post) or post[:1400]
    provider = "local_scene" if _supports_topic_specific_local_scene(topic, brief) else "auto"
    source_id = str(row.get("ID", "") or f"row-{row_number}")
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in source_id)
    image_path = Path(BLOGGER_ARTIFACT_DIR) / f"row_{row_number}" / f"topic-repair-{safe_id}.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    create_legal_image(
        topic=topic,
        image_brief=brief,
        visual_description=brief,
        post_context=post,
        output_path=str(image_path),
        api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        cloudflare_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip(),
        cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN", "").strip(),
        provider=provider,
    )
    qa = qa_image(
        api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        image_path=str(image_path),
        topic=topic,
        image_brief=brief,
    )
    if str(qa.get("decision", "")).upper() != "PASS":
        raise RuntimeError(f"BLOGGER_EXISTING_POST_IMAGE_QA_BLOCKED: {qa.get('issues', [])}")
    new_url = upload_blogger_image(str(image_path))
    current = svc.posts().get(blogId=bid, postId=post_id).execute()
    content = str(current.get("content", "") or "")
    old_url = str(row.get("رابط الصورة", "") or "").strip()
    if old_url and old_url in content:
        content = content.replace(old_url, new_url, 1)
    else:
        match = re.search(r"\\bsrc=[\"']([^\"']+)[\"']", content, flags=re.IGNORECASE)
        if match:
            content = content[:match.start(1)] + new_url + content[match.end(1):]
        else:
            content = f'<figure><img src="{new_url}" alt="{topic}" loading="eager" style="width:100%;height:auto;border-radius:12px"></figure>' + content
    svc.posts().patch(blogId=bid, postId=post_id, body={"content": content}).execute()
    verified = svc.posts().get(blogId=bid, postId=post_id).execute()
    verified_html = str(verified.get("content", "") or "")
    if new_url not in verified_html or len(_norm_text(verified_html)) < 900:
        raise RuntimeError("BLOGGER_EXISTING_POST_IMAGE_VERIFICATION_FAILED: API read-back did not confirm the new image and article body.")
    import hashlib
    image_sha = hashlib.sha256(image_path.read_bytes()).hexdigest()
    return new_url, int(qa.get("overall_score", 0) or 0), image_sha


def dedupe_blogger_topics(svc, bid: str, rows: list[dict[str, str]]) -> int:
    """Delete duplicate Blogger posts for the same generated article, keeping the oldest copy."""
    import re
    def key(value: str) -> str:
        text = re.sub(r"<[^>]+>", " ", str(value or ""))
        text = re.sub(r"\s+", " ", text).strip().casefold()
        return text

    canonical_titles = set()
    canonical_bodies = set()
    for row in rows:
        topic = str(row.get("الموضوع", "")).strip()
        post = str(row.get("المحتوى", "")).strip()
        if not topic or not post:
            continue
        try:
            article = _fallback_article(topic, post, str(row.get("المصادر القانونية", ""))) or {}
            title = key(article.get("title", ""))
            if title:
                canonical_titles.add(title)
        except Exception:
            pass
        body = key(post)
        if len(body) >= 180:
            canonical_bodies.add(body[:240])

    posts = []
    token = None
    while True:
        kwargs = {"blogId": bid, "maxResults": 500, "fetchBodies": True}
        if token:
            kwargs["pageToken"] = token
        data = svc.posts().list(**kwargs).execute()
        posts.extend(data.get("items", []) or [])
        token = data.get("nextPageToken")
        if not token:
            break

    groups: dict[str, list[dict]] = {}
    for item in posts:
        title = key(item.get("title", ""))
        body = key(item.get("content", ""))
        match_key = ""
        if title and title in canonical_titles:
            match_key = "title:" + title
        else:
            for snippet in canonical_bodies:
                if snippet and snippet in body:
                    match_key = "body:" + snippet
                    break
        if match_key:
            groups.setdefault(match_key, []).append(item)

    deleted = 0
    for group_key, items in groups.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda x: str(x.get("published", "") or x.get("updated", "")))
        keep = items[0]
        print(f"Blogger dedupe: keeping post {keep.get('id')} for {group_key}; duplicates={len(items)-1}")
        for item in items[1:]:
            pid = str(item.get("id", "")).strip()
            if not pid:
                continue
            try:
                svc.posts().delete(blogId=bid, postId=pid).execute()
                deleted += 1
                print(f"Blogger dedupe: deleted duplicate post {pid}")
            except Exception as exc:
                print(f"Blogger dedupe: could not delete duplicate {pid}: {exc}")
    return deleted

def cleanup_misdated_automation_posts(svc, bid: str, rows: list[dict[str, str]], today) -> int:
    older_snippets = []
    older_titles = {"في مسائل العمل: ما الذي يجب مراجعته قبل اتخاذ القرار؟".casefold()}
    for row in rows:
        if parse_date(row.get("تاريخ النشر", "")) == today:
            continue
        body = _norm_text(row.get("المحتوى", ""))
        if len(body) >= 120:
            older_snippets.append(body[:180])
        try:
            fallback_title = str(_fallback_article(str(row.get("الموضوع", "")), str(row.get("المحتوى", "")), str(row.get("المصادر القانونية", ""))).get("title", "")).strip().casefold()
            if fallback_title:
                older_titles.add(fallback_title)
        except Exception:
            pass
    if not older_snippets:
        return 0
    deleted = 0
    token = None
    while True:
        kwargs = {"blogId": bid, "maxResults": 500, "fetchBodies": True}
        if token:
            kwargs["pageToken"] = token
        data = svc.posts().list(**kwargs).execute()
        for item in data.get("items", []) or []:
            if not str(item.get("published", "")).startswith(today.isoformat()):
                continue
            body = _norm_text(item.get("content", ""))
            item_title = _norm_text(item.get("title", ""))
            title_match = item_title in older_titles
            body_match = any(snippet in body for snippet in older_snippets)
            if not title_match and not body_match:
                continue
            pid = str(item.get("id", "")).strip()
            if not pid:
                continue
            try:
                svc.posts().delete(blogId=bid, postId=pid).execute()
                deleted += 1
                print("Blogger cleanup: deleted misdated automation post " + pid)
            except Exception as exc:
                print("Blogger cleanup: could not delete misdated post " + pid + ": " + str(exc))
        token = data.get("nextPageToken")
        if not token:
            break
    return deleted
def main() -> int:
    config = load_blogger_config()
    if not config["enabled"]:
        print("Blogger publishing disabled; social pipeline continues.")
        return 0

    service = create_service(config["service_account_info"])
    sheet_name = config["sheet_range"].split("!", 1)[0]
    ensure_headers(service, config["sheet_id"], sheet_name)
    values = get_values(service, config["sheet_id"], config["sheet_range"])
    if not values:
        print("Blogger worker: no sheet rows.")
        return 0

    rows = [row_to_dict(row) for row in values[1:]]
    # Emit a compact, non-sensitive eligibility report so a green workflow cannot
    # conceal why a social-published row was not eligible for Blogger publication.
    published_rows = [row for row in rows if str(row.get("الحالة", "")).strip().upper() == "PUBLISHED"]
    blogger_done_rows = [row for row in published_rows if str(row.get("Blogger Status", "")).strip().upper() == "PUBLISHED"]
    missing_body_rows = [row for row in published_rows if not str(row.get("المحتوى", "")).strip()]
    print(
        "Blogger eligibility diagnostics: "
        f"sheet_rows={len(rows)}; social_published={len(published_rows)}; "
        f"blogger_already_published={len(blogger_done_rows)}; "
        f"missing_article_body={len(missing_body_rows)}"
    )
    for diagnostic_row in published_rows[-10:]:
        if str(diagnostic_row.get("Blogger Status", "")).strip().upper() != "PUBLISHED":
            print(
                "Blogger candidate diagnostic: "
                f"id={str(diagnostic_row.get('ID', '')).strip()}; "
                f"date={str(diagnostic_row.get('تاريخ النشر', '')).strip()}; "
                f"body_chars={len(str(diagnostic_row.get('المحتوى', '')).strip())}; "
                f"blogger_status={str(diagnostic_row.get('Blogger Status', '')).strip() or 'EMPTY'}"
            )
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today_cairo = datetime.now(ZoneInfo("Africa/Cairo")).date()
    # Prefer Blogger REST API when OAuth is configured. The browser editor has
    # intermittently saved only the title; use UI only as a fallback when API OAuth is absent.
    # OAuth refresh tokens can be revoked independently of the authenticated browser session.
    # Prefer the saved UI session when present so a stale OAuth token does not block publishing.
    # The shared publishing branch tries Blogger REST API first when OAuth exists,
    # then uses the saved browser session only if REST publication fails.
    has_blogger_oauth = bool(os.getenv("BLOGGER_OAUTH_JSON", "").strip())
    use_ui = bool(config.get("blogger_ui_storage_state_b64"))
    bid = str(config.get("blogger_blog_id", "") or "").strip()
    if has_blogger_oauth:
        try:
            # Resolve the real blog ID whenever OAuth is usable, even if a UI
            # session is retained as a fallback. The UI session must not disable
            # the primary REST API or leave repair calls with an empty blog ID.
            blogger_api = blogger_service()
            bid = blog_id(blogger_api, config["blogger_url"])
            if not use_ui:
                cleanup_misdated_automation_posts(blogger_api, bid, rows, today_cairo)
                deduped = dedupe_blogger_topics(blogger_api, bid, rows)
                print(f"Blogger dedupe: removed {deduped} duplicate posts.")
        except Exception as api_init_exc:
            if not use_ui:
                raise
            print(f"Blogger REST initialization unavailable; saved UI session remains fallback: {api_init_exc}")
    elif use_ui:
        print("Blogger UI-only mode: no OAuth credentials are configured.")
    else:
        print("Blogger has neither OAuth credentials nor a saved UI session; publication will fail closed.")
    # Image repair must use the Blogger API service, never the Google Sheets
    # service created above. In UI-session mode, skip API-only repair entirely.
    repair_service = None
    if os.getenv("BLOGGER_OAUTH_JSON", "").strip():
        try:
            repair_service = blogger_service()
        except Exception as exc:
            print(f"Blogger image repair skipped: Blogger API service unavailable: {exc}")
    # Never re-upload/re-generate an already published image on every run.
    # Repair is reserved for an explicit bad-image state only.
    if repair_service is not None:
        seen_image_urls = set()
        seen_image_hashes = set()
        # Reconcile a Blogger API insert that succeeded even though the worker
        # crashed before it could write the post ID/permalink back to Sheets.
        if repair_service is not None and bid:
            for reconcile_row_number, reconcile_row in enumerate(rows, start=2):
                if str(reconcile_row.get("الحالة", "")).strip().upper() != "PUBLISHED":
                    continue
                blogger_state = str(reconcile_row.get("Blogger Status", "")).strip().upper()
                image_mode = str(reconcile_row.get("Image Mode", "") or "").strip().upper()
                image_qa_state = str(reconcile_row.get("Image QA Status", "") or "").strip().upper()
                if blogger_state == "PUBLISHED" or not ("FALLBACK" in image_mode or "FALLBACK" in image_qa_state):
                    continue
                try:
                    existing_post = _find_existing_blogger_post_for_row(repair_service, bid, reconcile_row)
                    if not existing_post:
                        continue
                    existing_post_id = str(existing_post.get("id", "") or "").strip()
                    if not existing_post_id:
                        continue
                    # Repair the existing article in place; never insert a duplicate.
                    repaired_url, repaired_score, repaired_sha = _repair_existing_blogger_post_image(
                        repair_service, bid, existing_post_id, reconcile_row_number, reconcile_row
                    )
                    verified_post = repair_service.posts().get(
                        blogId=bid, postId=existing_post_id
                    ).execute()
                    verified_permalink = str(verified_post.get("url", "") or existing_post.get("url", "")).strip()
                    if not verified_permalink.startswith("https://") or repaired_url not in str(verified_post.get("content", "") or ""):
                        raise RuntimeError("BLOGGER_RECONCILIATION_READBACK_FAILED: repaired image or public permalink not confirmed.")
                    update_row(service, config["sheet_id"], sheet_name, reconcile_row_number, {
                        "Blogger Post ID": existing_post_id,
                        "Blogger URL": verified_permalink,
                        "Blogger Search Title": str(verified_post.get("title", "") or ""),
                        "Blogger Status": "PUBLISHED",
                        "Blogger Last Error": "",
                        "Blogger Image URL": repaired_url,
                        "Blogger Image QA Status": "PASS",
                        "Blogger Image QA Score": str(repaired_score),
                        "Blogger Image SHA256": repaired_sha,
                    })
                    reconcile_row["Blogger Post ID"] = existing_post_id
                    reconcile_row["Blogger URL"] = verified_permalink
                    reconcile_row["Blogger Status"] = "PUBLISHED"
                    reconcile_row["Blogger Last Error"] = ""
                    print(f"BLOGGER_EXISTING_POST_RECONCILED: row={reconcile_row_number}; image_score={repaired_score}; url={verified_permalink}")
                    if telegram_configured():
                        try:
                            telegram_send_message(
                                "✅ تم إصلاح صورة مقال Blogger المنشور والتحقق من الرابط\n"
                                f"العنوان: {verified_post.get('title', '')}\n"
                                f"الرابط: {verified_permalink}"
                            )
                        except Exception as telegram_exc:
                            print(f"Blogger reconciliation verified, but Telegram delivery failed: {telegram_exc}")
                except Exception as reconcile_exc:
                    reason = f"BLOGGER_EXISTING_POST_REPAIR_FAILED: {reconcile_exc}"[:1500]
                    _mark_blogger_failed(service, config, sheet_name, reconcile_row_number, reason)
                    print(reason)

        for existing_row_number, existing in enumerate(rows, start=2):
            if str(existing.get("Blogger Status", "")).strip().upper() != "PUBLISHED":
                continue
            image_url_key = str(existing.get("رابط الصورة", "")).strip().split("?", 1)[0].rstrip("/")
            image_hash_key = str(existing.get("Image SHA256", "")).strip().lower()
            duplicate_image = bool((image_url_key and image_url_key in seen_image_urls) or (image_hash_key and image_hash_key in seen_image_hashes))
            if image_url_key:
                seen_image_urls.add(image_url_key)
            if image_hash_key:
                seen_image_hashes.add(image_hash_key)
            if duplicate_image:
                reason = (
                    "BLOGGER_DUPLICATE_IMAGE_BLOCKED: this row's image matches another published Blogger image. "
                    "The shared social/Blogger source image must be repaired by the core publisher before Blogger can proceed."
                )
                update_row(service, config["sheet_id"], sheet_name, existing_row_number, {
                    "Image Mode": "IMAGE_DUPLICATE_BLOCKED",
                    "Image QA Status": "IMAGE_DUPLICATE_BLOCKED",
                    "Image QA Issues": reason[:1500],
                    "Blogger Status": "FAILED",
                    "Blogger Last Error": reason[:1500],
                })
                print(f"BLOGGER_DUPLICATE_IMAGE_BLOCKED: row={existing_row_number}; repair delegated to core image pipeline.")
                continue
            mode = str(existing.get("Image Mode", "") or "").strip().upper()
            qa = str(existing.get("Image QA Status", "")).strip().upper()
            if "FALLBACK" in mode or "FALLBACK" in qa:
                reason = (
                    "BLOGGER_SOURCE_IMAGE_BLOCKED: the existing social image is a generic fallback. "
                    "The core publisher must replace it with a topic-specific QA-approved image first."
                )
                update_row(service, config["sheet_id"], sheet_name, existing_row_number, {
                    "Blogger Status": "FAILED",
                    "Blogger Last Error": reason[:1500],
                })
                print(f"BLOGGER_TOPIC_IMAGE_BLOCKED: row={existing_row_number}; no generic image will be reused.")
    candidates = []
    for row_number, row in enumerate(rows, start=2):
        if str(row.get("الحالة", "")).strip().upper() != "PUBLISHED":
            continue
        if str(row.get("Blogger Status", "")).strip().upper() == "PUBLISHED":
            continue
        # Blogger may only use a topic-specific image that passed semantic or
        # deterministic local QA. Generic, stale, missing, or unreviewed visuals
        # must never be copied into a Blogger article.
        if not str(row.get("المحتوى", "")).strip():
            continue
        image_mode = str(row.get("Image Mode", "") or "").strip().upper()
        image_qa = str(row.get("Image QA Status", "") or "").strip().upper()
        approved_image_states = {"PASS", "REPAIRED_SINGLE_GENERATION", "IMAGE_REPAIR_COMPLETE"}
        if "FALLBACK" in image_mode or "FALLBACK" in image_qa or image_qa not in approved_image_states:
            reason = (
                f"BLOGGER_SOURCE_IMAGE_BLOCKED: Image Mode={image_mode or 'MISSING'}; "
                f"Image QA Status={image_qa or 'MISSING'}. A topic-specific QA-approved image is required."
            )
            _mark_blogger_failed(service, config, sheet_name, row_number, reason)
            print(reason)
            continue
        candidates.append((row_number, row))

    if not candidates:
        print("Blogger worker: no unpublished Blogger rows.")
        return 0

    # Prefer the item that was just published by the social production run.
    # This keeps Blogger on the exact same scheduled content slot instead of
    # accidentally taking an older unpublished row.
    def _recent_key(item):
        _, r = item
        raw = str(r.get("وقت آخر تشغيل", "") or "").strip()
        try:
            from datetime import datetime
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    today = today_cairo.isoformat()
    today_prefix = today.replace("-", "") + "-"
    today_candidates = [
        item for item in candidates
        if (
            str(item[1].get("ID", "")).strip().startswith(today_prefix)
            or parse_date(item[1].get("تاريخ النشر", "")) == today_cairo
        )
    ]
    if not today_candidates:
        print(f"Blogger worker: no published Sheet row for today ({today}); refusing to publish an older row.")
        return 0
    candidates = today_candidates
    print(f"Blogger: publishing only today's scheduled row(s) ({today}).")
    candidates.sort(key=_recent_key, reverse=True)
    row_number, row = candidates[0]
    update_row(service, config["sheet_id"], sheet_name, row_number, {
        "Blogger Status": "PROCESSING",
        "Blogger Last Error": "",
    })
    topic = str(row.get("الموضوع", "")).strip()
    post = str(row.get("المحتوى", "")).strip()
    image_url = str(row.get("رابط الصورة", "")).strip()
    source_id = str(row.get("ID", "")).strip()
    # Never let two Blogger rows inherit the same source image URL.
    normalized_image_url = image_url.split("?", 1)[0].rstrip("/")
    duplicate_owner = next((
        str(other.get("ID", "")).strip() for other in rows
        if str(other.get("ID", "")).strip() != source_id
        and normalized_image_url
        and str(other.get("رابط الصورة", "")).strip().split("?", 1)[0].rstrip("/") == normalized_image_url
    ), "")
    image_path = "" if duplicate_owner else resolve_image_path(image_url, source_id, row_number)
    if duplicate_owner:
        print(f"BLOGGER_DUPLICATE_IMAGE_REPLACEMENT: row={row_number} shared image belongs to source_id={duplicate_owner}; generating a new row-specific hero.")
        image_url = ""
    if image_path:
        # Repair legacy raw GitHub URLs that omitted the branch component.
        corrected_public_image = github_raw_url(image_path)
        if corrected_public_image:
            image_url = corrected_public_image
    if not image_path:
        # Create a topic-derived hero image instead of silently publishing a text-only article.
        try:
            from image_generator import create_legal_image
            generated_image = Path(BLOGGER_ARTIFACT_DIR) / ("row_" + str(row_number)) / "blogger-hero.jpg"
            create_legal_image(
                topic=topic,
                image_brief=post[:1200],
                visual_description=post[:1200],
                post_context=post,
                output_path=str(generated_image),
                api_key=os.getenv("GEMINI_API_KEY", "").strip(),
                cloudflare_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip(),
                cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN", "").strip(),
            )
            image_path = str(generated_image)
            try:
                image_url = upload_blogger_image(image_path)
                print("Blogger: generated hero image uploaded to Blogger storage.")
            except Exception as upload_exc:
                image_url = ""
                print(f"Blogger: image upload failed; refusing an unverified GitHub raw URL: {upload_exc}")
        except Exception as image_exc:
            # Never disguise provider exhaustion with a generic visual or a text-only post.
            failure = f"TOPIC_IMAGE_REQUIRED: no suitable topic-specific image could be generated: {image_exc}"
            _mark_blogger_failed(service, config, sheet_name, row_number, failure)
            raise BloggerPublishError(failure) from image_exc

    if not image_path or not Path(image_path).is_file() or Path(image_path).stat().st_size < 10000:
        failure = "TOPIC_IMAGE_REQUIRED: publication blocked because no valid row-owned image artifact exists."
        _mark_blogger_failed(service, config, sheet_name, row_number, failure)
        raise BloggerPublishError(failure)
    if not image_url:
        try:
            image_url = upload_blogger_image(image_path)
        except Exception as upload_exc:
            failure = f"BLOGGER_IMAGE_UPLOAD_FAILED: generated topic image could not be uploaded; refusing text-only publication: {upload_exc}"
            _mark_blogger_failed(service, config, sheet_name, row_number, failure)
            raise BloggerPublishError(failure) from upload_exc
    if not image_url.startswith("https://"):
        failure = "BLOGGER_IMAGE_URL_INVALID: published image must have a verified HTTPS URL."
        _mark_blogger_failed(service, config, sheet_name, row_number, failure)
        raise BloggerPublishError(failure)

    if image_path and Path(image_path).is_file() and Path(image_path).stat().st_size > 0 and image_url:
        import hashlib
        try:
            update_row(service, config["sheet_id"], sheet_name, row_number, {
                "رابط الصورة": image_url,
                "Image SHA256": hashlib.sha256(Path(image_path).read_bytes()).hexdigest(),
            })
        except Exception as fingerprint_exc:
            print(f"Blogger image identity persistence warning: {fingerprint_exc}")
    # If image generation succeeded but the first Blogger upload attempt failed,
    # retry once before composing the article. Image failure must never cancel publication.
    if image_path and Path(image_path).is_file() and Path(image_path).stat().st_size > 0 and not image_url:
        try:
            image_url = upload_blogger_image(image_path)
            print("Blogger: generated image upload retry succeeded.")
        except Exception as retry_exc:
            image_url = ""
            failure = f"BLOGGER_IMAGE_UPLOAD_FAILED: retry failed; unverified raw asset URLs are not accepted: {retry_exc}"
            _mark_blogger_failed(service, config, sheet_name, row_number, failure)
            raise BloggerPublishError(failure) from retry_exc

    legal_sources = str(row.get("المصادر القانونية", "")).strip()
    if not has_verified_legal_source(legal_sources):
        try:
            refreshed_legal_sources = _refresh_missing_legal_sources(topic, legal_sources)
            if has_verified_legal_source(refreshed_legal_sources):
                legal_sources = refreshed_legal_sources
                update_row(service, config["sheet_id"], sheet_name, row_number, {
                    "المصادر القانونية": legal_sources[:12000],
                })
                print("Blogger legal source recovery: refreshed the queued row with a live verified Egyptian source.")
        except Exception as research_exc:
            print(f"Blogger legal source recovery unavailable: {research_exc}")
    if not has_verified_legal_source(legal_sources):
        failure = (
            "LEGAL_SOURCE_GATE_BLOCKED: no verified Egyptian HTTPS legal source is attached; "
            "the Blogger article was withheld."
        )
        _mark_blogger_failed(service, config, sheet_name, row_number, failure)
        raise BloggerPublishError(failure)

    update_row(service, config["sheet_id"], sheet_name, row_number, {
        "Blogger Status": "PROCESSING",
        "Blogger Last Error": "",
    })

    if os.getenv("BLOGGER_DRY_RUN", "false").strip().lower() in {"1", "true", "yes", "on"}:
        print(f"Blogger DRY RUN: row={row_number}, topic={topic}, title source ready; no post will be published.")
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "Blogger Status": "DRY_RUN_READY",
            "Blogger Last Error": "",
        })
        return 0

    try:
        if use_ui:
            # Every Blogger post must carry its own topic-specific image.
            blogger_image_url = image_url
            if not blogger_image_url or not blogger_image_url.startswith("https://"):
                raise BloggerPublishError("TOPIC_IMAGE_REQUIRED: Blogger publication requires a valid HTTPS image URL.")
            print(f"Blogger: embedding verified row-owned topic image URL: {blogger_image_url}")
            article = None
            editorial_errors = []
            api_key = os.getenv("GEMINI_API_KEY", "").strip()
            model_candidates = list(dict.fromkeys(
                candidate for candidate in [
                    os.getenv("GEMINI_MODEL", "").strip(),
                    os.getenv("GEMINI_FALLBACK_MODEL", "").strip(),
                    "gemini-3.8-flash",
                ]
                if candidate and candidate.casefold().removeprefix("models/") != "gemini-2.5-flash"
            ))
            if api_key:
                for candidate_model in (x for x in model_candidates if x):
                    try:
                        article = prepare_article(
                            api_key=api_key,
                            model=candidate_model,
                            topic=topic,
                            post=post,
                            legal_sources=legal_sources,
                        )
                        print(f"Blogger editorial article generated with model {candidate_model}.")
                        break
                    except Exception as exc:
                        editorial_errors.append(f"{candidate_model}: {exc}")
                        print(f"Blogger editorial generation failed with {candidate_model}: {exc}")
                        error_text = str(exc).casefold()
                        if "resource_exhausted" in error_text or "quota" in error_text or "429" in error_text:
                            print("Blogger editorial quota/rate limit detected; skipping further model retries and using the local structured fallback.")
                            break
            if not isinstance(article, dict):
                print("Blogger editorial layer unavailable; using structured fallback: " + " | ".join(editorial_errors))
                article = _fallback_article(topic, post, legal_sources)
            article = _article_copy(article or {})
            # Reject title-only/near-empty model output before it reaches Blogger.
            # The structured fallback expands the original Sheet content into a complete article.
            article_text_parts = [str(article.get("lead", "")), str(article.get("meta_description", ""))]
            for section in article.get("sections", []) if isinstance(article.get("sections"), list) else []:
                if isinstance(section, dict):
                    article_text_parts.extend([str(section.get("heading", "")), str(section.get("body", ""))])
            for item in article.get("faq", []) if isinstance(article.get("faq"), list) else []:
                if isinstance(item, dict):
                    article_text_parts.extend([str(item.get("question", "")), str(item.get("answer", ""))])
            article_text_length = len(" ".join(article_text_parts).strip())
            if article_text_length < 900 or len(article.get("sections", [])) < 3:
                print(f"Blogger editorial output too short/incomplete (chars={article_text_length}); switching to structured full-article fallback.")
                article = _fallback_article(topic, post, legal_sources)
            title = str(article.get("title") or topic).strip()[:110]
            related = _related_internal_pages(topic)
            content = build_article_html(title, topic, post, blogger_image_url, legal_sources, related, article=article)
            if len(content) < 1500:
                print("Blogger HTML remained unusually short; rebuilding with the deterministic full-article fallback.")
                article = _fallback_article(topic, post, legal_sources)
                title = str(article.get("title") or topic).strip()[:110]
                content = build_article_html(title, topic, post, blogger_image_url, legal_sources, [], article=article)
            labels = normalize_blogger_labels([
                "قانون مصر",
                "اسأل محمود",
                *[str(x).strip() for x in article.get("keywords", []) if str(x).strip()],
            ])
            print(f"Blogger labels normalized: count={len(labels)} combined_chars={len(', '.join(labels))}")
            # Idempotency guard: a previous retry may already have published this
            # title even if the Sheet/artifact commit failed. Never create another
            # Blogger post when the public feed can verify an existing permalink.
            existing_public_url, existing_public_id = _public_post_permalink(
                config["blogger_url"], title, attempts=1
            )
            if existing_public_url:
                result = {
                    "post_id": existing_public_id or "",
                    "post_url": existing_public_url,
                    "title": title,
                    "publisher": "EXISTING_PUBLIC_POST",
                }
                print(f"Blogger duplicate prevention: reusing existing public post {existing_public_url}")
            elif os.getenv("BLOGGER_OAUTH_JSON", "").strip():
                # Prefer the REST API, but attempt the authenticated browser session if
                # OAuth refresh has been revoked/expired. Both paths verify the result.
                try:
                    blogger_api = blogger_service()
                    target_blog_id = bid or blog_id(blogger_api, config["blogger_url"])
                    published = blogger_api.posts().insert(
                        blogId=target_blog_id,
                        body={
                            "kind": "blogger#post",
                            "title": title,
                            "content": content,
                            "labels": labels,
                        },
                        isDraft=False,
                    ).execute()
                    result = {
                        "post_id": str(published.get("id", "")),
                        "post_url": str(published.get("url", "")),
                        "title": str(published.get("title", title)),
                        "publisher": "BLOGGER_REST_API",
                    }
                    if not result["post_id"] or not result["post_url"]:
                        raise BloggerPublishError("Blogger REST API did not return a verifiable published post ID and URL.")
                    print("Blogger article published through REST API.")
                except Exception as api_exc:
                    print(f"Blogger REST API unavailable; trying the saved authenticated UI session: {api_exc}")
                    result = publish_article_ui(
                        title=title,
                        content_html=content,
                        labels=labels,
                        blog_id=bid,
                        blog_url=config["blogger_url"],
                        search_description=str(article.get("meta_description", "")).strip()[:180],
                    )
            else:
                result = publish_article_ui(
                    title=title,
                    content_html=content,
                    labels=labels,
                    blog_id=bid,
                    blog_url=config["blogger_url"],
                    search_description=str(article.get("meta_description", "")).strip()[:180],
                )
            result["search_query"] = title
            result["search_candidates"] = json.dumps([title, *labels], ensure_ascii=False)
            result["meta_description"] = str(article.get("meta_description", "")).strip()[:150]
            target = Path(f"{BLOGGER_ARTIFACT_DIR}/row_{row_number}")
            target.mkdir(parents=True, exist_ok=True)
            (target / "article.html").write_text(content, encoding="utf-8")
        else:
            result = publish_article(
                topic=topic,
                post=post,
                image_url=image_url,
                image_path=image_path,
                legal_sources=legal_sources,
                output_dir=f"{BLOGGER_ARTIFACT_DIR}/row_{row_number}",
            )
        # Verify the published Blogger resource itself before recording success.
        if not str(result.get("post_id", "")).strip() or not str(result.get("post_url", "")).startswith("https://"):
            raise BloggerPublishError("BLOGGER_POST_VERIFICATION_FAILED: missing published post ID or HTTPS permalink.")

        # Prefer authenticated API read-back whenever OAuth is available. If the
        # token is revoked and the saved UI session published the post, fall back
        # to the public permalink; public 429s must not block a valid API read-back.
        verified_html = ""
        if has_blogger_oauth:
            try:
                verify_service = blogger_service()
                verify_blog_id = bid or blog_id(verify_service, config["blogger_url"])
                verified_post = verify_service.posts().get(
                    blogId=verify_blog_id,
                    postId=str(result.get("post_id", "")).strip(),
                ).execute()
                verified_html = str(verified_post.get("content", "") or "")
                result["post_url"] = str(verified_post.get("url", "") or result.get("post_url", "")).strip()
            except Exception as api_verify_exc:
                print(f"Blogger API read-back unavailable; attempting public permalink verification: {api_verify_exc}")
        if not verified_html:
            public_response = requests.get(
                str(result["post_url"]).strip(),
                headers={"User-Agent": "Mozilla/5.0 KhyratLegalContentEngine/1.0"},
                timeout=(10, 30),
            )
            public_response.raise_for_status()
            verified_html = str(public_response.text or "")
        verified_text = " ".join(re.sub(r"<[^>]+>", " ", verified_html).split())
        if len(verified_text) < 900:
            raise BloggerPublishError("BLOGGER_POST_VERIFICATION_FAILED: public/API read-back found an incomplete article body.")
        if image_url not in verified_html:
            raise BloggerPublishError("BLOGGER_POST_VERIFICATION_FAILED: public/API read-back did not find the required topic image.")
        if not str(result.get("post_url", "")).startswith("https://"):
            raise BloggerPublishError("BLOGGER_POST_VERIFICATION_FAILED: read-back did not return an HTTPS permalink.")

        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "Blogger Status": "PUBLISHED",
            "Blogger Post ID": result["post_id"],
            "Blogger URL": result["post_url"],
            "Blogger Search Title": result["title"],
            "Blogger Search Query": result["search_query"],
            "Blogger Search Candidates": result["search_candidates"],
            "Blogger Meta Description": result.get("meta_description", ""),
            "Blogger SEO Status": "PENDING",
            "Blogger SEO Error": "",
            "Blogger Last Error": "",
        })
        print(f"Blogger published and read-back verified: {result['title']} -> {result['post_url']}")
        # A Telegram success notice is permitted only after Blogger read-back and
        # the Sheet PUBLISHED state have both been persisted successfully.
        if telegram_configured():
            try:
                telegram_send_message(
                    "✅ تم نشر مقال Blogger والتحقق منه فعليًا\n"
                    f"العنوان: {result['title']}\n"
                    f"الرابط: {result['post_url']}"
                )
            except Exception as telegram_exc:
                print(f"Blogger success was verified, but Telegram delivery failed: {telegram_exc}")
        return 0
    except BloggerUIPublishError as ui_exc:
        error = f"UI: {ui_exc}"[:1500]
        # Browser autosave is unreliable in this Blogger account. If OAuth is repaired,
        # use the REST API to patch a title-only post in place or publish the prepared body.
        try:
            if not os.getenv("BLOGGER_OAUTH_JSON", "").strip() or "content" not in locals():
                raise BloggerPublishError("Blogger REST fallback requires a valid BLOGGER_OAUTH_JSON token and prepared article HTML.")
            blogger_api = blogger_service()
            target_blog_id = bid or blog_id(blogger_api, config["blogger_url"])
            page_token = None
            existing = None
            while True:
                kwargs = {"blogId": target_blog_id, "maxResults": 500, "fetchBodies": True}
                if page_token:
                    kwargs["pageToken"] = page_token
                batch = blogger_api.posts().list(**kwargs).execute()
                for item in batch.get("items", []) or []:
                    if str(item.get("title", "")).strip().casefold() == title.strip().casefold():
                        existing = item
                        break
                if existing or not batch.get("nextPageToken"):
                    break
                page_token = batch.get("nextPageToken")
            if existing:
                existing_id = str(existing.get("id", "")).strip()
                existing_html = str(existing.get("content", "") or "")
                visible_text = " ".join(re.sub(r"<[^>]+>", " ", existing_html).split())
                expected_image = str(locals().get("blogger_image_url", "") or "")
                if len(visible_text) < 900 or (expected_image and expected_image not in existing_html):
                    saved = blogger_api.posts().patch(blogId=target_blog_id, postId=existing_id, body={"content": content}).execute()
                else:
                    saved = existing
            else:
                saved = blogger_api.posts().insert(
                    blogId=target_blog_id,
                    body={"kind": "blogger#post", "title": title, "content": content, "labels": labels, "searchDescription": str(article.get("meta_description", "")).strip()[:150]},
                    isDraft=False,
                ).execute()
            saved_id = str(saved.get("id", "") or (existing or {}).get("id", "")).strip()
            saved_post = blogger_api.posts().get(blogId=target_blog_id, postId=saved_id).execute()
            saved_html = str(saved_post.get("content", "") or "")
            saved_text = " ".join(re.sub(r"<[^>]+>", " ", saved_html).split())
            if not saved_id or len(saved_text) < 900:
                raise BloggerPublishError("REST verification failed: Blogger article body is still incomplete.")
            expected_image = str(locals().get("blogger_image_url", "") or "")
            if expected_image and expected_image not in saved_html:
                raise BloggerPublishError("REST verification failed: generated article image is not embedded.")
            result = {
                "post_id": saved_id,
                "post_url": str(saved_post.get("url", "") or saved.get("url", "")),
                "title": str(saved_post.get("title", "") or title),
                "publisher": "BLOGGER_REST_REPAIR",
                "search_query": title,
                "search_candidates": json.dumps([title, *labels], ensure_ascii=False),
                "meta_description": str(article.get("meta_description", "")).strip()[:180],
            }
            if not result["post_url"]:
                raise BloggerPublishError("REST verification did not return a public post URL.")
            update_row(service, config["sheet_id"], sheet_name, row_number, {
                "Blogger Status": "PUBLISHED", "Blogger Post ID": result["post_id"],
                "Blogger URL": result["post_url"], "Blogger Search Title": result["title"],
                "Blogger Search Query": result["search_query"], "Blogger Search Candidates": result["search_candidates"],
                "Blogger Meta Description": result["meta_description"], "Blogger SEO Status": "PENDING",
                "Blogger SEO Error": "", "Blogger Last Error": "",
            })
            print(f"Blogger REST fallback verified full article: {result['post_url']}")
            return 0
        except Exception as rest_exc:
            error = f"UI failed: {ui_exc}; REST repair failed: {rest_exc}"[:1500]
            update_row(service, config["sheet_id"], sheet_name, row_number, {
                "Blogger Status": "FAILED", "Blogger Last Error": error,
            })
            print(f"Blogger publication remains retryable; neither UI nor REST verified a complete article: {error}")
            return 1
    except BloggerPublishError as exc:
        error = str(exc)[:1500]
        _mark_blogger_failed(service, config, sheet_name, row_number, error)
        print(f"Blogger publication failed (retryable): {error}")
        return 1
    except Exception as exc:
        error = f"UNEXPECTED_BLOGGER_FAILURE: {exc}"[:1500]
        _mark_blogger_failed(service, config, sheet_name, row_number, error)
        print(f"Blogger publication failed unexpectedly (retryable): {error}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
