from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from blogger_publisher import BloggerPublishError, blog_id, publish_article, upload_blogger_image, build_article_html, prepare_article, _article_copy, _fallback_article, service as blogger_service
from blogger_ui_publisher import BloggerUIPublishError, publish_article_ui, _public_post_permalink
from config import load_blogger_config
from sheets import create_service, ensure_headers, get_values, row_to_dict, update_row, HEADERS
from utils import parse_date

BLOGGER_ARTIFACT_DIR = "generated/blogger"

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

def _norm_text(value: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return " ".join(text.split()).casefold()

def dedupe_blogger_topics(svc, bid: str, rows: list[dict[str, str]]) -> int:
    """Delete duplicate Blogger posts for the same generated article, keeping the oldest copy."""
    import re
    def key(value: str) -> str:
        text = re.sub(r"<[^>]+>", " ", str(value or ""))
        text = re.sub(r"\\s+", " ", text).strip().casefold()
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
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today_cairo = datetime.now(ZoneInfo("Africa/Cairo")).date()
    use_ui = bool(config.get("blogger_ui_storage_state_b64"))
    bid = str(config.get("blogger_blog_id", "") or "").strip()
    if not use_ui:
        blogger_api = blogger_service()
        bid = blog_id(blogger_api, config["blogger_url"])
        cleanup_misdated_automation_posts(blogger_api, bid, rows, today_cairo)
        deduped = dedupe_blogger_topics(blogger_api, bid, rows)
        print(f"Blogger dedupe: removed {deduped} duplicate posts.")
    else:
        print("Blogger UI session detected: bypassing Blogger REST OAuth initialization.")
    # Never re-upload/re-generate an already published image on every run.
    # Repair is reserved for an explicit bad-image state only.
    for existing in rows:
        if str(existing.get("Blogger Status", "")).strip().upper() != "PUBLISHED":
            continue
        mode = str(existing.get("Image Mode", "") or "").strip().upper()
        qa = str(existing.get("Image QA Status", "") or "").strip().upper()
        if "FALLBACK" in mode or "FALLBACK" in qa:
            repair_published_image(service, bid, existing)
    candidates = []
    for row_number, row in enumerate(rows, start=2):
        if str(row.get("الحالة", "")).strip().upper() != "PUBLISHED":
            continue
        if str(row.get("Blogger Status", "")).strip().upper() == "PUBLISHED":
            continue
        # Blogger is independent from social publication. A valid published
        # content row is enough; Facebook/LinkedIn IDs are not required.
        if not str(row.get("المحتوى", "")).strip():
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
    topic = str(row.get("الموضوع", "")).strip()
    post = str(row.get("المحتوى", "")).strip()
    image_url = str(row.get("رابط الصورة", "")).strip()
    source_id = str(row.get("ID", "")).strip()
    image_path = resolve_image_path(image_url, source_id, row_number)
    if not image_path:
        # Article publication is independent from social-image availability.
        # Keep the article moving; an image is an enhancement, never a blocker.
        print("Blogger: no row-owned image available; continuing with a text-first article.")

    legal_sources = str(row.get("المصادر القانونية", "")).strip()

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
            # Upload to Blogger storage; Rich Editor should not embed the raw GitHub asset URL.
            blogger_image_url = image_url
            if blogger_image_url:
                print(f"Blogger UI: embedding row-owned generated image URL: {blogger_image_url}")
            else:
                print("Blogger UI: publishing a text-first article because no image is available.")
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
            if not isinstance(article, dict):
                print("Blogger editorial layer unavailable; using structured fallback: " + " | ".join(editorial_errors))
                article = _fallback_article(topic, post, legal_sources)
            article = _article_copy(article or {})
            title = str(article.get("title") or topic).strip()[:110]
            content = build_article_html(title, topic, post, blogger_image_url, legal_sources, [], article=article)
            labels = list(dict.fromkeys([
                "قانون مصر",
                "اسأل محمود",
                *[str(x).strip() for x in article.get("keywords", []) if str(x).strip()],
            ]))[:10]
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
            result["meta_description"] = str(article.get("meta_description", "")).strip()[:180]
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
        print(f"Blogger published: {result['title']} -> {result['post_url']}")
        return 0
    except BloggerUIPublishError as ui_exc:
        error = f"UI: {ui_exc}"[:1500]
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "Blogger Status": "FAILED",
            "Blogger Last Error": error,
        })
        print(f"Blogger UI publication failed (retryable); REST fallback intentionally disabled when UI session is configured: {error}")
        return 1
    except BloggerPublishError as exc:
        error = str(exc)[:1500]
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "Blogger Status": "FAILED",
            "Blogger Last Error": error,
        })
        print(f"Blogger publication failed (retryable): {error}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
