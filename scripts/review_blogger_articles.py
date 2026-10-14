from __future__ import annotations

import hashlib
import html
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path

from blogger_editor import prepare_article
from blogger_publisher import (
    DEFAULT_BLOG_URL, _article_copy, _tags, blog_id, build_article_html,
    normalize_blogger_labels, service, upload_blogger_image,
)

STATE_PATH = Path(os.getenv("BLOGGER_REVIEW_STATE", "data/blogger_article_review_state.json"))
OUTPUT_DIR = Path("generated/blogger/reviewed")


class ArticleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        elif tag in {"p", "div", "section", "article", "h1", "h2", "h3", "li", "br"} and not self.skip:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1
        elif tag in {"p", "div", "section", "article", "h1", "h2", "h3", "li"} and not self.skip:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def visible_text(content: str) -> str:
    parser = ArticleText()
    parser.feed(content or "")
    text = html.unescape(" ".join(" ".join(parser.parts).split()))
    # Remove known prompt leakage before the rewrite model sees the article.
    patterns = [
        r"المطلوب\s+مقال\s+توعوي.*?(?=[.!؟]|$)",
        r"لا\s+تذكر\s+أرقام\s+مواد.*?(?=[.!؟]|$)",
        r"ما\s+لم\s+تكن\s+موجودة\s+صراحة\s+في\s+المصادر.*?(?=[.!؟]|$)",
        r"يتم\s+مراجعة\s+كل\s+المقالات.*?(?=[.!؟]|$)",
        r"أنا\s+ذكاء\s+اصطناعي.*?(?=[.!؟]|$)",
        r"هذه\s+المقالة\s+(?:تمت|جرى)\s+كتابتها\s+بواسطة\s+الذكاء\s+الاصطناعي.*?(?=[.!؟]|$)",
    ]
    for pattern in patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def load_state() -> dict:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("reviewed_ids", [])
            return data
    except Exception:
        pass
    return {"schema_version": 1, "reviewed_ids": [], "failed_ids": []}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    from ai_router import has_any_provider_key
    if not has_any_provider_key():
        raise RuntimeError(
            "No text AI provider is configured. Set at least one of GEMINI_API_KEY, "
            "GROQ_API_KEY, CEREBRAS_API_KEY, or OPENROUTER_API_KEY."
        )
    max_posts = max(1, min(25, int(os.getenv("BLOGGER_REVIEW_LIMIT", "10"))))
    model = os.getenv("GEMINI_MODEL", "").strip() or os.getenv("GEMINI_FALLBACK_MODEL", "").strip() or "gemini-3.6-flash"
    print("Text AI providers configured: " + ", ".join(name for name, env in [("Gemini", "GEMINI_API_KEY"), ("Groq", "GROQ_API_KEY"), ("Cerebras", "CEREBRAS_API_KEY"), ("OpenRouter", "OPENROUTER_API_KEY")] if os.getenv(env, "").strip()))
    svc = service()
    bid = blog_id(svc, os.getenv("BLOGGER_URL", DEFAULT_BLOG_URL).strip())
    state = load_state()
    reviewed = set(str(x) for x in state.get("reviewed_ids", []))
    batch = svc.posts().list(blogId=bid, status="LIVE", fetchBodies=False, maxResults=500, orderBy="PUBLISHED").execute()
    posts = [p for p in (batch.get("items") or []) if str(p.get("id", "")) and str(p.get("title", "")).strip()]
    # Include additional pages; Blogger can return more than one page of live posts.
    token = batch.get("nextPageToken")
    while token:
        batch = svc.posts().list(blogId=bid, status="LIVE", fetchBodies=False, maxResults=500, orderBy="PUBLISHED", pageToken=token).execute()
        posts.extend(p for p in (batch.get("items") or []) if str(p.get("id", "")) and str(p.get("title", "")).strip())
        token = batch.get("nextPageToken")
    pending = [p for p in posts if str(p["id"]) not in reviewed]
    print(f"Live posts={len(posts)}; already reviewed={len(reviewed)}; pending={len(pending)}; this batch limit={max_posts}")
    if not pending:
        print("All live posts are marked reviewed.")
        return 0

    from image_generator import create_legal_image
    succeeded = 0
    failures = []
    for summary in pending[:max_posts]:
        post_id = str(summary["id"])
        old_title = str(summary.get("title", "")).strip()
        try:
            current = svc.posts().get(blogId=bid, postId=post_id, fetchBody=True).execute()
            old_html = str(current.get("content", "") or "")
            source_text = visible_text(old_html)
            if len(source_text) < 300:
                raise RuntimeError(f"Article body is too short to safely rewrite ({len(source_text)} chars).")
            article = prepare_article(
                api_key=api_key,
                model=model,
                topic=old_title,
                post=source_text[:18000],
                legal_sources=(
                    "No separately verified source packet is available for this legacy post. "
                    "Preserve only legal claims already supported by the source text; do not add statute numbers, "
                    "penalties, deadlines, court rulings, citations, or precise legal conclusions. "
                    "Where verification is missing, explain what facts and official sources the reader should check."
                ),
            )
            article = _article_copy(article)
            title = str(article.get("title") or old_title).strip()[:110]
            if not title or not article.get("lead") or len(article.get("sections", [])) < 2:
                raise RuntimeError("Rewritten article failed minimum completeness checks.")
            scene = " ".join([
                str(article.get("lead", "")),
                str(article.get("sections", [{}])[0].get("heading", "")),
                str(article.get("sections", [{}])[0].get("body", ""))[:700],
            ]).strip()[:1200]
            image_key = hashlib.sha256((post_id + "|" + title + "|" + scene).encode("utf-8")).hexdigest()[:14]
            image_path = OUTPUT_DIR / f"{image_key}.jpg"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            create_legal_image(
                topic=title,
                image_brief="Unique article-specific editorial photograph. Scene: " + scene,
                visual_description="A realistic contemporary scene showing this specific situation: " + scene,
                post_context=(title + "\n" + str(article.get("lead", "")) + "\n" + scene)[:1800],
                output_path=str(image_path),
                api_key=api_key,
                cloudflare_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip(),
                cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN", "").strip(),
            )
            if not image_path.is_file() or image_path.stat().st_size < 1000:
                raise RuntimeError("A distinct article image was not generated; refusing to update the live post.")
            image_url = upload_blogger_image(str(image_path))
            related = []
            # Keep existing links to avoid inventing URLs; the article builder adds standard internal navigation.
            article_html = build_article_html(
                title=title,
                topic=title,
                post=str(article.get("lead", "")),
                image_url=image_url,
                legal_sources="",
                related=related,
                article=article,
            )
            labels = normalize_blogger_labels(["قانون مصر", "اسأل محمود", *(article.get("keywords") or [])])
            svc.posts().patch(
                blogId=bid, postId=post_id,
                body={"title": title, "content": article_html},
            ).execute()
            verify = svc.posts().get(blogId=bid, postId=post_id, fetchBody=True).execute()
            verify_html = str(verify.get("content", "") or "")
            verify_text = visible_text(verify_html)
            if len(verify_text) < 900 or not re.search(r"<img\b[^>]*src=", verify_html, re.I):
                raise RuntimeError("Post update could not be verified with a substantial body and embedded image.")
            if re.search(r"(المطلوب مقال توعوي|يتم مراجعة كل المقالات|أنا ذكاء اصطناعي)", verify_text, re.I):
                raise RuntimeError("Prompt leakage remained after rewrite; post not marked complete.")
            reviewed.add(post_id)
            state["reviewed_ids"] = sorted(reviewed)
            state["failed_ids"] = [x for x in state.get("failed_ids", []) if str(x) != post_id]
            state["last_title"] = title
            state["last_post_url"] = str(verify.get("url", "") or "")
            save_state(state)
            succeeded += 1
            print(f"REVIEWED_AND_VERIFIED: {title} | {verify.get('url', '')} | unique image uploaded")
        except Exception as exc:
            failures.append({"id": post_id, "title": old_title, "error": str(exc)[:500]})
            print(f"FAILED (will retry): {old_title} | {exc}")
            error_text = str(exc).upper()
            if any(marker in error_text for marker in ("RESOURCE_EXHAUSTED", "QUOTA EXCEEDED", "429")):
                print("Gemini quota/rate limit detected; stopping this batch immediately to avoid repeated doomed requests.")
                break
    state["failed_ids"] = failures
    state["last_batch_success_count"] = succeeded
    save_state(state)
    print(f"Batch complete: success={succeeded}; failed={len(failures)}; total_reviewed={len(reviewed)}/{len(posts)}")
    # Failed items are deliberately not marked reviewed and will be retried on the next run.
    return 1 if failures and succeeded == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
