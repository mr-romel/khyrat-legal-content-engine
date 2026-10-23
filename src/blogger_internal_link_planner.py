from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


STOPWORDS = {
    "في", "من", "على", "عن", "الى", "إلى", "ما", "هل", "كيف", "متى", "مع",
    "هذا", "هذه", "ذلك", "تلك", "التي", "الذي", "و", "او", "أو", "ثم",
    "the", "and", "for", "with", "from", "that", "this",
}


def normalize_url(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return str(value or "").strip().rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))


def title_terms(title: str) -> set[str]:
    text = str(title or "").casefold()
    text = re.sub(r"[إأآٱ]", "ا", text).replace("ى", "ي").replace("ة", "ه")
    terms = re.findall(r"[a-z0-9\u0600-\u06ff]+", text)
    return {term for term in terms if len(term) > 2 and term not in STOPWORDS}


def build_plan(audit: dict, max_links_per_post: int = 3) -> dict:
    posts = [p for p in audit.get("posts", []) if p.get("url") and p.get("title")]
    token_map = {normalize_url(p["url"]): title_terms(p["title"]) for p in posts}
    recommendations = []
    for post in posts:
        source = normalize_url(post["url"])
        source_terms = token_map.get(source, set())
        candidates = []
        for target in posts:
            target_url = normalize_url(target["url"])
            if target_url == source:
                continue
            overlap = source_terms & token_map.get(target_url, set())
            # Require two meaningful shared title terms to reduce unrelated suggestions.
            if len(overlap) < 2:
                continue
            candidates.append((len(overlap), target["title"], target_url, sorted(overlap)))
        candidates.sort(key=lambda item: (-item[0], item[1]))
        existing = {normalize_url(x) for x in post.get("internal_links_to_known_posts", [])}
        for score, title, url, terms in candidates:
            if url in existing:
                continue
            recommendations.append({
                "source_title": post["title"], "source_url": post["url"],
                "target_title": title, "target_url": url,
                "shared_terms": terms, "relevance_score": score,
                "status": "REVIEW_REQUIRED",
                "instruction": "Add only if the target genuinely helps the reader in this paragraph; do not add links solely for SEO."
            })
            if sum(1 for row in recommendations if row["source_url"] == post["url"]) >= max_links_per_post:
                break
    return {
        "generated_at": audit.get("generated_at", ""),
        "blog_url": audit.get("blog_url", ""),
        "posts_in_audit": len(posts),
        "recommendations": len(recommendations),
        "automatically_published": False,
        "important_limit": "Suggestions use title-term overlap only; a human must confirm topical and legal relevance before editing live posts.",
        "items": recommendations,
    }


def write_plan(audit_path: str = "artifacts/seo-audit/report.json",
               output_dir: str = "artifacts/seo-audit") -> dict:
    source = Path(audit_path)
    audit = json.loads(source.read_text(encoding="utf-8"))
    result = build_plan(audit)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "internal-link-plan.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Contextual Internal-Link Plan", "",
        f"- Posts analyzed: {result['posts_in_audit']}",
        f"- Suggestions: {result['recommendations']}",
        "- Live articles changed: 0 (review-only plan)",
        "",
        "> Suggestions are based on title overlap, not full legal-context understanding. Confirm each link is useful and legally relevant before adding it.",
        "",
    ]
    for item in result["items"]:
        lines += [
            f"## {item['source_title']}",
            f"- Source: {item['source_url']}",
            f"- Suggested target: [{item['target_title']}]({item['target_url']})",
            f"- Shared terms: {', '.join(item['shared_terms'])}",
            f"- Relevance score: {item['relevance_score']}",
            f"- Status: {item['status']}",
            "",
        ]
    (out / "internal-link-plan.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("posts_in_audit", "recommendations", "automatically_published")}, ensure_ascii=False))
    return result


if __name__ == "__main__":
    write_plan()
